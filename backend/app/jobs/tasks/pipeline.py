"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.

Pipeline flow (each stage is independent — reads input from DB, writes output to DB):
  stt_transcribe  →  nmt_translate  →  tts_pipeline
"""
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus, JobType

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

    Downloads the file from MinIO, runs Whisper, stores the result in the
    Job row, then creates one NMT job and dispatches nmt_translate.

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript":     str,
            "segments":       list[dict],   # [{start, end, text}, ...]
            "metadata":       dict,
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING ───────────────────────────────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── Read output_type from this job's input_data ──────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            from app.jobs.models import Job as _Job
            stt_job_row = db.get(_Job, job_id)
            _input_data = dict(stt_job_row.input_data) if stt_job_row and stt_job_row.input_data else {}
    finally:
        engine.dispose()
    output_type = _input_data.get("output_type", "fullDubbing")
    task_id     = _input_data.get("task_id")

    # ── 2. Resolve the MinIO key ─────────────────────────────────────────────
    async def _get_file_key() -> str:
        from app.core.db import AsyncSessionLocal
        from app.media.models import Video
        async with AsyncSessionLocal() as db:
            video = await db.get(Video, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found.")
            return video.audio_path or video.file_path

    file_key: str = self._run_sync(_get_file_key())
    logger.info("[STT] job=%s video=%s file_key=%s", job_id, video_id, file_key)

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
            logger.info("[STT] downloaded %s → %s", file_key, local_path)
        else:
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe ────────────────────────────────────────────────────
        structured_segments = []
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

            logger.info("[STT] Starting transcription | duration=%.1fs | job=%s", info.duration, job_id)

            for seg in segments_generator:
                segment_dict = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

                current_time = segment_dict["end"]
                progress = 25.0 + (65.0 * current_time / max(info.duration, 0.1))
                self.update_progress(job_id, min(progress, 90.0))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            metadata = {
                "language": info.language,
                "duration": round(info.duration, 2),
                "model_size": whisper.model_size,
                "device": whisper.device,
                "compute_type": whisper.compute_type,
                "processing_time": round(processing_time, 2),
                "segment_count": len(structured_segments),
            }

        except Exception as exc:
            logger.error("[STT] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 90.0)

        output = {
            "job_id":     job_id,
            "video_id":   video_id,
            "transcript": full_transcript,
            "segments":   structured_segments,
            "metadata":   metadata,
        }

        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

        # ── 5. Write STT result to VideoTask ─────────────────────────────────
        if task_id:
            from app.tasks.models import TaskStatus
            captions_only = output_type == "captionsOnly"
            self._patch_task(
                task_id,
                TaskStatus.COMPLETED if captions_only else TaskStatus.PROCESSING,
                transcript=full_transcript,
                stt_metadata=metadata,
                progress=100.0 if captions_only else 10.0,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow() if captions_only else None,
            )

        # ── 6. Conditionally dispatch NMT based on output_type ───────────────
        NMT_REQUIRED = {"captionsAndTranslation", "translationAndTTS", "fullDubbing"}
        if structured_segments and output_type in NMT_REQUIRED:
            from app.jobs.tasks.nmt import nmt_translate

            nmt_job_id = self._create_next_job(
                job_id,
                JobType.NMT_TRANSLATE,
                input_data={
                    "task_id":    task_id,
                    "source_lang": language or "auto",
                    "target_lang": target_lang,
                    "output_type": output_type,
                },
            )
            nmt_translate.apply_async(args=[nmt_job_id], queue="ai_nmt")
            logger.info("[STT] NMT job %s dispatched | job=%s | segments=%d | output_type=%s",
                        nmt_job_id, job_id, len(structured_segments), output_type)
        else:
            if structured_segments:
                logger.info("[STT] output_type=%s — skipping NMT/TTS | job=%s", output_type, job_id)
            else:
                logger.info("[STT] No segments to translate; pipeline ends here | job=%s", job_id)

        logger.info(
            "[STT] done | job=%s | duration=%.1fs | segments=%d",
            job_id, metadata.get("duration", 0), metadata.get("segment_count", 0),
        )

        return output


# ===========================================================================
# Text-to-Speech pipeline stage
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.tts_pipeline",
    max_retries=2,
    default_retry_delay=30,
    queue="ai_tts",
)
def tts_pipeline(self, job_id: str) -> dict:
    """
    TTS pipeline stage.

    Reads translated segments from the parent NMT Job, synthesizes each one
    via Habibi-TTS, uploads WAV files to MinIO, and writes a combined result
    into this Job's output_data.

    Returns:
        {
            "job_id":    str,
            "video_id":  str,
            "segments":  list[dict],  # [{..., "tts_key": "tts/vid/seg_N.wav", "audio_url": ...}]
            "metadata":  dict,
        }
    """
    from app.jobs.celery_app import synthesize_tts
    from app.jobs.models import Job

    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 1. Load NMT output from parent job ───────────────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            tts_job = db.get(Job, job_id)
            if not tts_job:
                raise ValueError(f"TTS job {job_id} not found")
            parent = db.get(Job, tts_job.parent_job_id) if tts_job.parent_job_id else None
            if not parent or not parent.output_data:
                raise ValueError(f"TTS job {job_id} has no parent NMT output")
            nmt_output = dict(parent.output_data)
            video_id = tts_job.video_id
            tts_input = dict(tts_job.input_data or {})
    finally:
        engine.dispose()

    task_id = tts_input.get("task_id")

    segments: list = nmt_output.get("segments", [])
    metadata: dict = nmt_output.get("metadata", {})

    logger.info("[TTS] job=%s video=%s segments=%d", job_id, video_id, len(segments))

    # ── 2. Synthesize each segment ───────────────────────────────────────────
    result_segments = []
    for idx, seg in enumerate(segments):
        text = seg.get("translated_text") or seg.get("text", "")
        if not text.strip():
            result_segments.append({**seg, "tts_key": None, "audio_url": None})
            continue

        minio_key = f"tts/{video_id}/segment_{idx}.wav"
        try:
            tts_result = synthesize_tts.apply_async(
                kwargs={
                    "text": text,
                    "dialect": "MSA",
                    "job_id": f"{job_id}_seg_{idx}",
                    "upload_to_minio": True,
                    "minio_key": minio_key,
                },
                queue="ai_tts",
            ).get(timeout=300)  # wait per-segment (TTS worker is co-located)
            result_segments.append({
                **seg,
                "tts_key": tts_result.get("minio_key"),
                "audio_url": tts_result.get("audio_url"),
            })
            logger.debug("[TTS] segment %d synthesized | job=%s", idx, job_id)
        except Exception as exc:
            logger.error("[TTS] segment %d failed | job=%s: %s", idx, job_id, exc)
            result_segments.append({**seg, "tts_key": None, "audio_url": None, "tts_error": str(exc)})

        progress = 10.0 + (85.0 * (idx + 1) / max(len(segments), 1))
        self.update_progress(job_id, min(progress, 95.0))

    output = {
        "job_id":   job_id,
        "video_id": video_id,
        "segments": result_segments,
        "metadata": {**metadata, "tts_segments": len(result_segments)},
    }
    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

    # ── Write final merged result to VideoTask and mark COMPLETED ────────────
    if task_id:
        from app.tasks.models import TaskStatus
        self._patch_task(
            task_id,
            TaskStatus.COMPLETED,
            segments=result_segments,
            progress=100.0,
            completed_at=datetime.utcnow(),
        )

    logger.info("[TTS] done | job=%s | segments=%d", job_id, len(result_segments))
    return output


# ===========================================================================
# Stubs kept for compatibility
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
    translation_key: Optional[str] = None,
    target_lang: str = "en",
) -> dict:
    """Legacy stub — use tts_pipeline for the pipeline flow."""
    if isinstance(job_id, dict):
        video_id = job_id.get("video_id")
        job_id = job_id.get("job_id")
    self._patch_job(job_id, JobStatus.PROCESSING, celery_task_id=self.request.id, started_at=datetime.utcnow())
    logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)
    output = {"job_id": job_id, "video_id": video_id, "audio_key": None}
    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
    return output


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.dubbing_merge",
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
)
def dubbing_merge(self, job_id: str, video_id: str, audio_key: str) -> dict:
    """Stub: merge synthesised audio with the original video."""
    self._patch_job(job_id, JobStatus.PROCESSING, celery_task_id=self.request.id, started_at=datetime.utcnow())
    logger.info("[STUB] dubbing_merge job=%s video=%s", job_id, video_id)
    return {"job_id": job_id, "video_id": video_id, "output_key": None}
