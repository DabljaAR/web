"""
FastAPI router for Speech-to-Text API endpoints.
Location: sst/router.py
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import Optional

from app.stt.schema import (
    TranscriptionResponse,
    TranscriptionRequest,
    AsyncJobResponse,
    JobStatusResponse,
    MetricsResponse,
    HealthCheckResponse,
    ErrorResponse,
)
from app.stt.services import TranscriptionService

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/transcription",
    tags=["transcription"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)

# Service instance (initialized in main.py)
service: TranscriptionService = None


def set_service(svc: TranscriptionService) -> None:
    """Set service instance (call from main.py on startup)."""
    global service
    service = svc


# ==================== SYNC TRANSCRIPTION ====================

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Synchronous transcription",
    description="""
    Upload an audio/video file and get transcription immediately.
    
    **File Support:**
    - Format: MP3, MP4, WAV, M4A, FLAC, OGG, WMA, AAC
    - Max Size: 5GB
    - Max Duration: 1 hour (3600 seconds)
    
    **Best for:** Files < 10 minutes (quick turnaround)
    """,
    responses={
        200: {"description": "Transcription successful", "model": TranscriptionResponse},
        400: {"description": "Invalid file or parameters"},
        413: {"description": "File too large"},
        500: {"description": "Transcription failed"}
    }
)
async def transcribe_file(
    file: UploadFile = File(..., description="Audio/video file to transcribe"),
    language: Optional[str] = None,
):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        logger.info(f"📥 Received file: {file.filename}")

        # Validate file type
        valid_extensions = {
            ".mp3", ".mp4", ".wav", ".m4a", ".flac",
            ".ogg", ".wma", ".aac", ".mov", ".mkv", ".webm"
        }
        file_ext = "." + file.filename.lower().rsplit(".", 1)[-1]
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_ext}"
            )

        result = await service.transcribe_file(file, language)
        logger.info(f"✅ Transcription complete: {file.filename}")
        return result

    except HTTPException:
        # Re-raise HTTPExceptions as-is (don't swallow 400s as 500s)
        raise

    except FileNotFoundError as e:
        logger.warning(f"File error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== ASYNC TRANSCRIPTION ====================

@router.post(
    "/transcribe-async",
    response_model=AsyncJobResponse,
    summary="Asynchronous transcription",
    responses={
        200: {"description": "Job submitted successfully", "model": AsyncJobResponse},
        400: {"description": "Invalid file"},
        500: {"description": "Failed to queue job"}
    }
)
async def submit_async_transcription(
    file: UploadFile = File(..., description="Audio/video file"),
    language: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await service.submit_async_transcription(file, language)

        if background_tasks:
            background_tasks.add_task(
                service.process_async_transcription,
                result["task_id"]
            )

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to submit async job: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue job")


@router.get(
    "/status/{task_id}",
    response_model=JobStatusResponse,
    summary="Check async job status",
    responses={
        200: {"description": "Job status", "model": JobStatusResponse},
        404: {"description": "Task not found"}
    }
)
async def get_job_status(task_id: str):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        job = service.get_job_status(task_id)

        # Convert result dict to TranscriptionResponse only if it has required fields
        if job.get("result") and isinstance(job["result"], dict):
            result_data = job["result"]
            # Only attempt conversion if metadata is populated
            metadata = result_data.get("metadata", {})
            if metadata and all(k in metadata for k in [
                "language", "duration", "model_size", "device",
                "processing_time", "segment_count"
            ]):
                job["result"] = TranscriptionResponse(**result_data)
            else:
                job["result"] = None

        return JobStatusResponse(**job)

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    except Exception as e:
        logger.error(f"Error checking status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check status")


@router.delete(
    "/cancel/{task_id}",
    summary="Cancel async job",
    description="Cancel a queued or running transcription job",
)
async def cancel_job(task_id: str):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        job = service.get_job_status(task_id)

        if job["status"] in ["success", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status: {job['status']}"
            )

        job["status"] = "cancelled"
        logger.info(f"🛑 Job cancelled: {task_id}")

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Job has been cancelled"
        }

    except HTTPException:
        raise

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")


# ==================== HEALTH & MONITORING ====================

@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check",
    description="Check API and model status",
)
async def health_check():
    # FIX: return 503 when service is not initialized instead of 200/unhealthy
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return service.get_health()


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Performance metrics",
    description="Get API performance metrics and statistics",
)
async def get_metrics():
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    metrics = service.get_metrics()
    return MetricsResponse(**metrics)


# ==================== API INFO ====================

@router.get(
    "/info",
    summary="API information",
    description="Get API information and available endpoints",
)
async def api_info():
    return {
        "name": "Speech-to-Text API",
        "version": "1.0.0",
        "description": "Fast and accurate speech-to-text transcription",
        "model": "Faster-Whisper",
        "endpoints": {
            "POST /transcribe": "Sync transcription (blocking)",
            "POST /transcribe-async": "Async transcription (non-blocking)",
            "GET /status/{task_id}": "Check async job status",
            "DELETE /cancel/{task_id}": "Cancel async job",
            "GET /health": "Health check",
            "GET /metrics": "Performance metrics",
            "GET /info": "API information",
        },
        "docs": "/docs",
        "openapi": "/openapi.json"
    }


# ==================== ROOT ====================

@router.get(
    "/",
    summary="API root",
    description="API is running",
)
async def root():
    return {
        "message": "Speech-to-Text API is running",
        "docs": "/docs",
        "info": "/api/transcription/info"
    }