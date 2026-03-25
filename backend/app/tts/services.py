"""
TTS Service — for TTS synthesis with Job tracking.

Async TTS:
  1. Creates a Job row (JobType.TTS_SYNTHESIZE)
  2. Dispatches synthesize_tts task to the ai_tts Celery queue
  3. Returns the job_id for polling
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobType, JobStatus
from app.jobs.schemas import JobCreate

logger = logging.getLogger(__name__)


class TTSService:
    """
    Service for TTS synthesis with Job tracking.
    
    Uses Habibi-TTS model to synthesize Arabic speech from translated text.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_tts(
        self,
        text: str,
        dialect: str = "MSA",
        job_id: Optional[str] = None,
        user_id: Optional[int] = None,
        video_id: Optional[int] = None,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        target_lang: str = "arb_Arab",
    ) -> str:
        """
        Submit TTS synthesis job.
        
        Creates a Job record in the database and dispatches a Celery task.
        
        Returns:
            job_id: The Job ID for polling status
        """
        from app.jobs.celery_app import synthesize_tts
        
        if not job_id:
            job_id = str(uuid.uuid4())
        
        # Generate ID for the Job record
        job_id = str(uuid.uuid4())
        
        job = Job(
            id=job_id,
            job_type=JobType.TTS_SYNTHESIZE,
            status=JobStatus.QUEUED,
            user_id=user_id,
            video_id=video_id,
            progress=0.0,
            input_data={
                "text": text,
                "dialect": dialect,
                "ref_audio_path": ref_audio_path,
                "ref_text": ref_text,
                "speed": speed,
                "cfg_strength": cfg_strength,
                "target_lang": target_lang,
            },
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(
            "[TTS Service] Created job %s for video_id=%s dialect=%s",
            job.id, video_id, dialect
        )
        
        result = synthesize_tts.apply_async(
            kwargs={
                "text": text,
                "dialect": dialect,
                "ref_audio_path": ref_audio_path,
                "ref_text": ref_text,
                "speed": speed,
                "cfg_strength": cfg_strength,
                "job_id": job.id,
            },
            queue="ai_tts",
            task_id=str(job.id),
        )
        
        logger.info(
            "[TTS Service] Dispatched TTS task %s for job %s",
            result.id, job.id
        )
        
        return job.id

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get job status by job_id."""
        from app.jobs.service import JobService
        job_service = JobService(self.db)
        job = await job_service.get_job(job_id)
        
        if not job:
            return None
        
        return {
            "job_id": job.id,
            "status": job.status.value,
            "video_id": job.video_id,
            "output_data": job.output_data,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_health(self) -> dict:
        """Get TTS service health status."""
        from app.config import settings
        from app.tts.models import HabibiTTSModelManager
        
        # Check if model manager has loaded models
        model_loaded = len(HabibiTTSModelManager._models) > 0
        device = "unknown"
        
        # Get device from the model manager
        try:
            # Try to instantiate and get device (lazy load)
            mgr = HabibiTTSModelManager()
            device = mgr.device
        except Exception:
            pass
        
        return {
            "status": "healthy" if model_loaded else "starting",
            "model_loaded": model_loaded,
            "device": device,
            "dialect": "MSA",
            "version": "1.0.0",
            "habibi_device": settings.HABIBI_DEVICE,
        }