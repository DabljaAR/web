"""
app/stt/models.py

WhisperModelManager extends celery.Task so that one model instance is held
per worker process and reused across every STT task invocation.

The model is loaded lazily via a @property — nothing loads at import time.
All original WhisperModelManager logic is unchanged.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

import torch
from celery import Task
from faster_whisper import WhisperModel

from app.config import settings
from app.shared.enums import AudioVideoExtension

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Strip and collapse whitespace in transcribed text."""
    return " ".join(text.split())


VALID_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    e.value for e in AudioVideoExtension
)

MAX_AUDIO_DURATION   = settings.STT_MAX_AUDIO_DURATION
MAX_RETRIES          = settings.STT_RETRY_ATTEMPTS
RETRY_DELAY          = settings.STT_RETRY_DELAY
GPU_MEMORY_THRESHOLD = settings.STT_GPU_MEMORY_THRESHOLD


# ===========================================================================
# WhisperModelManager — also the Celery base task
# ===========================================================================

class WhisperModelManager(Task):
    """
    Production-grade Whisper transcription manager.

    Extends celery.Task so `transcribe_task` (below) can use it as `base=`.
    One instance is kept per Celery worker process; the Whisper model inside
    it is loaded lazily on the first call to `transcribe()`.
    """

    abstract = True  # tells Celery: base class only, don't register as a task

    # Class-level holders so the model survives across task invocations
    _model: Optional[WhisperModel] = None
    _lock             = Lock()
    _is_transcribing  = False

    def __init__(self):
        # Resolve config — do NOT load the model here
        self.model_size    = settings.STT_MODEL_SIZE
        self._device       = None
        self._compute_type = None

        self.metrics = {
            "total_requests":            0,
            "successful_transcriptions": 0,
            "failed_transcriptions":     0,
            "total_processing_time":     0,
            "avg_processing_time":       0,
        }

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = settings.get_device()
        return self._device

    @property
    def compute_type(self) -> str:
        if self._compute_type is None:
            self._compute_type = settings.get_compute_type()
        return self._compute_type

    @property
    def model(self) -> WhisperModel:
        """Load the Whisper model once per worker process (lazy)."""
        if WhisperModelManager._model is None:
            logger.info(
                f"[STT] Loading Whisper | size={self.model_size} | "
                f"device={self.device} | compute_type={self.compute_type}"
            )
            try:
                WhisperModelManager._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                logger.info("✅ Whisper model loaded successfully")
            except Exception as e:
                logger.error(f"❌ Failed to load Whisper model: {e}")
                raise
        return WhisperModelManager._model

    # ------------------------------------------------------------------
    # Validation  (unchanged)
    # ------------------------------------------------------------------

    def _validate_audio_file(self, audio_path: str) -> None:
        path = Path(audio_path)

        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not os.access(audio_path, os.R_OK):
            raise PermissionError(f"Cannot read audio file: {audio_path}")

        max_size_gb  = settings.STT_MAX_FILE_SIZE_GB
        file_size_gb = path.stat().st_size / (1024 ** 3)
        if file_size_gb > max_size_gb:
            raise ValueError(
                f"File too large: {file_size_gb:.2f} GB (max {max_size_gb} GB)"
            )

        if path.suffix.lower() not in VALID_AUDIO_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {path.suffix}. "
                f"Supported: {VALID_AUDIO_EXTENSIONS}"
            )

    # ------------------------------------------------------------------
    # GPU helpers  (unchanged)
    # ------------------------------------------------------------------

    def _check_gpu_memory(self) -> bool:
        if self.device != "cuda":
            return True
        try:
            allocated = (
                torch.cuda.memory_allocated()
                / torch.cuda.get_device_properties(0).total_memory
            )
            if allocated > GPU_MEMORY_THRESHOLD:
                logger.warning(
                    f"GPU memory {allocated*100:.1f}% > "
                    f"threshold {GPU_MEMORY_THRESHOLD*100:.0f}%"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Could not check GPU memory: {e}")
            return True

    def _cleanup_gpu_memory(self) -> None:
        if self.device == "cuda":
            try:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public transcribe  (unchanged)
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs,
    ) -> dict:
        self._validate_audio_file(audio_path)

        if not self._check_gpu_memory():
            raise RuntimeError("Insufficient GPU memory. Please try again later.")

        with self._lock:
            if self._is_transcribing:
                raise RuntimeError(
                    "Transcription already in progress. Use async endpoint."
                )
            self._is_transcribing = True

        try:
            self.metrics["total_requests"] += 1
            return self._transcribe_with_retry(audio_path, language, **kwargs)
        finally:
            self._is_transcribing = False
            self._cleanup_gpu_memory()

    def _transcribe_with_retry(
        self,
        audio_path: str,
        language: Optional[str],
        **kwargs,
    ) -> dict:
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Transcription attempt {attempt + 1}/{MAX_RETRIES} | "
                    f"file={Path(audio_path).name}"
                )
                start_time = time.time()

                segments_generator, info = self.model.transcribe(
                    audio_path,
                    language=language,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 50},
                    **kwargs,
                )

                if info.duration > settings.STT_MAX_AUDIO_DURATION:
                    raise ValueError(
                        f"Audio too long: {info.duration:.0f}s "
                        f"(max {settings.STT_MAX_AUDIO_DURATION}s)"
                    )

                segments = list(segments_generator)
                structured_segments = [
                    {
                        "start": round(seg.start, 2),
                        "end":   round(seg.end,   2),
                        "text":  clean_text(seg.text),
                    }
                    for seg in segments
                ]

                transcript      = " ".join(s["text"] for s in structured_segments)
                processing_time = time.time() - start_time

                self.metrics["successful_transcriptions"] += 1
                self.metrics["total_processing_time"]     += processing_time
                self.metrics["avg_processing_time"]        = (
                    self.metrics["total_processing_time"]
                    / self.metrics["successful_transcriptions"]
                )

                result = {
                    "transcript": transcript,
                    "segments":   structured_segments,
                    "metadata": {
                        "language":        info.language,
                        "duration":        round(info.duration, 2),
                        "model_size":      self.model_size,
                        "device":          self.device,
                        "compute_type":    self.compute_type,
                        "processing_time": round(processing_time, 2),
                        "segment_count":   len(structured_segments),
                    },
                }

                logger.info(
                    f"✅ Transcription done | duration={info.duration:.1f}s | "
                    f"time={processing_time:.1f}s | "
                    f"speed={info.duration/processing_time:.2f}x"
                )
                return result

            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                last_exception = e
                logger.warning(f"GPU error attempt {attempt + 1}: {e}")
                self._cleanup_gpu_memory()
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)

            except Exception as e:
                logger.exception(f"Transcription failed: {e}")
                raise RuntimeError("STT inference failed") from e

        self.metrics["failed_transcriptions"] += 1
        raise RuntimeError(
            f"Transcription failed after {MAX_RETRIES} retries: {last_exception}"
        )

    # ------------------------------------------------------------------
    # Metrics / health / cleanup  (unchanged)
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        return {
            **self.metrics,
            "device":          self.device,
            "model_size":      self.model_size,
            "compute_type":    self.compute_type,
            "is_transcribing": self._is_transcribing,
        }

    def get_health(self) -> dict:
        return {
            "status":       "healthy",
            "model_loaded": WhisperModelManager._model is not None,
            "device":       self.device,
            "model_size":   self.model_size,
            "version":      "2.0.0",
        }

    def cleanup(self) -> None:
        try:
            self._cleanup_gpu_memory()
            logger.info("WhisperModelManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# ===========================================================================
# Celery task
# base=WhisperModelManager means `self` inside the task IS the manager,
# and the same instance (with the loaded model) is reused every invocation.
# ===========================================================================

from app.jobs.celery_app import celery_app  # noqa: E402


def _make_celery_db():
    """
    Build a sync engine + session for use inside Celery tasks.

    We intentionally use:
      - psycopg2 (sync driver) instead of asyncpg
      - NullPool so no connection is held between calls

    asyncpg binds connections to the event loop at the driver level.
    Even a fresh create_async_engine reuses the same asyncpg pool state
    when asyncio.run() is called repeatedly in the same Celery worker
    process, causing "another operation is in progress".

    Sync psycopg2 + NullPool has none of these constraints and is the
    correct choice for Celery workers.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.pool import NullPool
    from app.config import settings

    # Convert asyncpg URL → psycopg2 URL
    # e.g. postgresql+asyncpg://user:pass@host/db
    #   →  postgresql+psycopg2://user:pass@host/db
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql://", "postgresql+psycopg2://"
    )

    engine = create_engine(sync_url, poolclass=NullPool)
    factory = sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def _download_from_minio(storage, file_key: str, local_path: Path) -> Optional[Path]:
    """
    Download file_key from MinIO to local_path.
    Uses an isolated asyncio.run() — safe because it has no shared loop state.
    Returns None on success, or the resolved local path for local storage.
    """
    import asyncio as _asyncio
    from app.media.storage import S3StorageService

    if isinstance(storage, S3StorageService):
        async def _dl():
            async with storage.session.client(
                "s3",
                endpoint_url=storage.endpoint_url,
                aws_access_key_id=storage.access_key,
                aws_secret_access_key=storage.secret_key,
            ) as s3:
                await s3.download_file(storage.bucket_name, file_key, str(local_path))

        _asyncio.run(_dl())
        logger.info(f"[STT] Downloaded {file_key} → {local_path}")
        return None
    else:
        return Path(storage.get_absolute_path(file_key))


def _run_stt_job(
    task: "WhisperModelManager",
    job_id: str,
    file_key: str,
    language: Optional[str],
    target_lang: str = "arb_Arab",
) -> None:
    """
    Fully synchronous pipeline:
      - DB via psycopg2 + NullPool (no asyncpg, no event loop issues)
      - MinIO download via isolated asyncio.run() (no shared loop state)
      - Whisper blocking call directly (no executor needed in sync context)
      - After STT completes, dispatches each segment to NMT queue for translation
    """
    import tempfile
    from app.jobs.models import Job, JobStatus
    from app.media.models import Video 
    from app.media.storage import get_storage_service
    from app.jobs.tasks.nmt import nmt_translate_segment

    storage = get_storage_service()
    engine, SessionLocal = _make_celery_db()

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            logger.error(f"[STT] Job {job_id} not found — aborting.")
            engine.dispose()
            return

        # 1. PROCESSING
        job.status     = JobStatus.PROCESSING
        job.progress   = 0.0
        job.started_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                suffix     = Path(file_key).suffix or ".mp3"
                local_path = Path(tmp_dir) / f"audio{suffix}"

                # 2. Download from MinIO
                resolved = _download_from_minio(storage, file_key, local_path)
                if resolved is not None:
                    local_path = resolved  # local storage: use existing file path

                job.progress   = 20.0
                job.updated_at = datetime.utcnow()
                db.commit()

                # 3. Transcribe — direct blocking call (sync worker context)
                result = task.transcribe(str(local_path), language=language)

            # 4. Dispatch segments to NMT queue for parallel translation
            segments = result.get("segments", [])
            nmt_tasks_submitted = 0
            
            if segments:
                logger.info(f"[STT] Dispatching {len(segments)} segments to NMT queue for job {job_id}")
                for idx, segment in enumerate(segments):
                    nmt_translate_segment.apply_async(
                        kwargs={
                            "segment_id": idx,
                            "job_id": job_id,
                            "text": segment.get("text", ""),
                            "start": segment.get("start", 0.0),
                            "end": segment.get("end", 0.0),
                            "source_lang": language,
                            "target_lang": target_lang,
                        },
                        queue="ai_nmt"
                    )
                    nmt_tasks_submitted += 1
            
            result["nmt_tasks_submitted"] = nmt_tasks_submitted

            # 5. COMPLETED
            job.status       = JobStatus.COMPLETED
            job.progress     = 100.0
            job.output_data  = result
            job.completed_at = datetime.utcnow()
            job.updated_at   = datetime.utcnow()
            db.commit()

            logger.info(
                f"[STT] Job {job_id} completed | "
                f"duration={result['metadata'].get('duration')}s | "
                f"time={result['metadata'].get('processing_time')}s | "
                f"segments={len(segments)} | nmt_tasks={nmt_tasks_submitted}"
            )

        except Exception as exc:
            logger.exception(f"[STT] Job {job_id} failed: {exc}")
            job.status        = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at  = datetime.utcnow()
            job.updated_at    = datetime.utcnow()
            db.commit()
            raise
        finally:
            engine.dispose()



