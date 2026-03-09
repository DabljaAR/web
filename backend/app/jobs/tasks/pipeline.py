"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.
"""
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from celery import chain

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus

logger = logging.getLogger(__name__)


# ===========================================================================
# Speech-to-Text
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.stt_transcribe",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_stt",
)
def stt_transcribe(
    self,
    job_id: str,
    video_id: str,
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe the audio track of *video_id*.

    Downloads the file from MinIO, runs Whisper via the shared
    ``transcribe_task`` model instance (loaded once per worker), then
    stores the result in the Job row.

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript_key": None,          # raw file unchanged in storage
            "transcript":     str,           # full text
            "segments":       list[dict],    # [{start, end, text}, ...]
            "metadata":       dict,
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    # Import the task instance — its base IS WhisperModelManager,
    # so calling .transcribe() reuses the single model loaded in this worker.
    from app.stt.models import transcribe_task as whisper

    storage = get_storage_service()

    # ── 1. Mark PROCESSING + record Celery task id ───────────────────────────
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )

    # ── 2. Look up the Video row to get the MinIO key ────────────────────────
    async def _get_file_key() -> str:
        from app.core.db import AsyncSessionLocal
        from app.media.models import Video
        async with AsyncSessionLocal() as db:
            video = await db.get(Video, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found.")
            # Prefer the extracted audio track; fall back to the raw file
            return video.audio_path or video.file_path

    file_key: str = self._run_sync(_get_file_key())
    logger.info("[STT pipeline] job=%s video=%s file_key=%s", job_id, video_id, file_key)

    self.update_progress(job_id, 10.0)

    # ── 3. Download from MinIO ───────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix     = Path(file_key).suffix or ".mp3"
        local_path = Path(tmp_dir) / f"audio{suffix}"

        if isinstance(storage, S3StorageService):
            async def _download():
                async with storage.session.client(
                    "s3",
                    endpoint_url=storage.endpoint_url,
                    aws_access_key_id=storage.access_key,
                    aws_secret_access_key=storage.secret_key,
                ) as s3:
                    await s3.download_file(
                        storage.bucket_name, file_key, str(local_path)
                    )

            self._run_sync(_download())
            logger.info("[STT pipeline] downloaded %s → %s", file_key, local_path)
        else:
            # Local storage — point directly at the file, no copy needed
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe using the shared WhisperModelManager instance ──────
        # whisper IS the transcribe_task instance whose base=WhisperModelManager,
        # so whisper.transcribe() calls WhisperModelManager.transcribe() and the
        # model is lazy-loaded once, then reused for every subsequent task call.
        try:
            result: dict = whisper.transcribe(str(local_path), language=language)
        except Exception as exc:
            logger.error("[STT pipeline] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

    self.update_progress(job_id, 90.0)

    # ── 5. Persist output_data — on_success hook will set COMPLETED ──────────
    output = {
        "job_id":         job_id,
        "video_id":       video_id,
        "transcript_key": file_key,   # the source audio key — unchanged
        "transcript":     result["transcript"],
        "segments":       result["segments"],
        "metadata":       result["metadata"],
    }

    self._run_sync(
        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
    )

    logger.info(
        "[STT pipeline] job=%s done | duration=%.1fs | segments=%d",
        job_id,
        result["metadata"].get("duration", 0),
        result["metadata"].get("segment_count", 0),
    )

    return output


# ===========================================================================
# Neural Machine Translation
# ===========================================================================

from app.jobs.tasks.nmt import nmt_translate

# ===========================================================================
# Text-to-Speech
# ===========================================================================

@celery_app.task(
    bind=True,
    # ── NOTE: We do NOT use BaseJobTask as the base class here. ──────────
    # This prevents the automatic lifecycle hooks from crashing when they
    # encounter a dictionary as the first argument in a Celery chain.
    # Instead, we use its STATIC methods manually.
    name="app.jobs.tasks.pipeline.tts_synthesize",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_tts",
)
def tts_synthesize(
    self,
    job_id: Any,
    video_id: Optional[str] = None,
    translation_key: Optional[str] = None,
    target_lang: str = "en",
) -> dict:
    """
    Stub: synthesise speech from the translated text.

    Returns:
        {"job_id": job_id, "video_id": video_id, "audio_key": None}
    """
    if isinstance(job_id, dict):
        result = job_id
        job_id = result.get("job_id")
        video_id = video_id or result.get("video_id")
        translation_key = translation_key or result.get("transcript_key") or result.get("translation_key")
        target_lang = result.get("target_lang") or target_lang or "en"

    if job_id:
        BaseJobTask._run_sync(
            BaseJobTask._patch_job(
                job_id,
                JobStatus.PROCESSING,
                celery_task_id=self.request.id,
                started_at=datetime.utcnow(),
            )
        )

    try:
        # TODO: call TTS service
        logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)
        
        output = {"job_id": job_id, "video_id": video_id, "audio_key": None}
        
        if job_id:
            BaseJobTask._run_sync(
                BaseJobTask._patch_job(
                    job_id,
                    JobStatus.COMPLETED,
                    progress=100.0,
                    completed_at=datetime.utcnow()
                )
            )
        return output
        
    except Exception as e:
        logger.error("tts_synthesize failed for job %s: %s", job_id, e)
        if job_id:
            BaseJobTask._run_sync(
                BaseJobTask._patch_job(
                    job_id,
                    JobStatus.FAILED,
                    error_message=str(e),
                    completed_at=datetime.utcnow()
                )
            )
        raise


# ===========================================================================
# Dubbing merge
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.dubbing_merge",
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
)
def dubbing_merge(self, job_id: str, video_id: str, audio_key: str) -> dict:
    """
    Stub: merge the synthesised audio track with the original video.

    Returns:
        {"job_id": job_id, "video_id": video_id, "output_key": "<storage_key>"}
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call FFmpeg merge service
    logger.info("[STUB] dubbing_merge job=%s video=%s", job_id, video_id)
    return {"job_id": job_id, "video_id": video_id, "output_key": None}


# ===========================================================================
# Full dubbing pipeline (orchestrator)
# ===========================================================================

def dispatch_full_dubbing_pipeline(
    job_id: str,
    video_id: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> None:
    """
    Dispatch the full dubbing pipeline as a Celery ``chain``.

    Sequence: stt_transcribe → nmt_translate → tts_synthesize → dubbing_merge
    """
    pipeline = chain(
        stt_transcribe.s(job_id, video_id, source_lang),
        nmt_translate.s(),
        tts_synthesize.s(),
        dubbing_merge.si(),
    )
    pipeline.apply_async()