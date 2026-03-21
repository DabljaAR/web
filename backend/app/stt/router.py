"""
FastAPI router for Speech-to-Text endpoints.

Sync endpoint  → /transcribe         (file upload, immediate response)
Async endpoint → /transcribe-async   (video_id in MinIO, returns job_id)
Status         → /jobs/{job_id}      (polls Job table)
Cancel         → /jobs/{job_id}      DELETE
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user          # your existing auth dep
from app.jobs.models import Job, JobStatus
from app.stt.schema import (
    AsyncJobResponse,
    ErrorResponse,
    HealthCheckResponse,
    JobStatusResponse,
    MetricsResponse,
    TranscriptionResponse,
)
from app.shared.enums import AudioVideoExtension
from app.stt.services import TranscriptionService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/transcription",
    tags=["transcription"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)

# ---------------------------------------------------------------------------
# Dependency — fresh service per request (carries the request-scoped DB session)
# ---------------------------------------------------------------------------

def get_stt_service(db: AsyncSession = Depends(get_db)) -> TranscriptionService:
    return TranscriptionService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_valid_audio(file: UploadFile) -> None:
    filename = file.filename or ""
    # Extract extension: "track.MP3" -> ".mp3"
    ext = f".{filename.lower().rsplit('.', 1)[-1]}"
    
    if not AudioVideoExtension.has_value(ext):
        allowed = ", ".join([e.value for e in AudioVideoExtension])
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported format: {ext}. Supported formats are: {allowed}"
        )


def _job_to_response(job: Job) -> JobStatusResponse:
    """Map a Job ORM row to the JobStatusResponse schema."""
    result = None
    if job.status == JobStatus.COMPLETED and job.output_data:
        try:
            result = TranscriptionResponse(**job.output_data)
        except Exception as e:
            logger.warning(f"Could not parse output_data for job {job.id}: {e}")

    return JobStatusResponse(
        task_id=job.id,
        status=job.status.value.lower(),
        result=result,
        error=job.error_message,
        progress={"percent": job.progress} if job.progress is not None else None,
    )


# ===========================================================================
# SYNC TRANSCRIPTION  —  unchanged behaviour, no Job record created
# ===========================================================================

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Synchronous transcription (blocking)",
    description="""
Upload an audio/video file and receive the transcript immediately.

**Best for:** files < 10 minutes.  
**Formats:** MP3, MP4, WAV, M4A, FLAC, OGG, WMA, AAC, MOV, MKV, WEBM  
**Max size:** 5 GB | **Max duration:** 1 hour
""",
)
async def transcribe_sync(
    file: UploadFile = File(..., description="Audio/video file"),
    language: Optional[str] = Query(default=None, description="ISO-639-1 code, e.g. 'en'"),
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    _assert_valid_audio(file)
    try:
        return await svc.transcribe_file(file, language)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error(f"Sync transcription error: {exc}")
        raise HTTPException(status_code=500, detail="Transcription failed.")
    except Exception as exc:
        logger.exception(f"Unexpected sync transcription error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error.")


# ===========================================================================
# ASYNC TRANSCRIPTION  —  Celery-backed, requires an uploaded video/audio
# ===========================================================================

@router.post(
    "/transcribe-async",
    response_model=AsyncJobResponse,
    summary="Asynchronous transcription (Celery)",
    description="""
Queue an STT job for a file already stored in MinIO.

**Option A — direct MinIO key** (works for any file in MinIO):
Pass `file_key`, e.g. `audio/42/uuid.mp3`.

**Option B — video record** (file was uploaded via `/api/videos/upload`):
Pass `video_id` instead. The service will resolve the key from the DB
and prefer the extracted `audio_path` over the raw `file_path`.

Returns a `job_id` to poll at `GET /api/transcription/jobs/{job_id}`.
""",
)
async def transcribe_async(
    file_key: Optional[str] = Query(default=None, description="MinIO object key, e.g. 'audio/42/uuid.mp3'"),
    video_id: Optional[str] = Query(default=None, description="UUID of an existing Video/Audio DB record"),
    language: Optional[str] = Query(default=None, description="ISO-639-1 code, e.g. 'ar'. None = auto-detect"),
    target_lang: Optional[str] = Query(default="arb_Arab", description="Target language for NMT translation, e.g. 'arb_Arab'"),
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    if not file_key and not video_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file_key' (MinIO object key) or 'video_id'."
        )

    job: Job = await svc.submit_async_transcription(
        file_key=file_key or "",
        user_id=current_user.user_id,
        language=language,
        video_id=video_id,
        target_lang=target_lang,
    )

    return AsyncJobResponse(
        task_id=job.id,
        status=job.status.value.lower(),
        message=f"STT job queued. Poll status at /api/transcription/jobs/{job.id}",
    )


# ===========================================================================
# JOB STATUS  —  reads Job table
# ===========================================================================

@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll async job status",
    responses={404: {"description": "Job not found"}},
)
async def get_job_status(
    job_id: str,
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    job: Optional[Job] = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return _job_to_response(job)


# ===========================================================================
# CANCEL JOB
# ===========================================================================

@router.delete(
    "/jobs/{job_id}",
    summary="Cancel a queued or running STT job",
    responses={
        404: {"description": "Job not found"},
        400: {"description": "Job already finished"},
    },
)
async def cancel_job(
    job_id: str,
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    job: Optional[Job] = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status.value}'.",
        )

    # Revoke Celery task if it has one
    if job.celery_task_id:
        from app.jobs.celery_app import celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")

    job.status = JobStatus.CANCELLED
    job.updated_at = __import__("datetime").datetime.utcnow()
    await svc.db.commit()

    logger.info(f"[STT] Job {job_id} cancelled by user {current_user.user_id}")
    return {"job_id": job_id, "status": "cancelled", "message": "Job has been cancelled."}


# ===========================================================================
# HEALTH & METRICS
# ===========================================================================

@router.get("/health", response_model=HealthCheckResponse, summary="Health check" )
async def health_check(svc: TranscriptionService = Depends(get_stt_service) , current_user=Depends(get_current_user),):
    return svc.get_health()


@router.get("/metrics", response_model=MetricsResponse, summary="Performance metrics")
async def get_metrics(
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    return MetricsResponse(**svc.get_metrics())


# ===========================================================================
# INFO
# ===========================================================================

@router.get("/info", summary="API information")
async def api_info(current_user=Depends(get_current_user),):
    return {
        "name": "Speech-to-Text API",
        "version": "2.0.0",
        "backend": "Faster-Whisper + Celery (ai_stt queue)",
        "endpoints": {
            "POST /transcribe":            "Sync transcription (blocking, file upload)",
            "POST /transcribe-async":      "Async transcription (video_id in MinIO)",
            "GET  /jobs/{job_id}":         "Poll async job status",
            "DELETE /jobs/{job_id}":       "Cancel async job",
            "GET  /health":                "Health check",
            "GET  /metrics":               "Performance metrics",
        },
    }