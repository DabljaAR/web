"""TTS FastAPI router for Habibi-TTS synthesis."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.tts.services import TTSService
from app.tts.schema import (
    TTSRequest,
    TTSResponse,
    TTSStatusResponse,
    TTSJobResponse,
    TTSErrorResponse,
    ArabicDialect,
    TTSHealthResponse,
)
from app.jobs.celery_app import celery_app
from app.jobs.service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["TTS"])


def get_tts_service(db: AsyncSession = Depends(get_db)) -> TTSService:
    return TTSService(db)


@router.post("/synthesize", response_model=TTSResponse)
async def synthesize(
    req: TTSRequest,
    current_user = Depends(get_current_user),
    svc: TTSService = Depends(get_tts_service),
):
    """
    Trigger TTS synthesis with Job tracking.
    
    Creates a Job record and dispatches Celery task.
    """
    if req.dialect.upper() not in ("MSA", "EGY"):
        raise HTTPException(400, f"Unknown dialect '{req.dialect}'. Use MSA or EGY.")

    try:
        job_id = await svc.submit_tts(
            text=req.text,
            dialect=req.dialect,
            job_id=req.job_id,
            user_id=current_user.user_id,
            ref_audio_path=req.ref_audio_path,
            ref_text=req.ref_text,
            speed=req.speed,
            cfg_strength=req.cfg_strength,
            upload_to_minio=req.upload_to_minio,
            minio_key=req.minio_key,
        )
        
        return TTSResponse(task_id=job_id, status="queued")
    
    except Exception as e:
        logger.error("[TTS] Failed to submit synthesis: %s", e)
        raise HTTPException(500, f"Failed to submit TTS job: {str(e)}")


@router.get("/status/{task_id}", response_model=TTSStatusResponse)
async def task_status(task_id: str):
    """Get TTS task status from Celery."""
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=celery_app)
    return TTSStatusResponse(
        task_id=task_id,
        status=result.status,
        result=result.result if result.ready() else None,
        info=str(result.info) if result.info else None,
    )


@router.get("/jobs/{job_id}", response_model=TTSJobResponse)
async def get_job(
    job_id: str,
    svc: TTSService = Depends(get_tts_service),
):
    """Get TTS job status from database."""
    job_data = await svc.get_job_status(job_id)
    
    if not job_data:
        raise HTTPException(404, f"Job {job_id} not found")
    
    return TTSJobResponse(
        job_id=job_data["job_id"],
        status=job_data["status"],
        video_id=job_data.get("video_id"),
        output_key=job_data.get("output_data", {}).get("output_path") if job_data.get("output_data") else None,
        error=job_data.get("error_message"),
        created_at=job_data.get("created_at"),
        completed_at=job_data.get("completed_at"),
    )


@router.get("/health", response_model=TTSHealthResponse, summary="Health check")
async def health_check(svc: TTSService = Depends(get_tts_service)):
    """Get TTS service health status."""
    return TTSHealthResponse(**svc.get_health())