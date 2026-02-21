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
    
    **Example:**
    ```
    curl -X POST http://localhost:8000/api/transcription/transcribe \\
      -F "file=@audio.mp3" \\
      -F "language=en"
    ```
    """,
    responses={
        200: {
            "description": "Transcription successful",
            "model": TranscriptionResponse
        },
        400: {
            "description": "Invalid file or parameters"
        },
        413: {
            "description": "File too large"
        },
        500: {
            "description": "Transcription failed"
        }
    }
)
async def transcribe_file(
    file: UploadFile = File(..., description="Audio/video file to transcribe"),
    language: Optional[str] = None,
):
    """
    Transcribe audio file synchronously.
    
    Args:
        file: Audio/video file (MP3, MP4, WAV, etc.)
        language: Optional language code (e.g., 'en', 'es', 'fr')
        
    Returns:
        Transcription result with segments and metadata
    """
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        logger.info(f"📥 Received file: {file.filename}")
        
        # Validate file type
        valid_extensions = {
            ".mp3", ".mp4", ".wav", ".m4a", ".flac",
            ".ogg", ".wma", ".aac", ".mov", ".mkv", ".webm"
        }
        file_ext = file.filename.lower().split('.')[-1]
        if f".{file_ext}" not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: .{file_ext}"
            )
        
        # Transcribe
        result = await service.transcribe_file(file, language)
        
        logger.info(f"✅ Transcription complete: {file.filename}")
        return result
        
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
    description="""
    Submit a file for async transcription.
    
    **Workflow:**
    1. POST file → Get task_id
    2. Poll GET /status/{task_id} → Check progress
    3. Get result when status is 'success'
    
    **Best for:** Large files or when you don't want to wait
    
    **Example:**
    ```
    # Submit job
    curl -X POST http://localhost:8000/api/transcription/transcribe-async \\
      -F "file=@video.mp4"
    
    # Check status
    curl http://localhost:8000/api/transcription/status/{task_id}
    ```
    """,
    responses={
        200: {
            "description": "Job submitted successfully",
            "model": AsyncJobResponse
        },
        400: {
            "description": "Invalid file"
        },
        500: {
            "description": "Failed to queue job"
        }
    }
)
async def submit_async_transcription(
    file: UploadFile = File(..., description="Audio/video file"),
    language: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Submit file for async transcription.
    
    Args:
        file: Audio/video file
        language: Optional language code
        background_tasks: FastAPI background task manager
        
    Returns:
        Task ID and status
    """
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Submit job
        result = await service.submit_async_transcription(file, language)
        
        # Process in background (optional - can use Celery instead)
        if background_tasks:
            background_tasks.add_task(
                service.process_async_transcription,
                result["task_id"]
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to submit async job: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue job")


@router.get(
    "/status/{task_id}",
    response_model=JobStatusResponse,
    summary="Check async job status",
    description="""
    Check the status of an async transcription job.
    
    **Status Values:**
    - `queued`: Waiting to start
    - `processing`: Currently transcribing
    - `success`: Completed (result available)
    - `failed`: Failed (check error field)
    
    **Example:**
    ```
    curl http://localhost:8000/api/transcription/status/550e8400-e29b-41d4-a716-446655440000
    ```
    """,
    responses={
        200: {
            "description": "Job status",
            "model": JobStatusResponse
        },
        404: {
            "description": "Task not found"
        }
    }
)
async def get_job_status(
    task_id: str = "Task ID from /transcribe-async response",
):
    """
    Get status of async transcription job.
    
    Args:
        task_id: Task ID from submission response
        
    Returns:
        Job status and result (if ready)
    """
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        job = service.get_job_status(task_id)
        
        # Convert result dict to response model if available
        if job["result"]:
            job["result"] = TranscriptionResponse(**job["result"])
        
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
    """Cancel an async job."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        job = service.get_job_status(task_id)
        
        if job["status"] in ["success", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status: {job['status']}"
            )
        
        # Update status
        job["status"] = "cancelled"
        
        logger.info(f"🛑 Job cancelled: {task_id}")
        
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Job has been cancelled"
        }
        
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
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    if not service:
        return {
            "status": "unhealthy",
            "model_loaded": False,
            "device": "unknown",
            "version": "1.0.0"
        }
    
    return service.get_health()


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Performance metrics",
    description="Get API performance metrics and statistics",
)
async def get_metrics():
    """
    Get performance metrics.
    
    Returns:
        Performance statistics
    """
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
    """
    Get API information.
    
    Returns:
        API version and endpoints
    """
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


# ==================== HELLO ENDPOINT ====================

@router.get(
    "/",
    summary="API root",
    description="API is running",
)
async def root():
    """API root endpoint."""
    return {
        "message": "Speech-to-Text API is running",
        "docs": "/docs",
        "info": "/api/transcription/info"
    }