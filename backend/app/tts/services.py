"""
TTS Service — for TTS synthesis with Job tracking.

Uses SILMA-TTS model for high-quality Arabic speech synthesis.

Async TTS:
  1. Creates a Job row (JobType.TTS_SYNTHESIZE)
  2. Dispatches synthesize_tts task to the ai_tts Celery queue
  3. Returns the job_id for polling
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobType, JobStatus

logger = logging.getLogger(__name__)


class TTSService:
    """
    Service for TTS synthesis with Job tracking.
    
    Uses SILMA-TTS model to synthesize Arabic speech from translated text.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_tts(
        self,
        text: str,
        job_id: Optional[str] = None,
        user_id: Optional[int] = None,
        video_id: Optional[int] = None,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        nfe_step: Optional[int] = None,
        sway_sampling_coef: Optional[float] = None,
        target_rms: Optional[float] = None,
        seed: Optional[int] = None,
        target_lang: str = "arb_Arab",
        upload_to_minio: bool = False,
        minio_key: Optional[str] = None,
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
        
        job = Job(
            id=job_id,
            job_type=JobType.TTS_SYNTHESIZE,
            status=JobStatus.QUEUED,
            user_id=user_id,
            video_id=video_id,
            progress=0.0,
            input_data={
                "text": text,
                "ref_audio_path": ref_audio_path,
                "ref_text": ref_text,
                "speed": speed,
                "cfg_strength": cfg_strength,
                "nfe_step": nfe_step,
                "sway_sampling_coef": sway_sampling_coef,
                "target_rms": target_rms,
                "target_lang": target_lang,
                "upload_to_minio": upload_to_minio,
                "minio_key": minio_key,
            },
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(
            "[TTS Service] Created job %s for video_id=%s",
            job.id, video_id
        )
        
        result = synthesize_tts.apply_async(
            kwargs={
                "text": text,
                "ref_audio_path": ref_audio_path,
                "ref_text": ref_text,
                "speed": speed,
                "cfg_strength": cfg_strength,
                "nfe_step": nfe_step,
                "sway_sampling_coef": sway_sampling_coef,
                "target_rms": target_rms,
                "seed": seed,
                "job_id": job.id,
                "upload_to_minio": upload_to_minio,
                "minio_key": minio_key,
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
        from app.tts.models import SilmaTTSModelManager
        
        # Check if model manager has loaded model
        model_loaded = SilmaTTSModelManager._model is not None
        device = "unknown"
        
        # Get device from the model manager
        try:
            # Try to instantiate and get device (lazy load)
            mgr = SilmaTTSModelManager()
            device = mgr.device
        except Exception:
            pass
        
        return {
            "status": "healthy" if model_loaded else "starting",
            "model_loaded": model_loaded,
            "device": device,
            "model": "SILMA-TTS",
            "version": "1.0.0",
            "silma_device": settings.SILMA_DEVICE,
        }