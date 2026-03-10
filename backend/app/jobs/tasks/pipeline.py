"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.
"""
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Transcribe the audio track of *video_id*.

    Downloads the file from MinIO, runs Whisper via the shared
    ``transcribe_task`` model instance (loaded once per worker), then
    stores the result in the Job row.

    As segments are transcribed, they are immediately dispatched to the
    NMT queue for parallel translation (chunked processing).

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript_key": None,          # raw file unchanged in storage
            "transcript":     str,           # full text
            "segments":       list[dict],    # [{start, end, text}, ...]
            "metadata":       dict,
            "nmt_tasks_submitted": int,      # number of NMT tasks dispatched
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager
    from app.jobs.tasks.nmt import nmt_translate_segment

    whisper = WhisperModelManager()
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
        # Whisper yields segments progressively, so we dispatch each segment
        # to NMT queue as soon as it's available (chunked processing)
        import time
        structured_segments = []
        nmt_tasks_submitted = 0
        transcript_parts = []

        try:
            start_time = time.time()
            segments_generator, info = whisper.model.transcribe(
                str(local_path),
                language=language,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 50},
            )

            if info.duration > 3600:
                raise ValueError(f"Audio too long: {info.duration:.0f}s (max 3600s)")

            logger.info(f"[STT] Starting transcription | duration={info.duration:.1f}s | job={job_id}")

            for seg in segments_generator:
                segment_dict = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

                if segment_dict["text"].strip():
                    nmt_translate_segment.apply_async(
                        kwargs={
                            "segment_id": len(structured_segments) - 1,
                            "job_id": job_id,
                            "text": segment_dict["text"],
                            "start": segment_dict["start"],
                            "end": segment_dict["end"],
                            "source_lang": language,
                            "target_lang": target_lang,
                        },
                        queue="ai_nmt"
                    )
                    nmt_tasks_submitted += 1
                    logger.debug(f"[STT] Dispatched segment {len(structured_segments)-1} to NMT | job={job_id}")

                self.update_progress(job_id, 25.0 + (60.0 * len(structured_segments) / max(info.duration, 1)))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            result = {
                "transcript": full_transcript,
                "segments": structured_segments,
                "metadata": {
                    "language": info.language,
                    "duration": round(info.duration, 2),
                    "model_size": whisper.model_size,
                    "device": whisper.device,
                    "compute_type": whisper.compute_type,
                    "processing_time": round(processing_time, 2),
                    "segment_count": len(structured_segments),
                },
            }

        except Exception as exc:
            logger.error("[STT pipeline] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 90.0)

        # ── 5. Persist output_data — on_success hook will set COMPLETED ──────────
        output = {
            "job_id":         job_id,
            "video_id":       video_id,
            "transcript_key": file_key,
            "transcript":     result["transcript"],
            "segments":       result["segments"],
            "metadata":       result["metadata"],
            "nmt_tasks_submitted": nmt_tasks_submitted,
        }

        self._run_sync(
            self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
        )

        logger.info(
            "[STT pipeline] job=%s done | duration=%.1fs | segments=%d | nmt_tasks=%d",
            job_id,
            result["metadata"].get("duration", 0),
            result["metadata"].get("segment_count", 0),
            nmt_tasks_submitted,
        )

        return output


# ===========================================================================
# Neural Machine Translation
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.nmt_translate",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
)
def nmt_translate(
    self,
    job_id: str,
    video_id: str,
    transcript_key: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> dict:
    """
    Stub: translate the transcript produced by ``stt_transcribe``.

    Returns:
        {"job_id": job_id, "video_id": video_id, "translation_key": "<storage_key>"}
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call NMT service
    logger.info(
        "[STUB] nmt_translate job=%s video=%s %s→%s",
        job_id, video_id, source_lang, target_lang,
    )
    return {"job_id": job_id, "video_id": video_id, "translation_key": None}


# ===========================================================================
# Text-to-Speech
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.tts_synthesize",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_tts",
)
def tts_synthesize(
    self,
    job_id: str,
    video_id: str,
    translation_key: str,
    target_lang: str = "en",
) -> dict:
    """
    Stub: synthesise speech from the translated text.

    Returns:
        {"job_id": job_id, "video_id": video_id, "audio_key": "<storage_key>"}
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call TTS service
    logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)
    return {"job_id": job_id, "video_id": video_id, "audio_key": None}


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