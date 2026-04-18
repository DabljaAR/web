"""
TranscriptionService — updated to use MinIO + Celery job queue.

Sync transcription (transcribe_file) is unchanged — still runs in-process.
Async transcription (submit_async_transcription) now:
  1. Looks up the Video record for the supplied video_id
  2. Creates a Job row (JobType.STT_TRANSCRIBE)
  3. Dispatches ``stt_transcribe`` to the ai_stt Celery queue
  4. Returns the job_id for polling
"""

import logging
import uuid
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.jobs.models import Job, JobType, JobStatus
from app.jobs.schemas import JobCreate
from app.config import settings
from app.media.models import Video
from app.media.storage import get_storage_service
from app.stt.models import WhisperModelManager
from app.stt.schema import TranscriptionResponse, TranscriptionMetadata, TranscriptionSegment
from app.shared.processing_mode import resolve_processing_mode

logger = logging.getLogger(__name__)

# Temp dir for sync uploads
UPLOAD_DIR = Path(tempfile.gettempdir()) / "stt_uploads"

CHUNK_ELIGIBLE_OUTPUT_TYPES = {
    "captionsOnly",
    "captionsAndTranslation",
    "translationAndTTS",
    "fullDubbing",
}


class TranscriptionService:
    """
    STT service.

    - Direct (sync) transcription: used by the blocking /transcribe endpoint.
    - Async transcription: creates a Job + dispatches a Celery task.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_service()
        self._model_manager: Optional[WhisperModelManager] = None  # lazy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> WhisperModelManager:
        """Lazy-load the Whisper model (only for sync path)."""
        if self._model_manager is None:
            self._model_manager = WhisperModelManager()
        return self._model_manager

    @staticmethod
    def _save_upload_locally(file: UploadFile) -> Path:
        """Save UploadFile to a local temp path for in-process transcription."""
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_id = str(uuid.uuid4())
        tmp_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        content = file.file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
        return tmp_path

    @staticmethod
    def _build_response(raw: dict) -> TranscriptionResponse:
        """Convert raw WhisperModelManager result → Pydantic response."""
        meta = raw["metadata"]
        return TranscriptionResponse(
            transcript=raw["transcript"],
            segments=[TranscriptionSegment(**s) for s in raw["segments"]],
            metadata=TranscriptionMetadata(**meta),
        )

    # ------------------------------------------------------------------
    # Sync transcription (unchanged behaviour)
    # ------------------------------------------------------------------

    async def transcribe_file(
        self,
        file: UploadFile,
        language: Optional[str] = None,
    ) -> TranscriptionResponse:
        """
        Blocking transcription — runs Whisper in-process.
        Best for short files where an immediate response is acceptable.
        """
        tmp_path = self._save_upload_locally(file)
        try:
            raw = self._get_model().transcribe(str(tmp_path), language=language)
            return self._build_response(raw)
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Async transcription — Celery-backed
    # ------------------------------------------------------------------

    async def submit_async_transcription(
        self,
        file_key: str,
        user_id: int,
        language: Optional[str] = None,
        video_id: Optional[str] = None,
        target_lang: str = "arb_Arab",
    ) -> Job:
        """
        Create a Job record and dispatch the Celery STT task.

        Args:
            file_key:  MinIO object key of the audio/video file,
                       e.g. "audio/42/uuid.mp3".  The file must already
                       exist in MinIO — no upload happens here.
            user_id:   ID of the requesting user.
            language:  Optional ISO-639-1 language code; None = auto-detect.
            video_id:  Optional — link the job to a Video DB record.
                       Pass it when the file came from the media upload flow.
                       Omit it when referencing a MinIO key directly.
            target_lang: Target language for NMT translation (default: arb_Arab)

        Returns:
            The newly created Job ORM instance.
        """
        # If a video_id is provided, verify it exists and belongs to this user
        if video_id:
            from sqlalchemy import select
            result = await self.db.execute(select(Video).where(Video.id == video_id))
            video: Optional[Video] = result.scalar_one_or_none()
            if not video:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail=f"Video {video_id} not found.")
            if video.user_id != user_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Access denied.")
            # Prefer extracted audio track if available
            file_key = video.audio_path or video.file_path

        # 1. Check for existing active job first (prevent duplicates)
        existing_query = select(Job).where(
            Job.video_id == video_id,
            Job.job_type == JobType.STT_TRANSCRIBE,
            Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING])
        )
        existing_result = await self.db.execute(existing_query)
        existing_job = existing_result.scalars().first()
        
        if existing_job:
            logger.info(
                f"[STT] Found existing active job {existing_job.id} for video {video_id}, returning existing job"
            )
            return existing_job

        # 2. Create Job record
        # video_id is nullable on the Job model — fine to pass None
        output_type = "fullDubbing"
        processing_mode = (
            resolve_processing_mode(output_type)
        )
        job = Job(
            id=str(uuid.uuid4()),
            video_id=video_id,  # Use None if not provided (nullable in model)
            user_id=user_id,
            job_type=JobType.STT_TRANSCRIBE,
            status=JobStatus.QUEUED,
            progress=0.0,
            input_data={
                "video_id": video_id,
                "language": language,
                "target_lang": target_lang,
                "output_type": output_type,
                "processing_mode": processing_mode,
            },
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        # 3. Dispatch Celery task
        from app.jobs.tasks.pipeline import stt_transcribe
        celery_result = stt_transcribe.apply_async(
            kwargs={
                "job_id": job.id,
                "video_id": video_id,
                "language": language,
                "target_lang": target_lang,
            },
            task_id=job.id,
        )

        # 4. Persist Celery task id
        job.celery_task_id = celery_result.id
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            "[STT] Queued job %s | file_key=%s | language=%s | output_type=%s | processing_mode=%s",
            job.id,
            file_key,
            language,
            output_type,
            processing_mode,
        )
        return job

    # ------------------------------------------------------------------
    # Job status (reads from DB, not in-memory storage)
    # ------------------------------------------------------------------

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Fetch a Job row by id."""
        return await self.db.get(Job, job_id)

    # ------------------------------------------------------------------
    # Health / metrics (proxy to model manager if loaded)
    # ------------------------------------------------------------------

    def get_health(self) -> dict:
        manager = self._model_manager
        return {
            "status": "healthy",
            "model_loaded": manager is not None,
            "device": manager.device if manager else "unloaded",
            "model_size": manager.model_size if manager else "unloaded",
            "version": "2.0.0",
        }

    def get_metrics(self) -> dict:
        manager = self._model_manager
        if not manager:
            return {
                "total_requests": 0,
                "successful_transcriptions": 0,
                "failed_transcriptions": 0,
                "avg_processing_time": 0.0,
                "device": "unloaded",
                "model_size": "unloaded",
                "compute_type": "unloaded",
                "is_transcribing": False,
            }
        return manager.get_metrics()

    def cleanup(self) -> None:
        if self._model_manager:
            self._model_manager.cleanup()
        logger.info("TranscriptionService cleanup completed.")