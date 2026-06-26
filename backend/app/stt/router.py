"""FastAPI router for Speech-to-Text endpoints.

All heavy lifting is done by the STT microservice.
This router is a thin facade: it validates requests and delegates to
the stt-service via HTTP (sync) or RabbitMQ/orchestrator (async).

Sync endpoint  → POST /transcribe        (file upload → immediate result)
Async endpoint → POST /transcribe-async  (creates Job, orchestrator dispatches)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.stt.schema import AsyncJobResponse, TranscriptionResponse
from app.shared.enums import AudioVideoExtension
from app.stt.services import TranscriptionService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/transcription",
    tags=["transcription"],
)


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_stt_service(db: AsyncSession = Depends(get_db)) -> TranscriptionService:
    return TranscriptionService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_valid_audio(file: UploadFile) -> None:
    filename = file.filename or ""
    ext = f".{filename.lower().rsplit('.', 1)[-1]}"
    if not AudioVideoExtension.has_value(ext):
        allowed = ", ".join(e.value for e in AudioVideoExtension)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Supported: {allowed}",
        )


# ===========================================================================
# SYNC TRANSCRIPTION  —  proxied to STT microservice
# ===========================================================================

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Synchronous transcription (blocking)",
    description="""
Upload an audio/video file and receive the transcript immediately.

The request is forwarded to the **STT microservice** which runs Faster-Whisper.

**Best for:** files < 10 minutes.
**Formats:** MP3, MP4, WAV, M4A, FLAC, OGG, WMA, AAC, MOV, MKV, WEBM
**Max duration:** 1 hour
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
        logger.error("Sync transcription error: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed.")
    except Exception as exc:
        logger.exception("Unexpected sync transcription error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error.")


# ===========================================================================
# ASYNC TRANSCRIPTION  —  Job + RabbitMQ → orchestrator → STT microservice
# ===========================================================================

@router.post(
    "/transcribe-async",
    response_model=AsyncJobResponse,
    summary="Asynchronous transcription",
    description="""
Queue an STT job for a file already stored in MinIO.

The backend creates a **Job** record and publishes a ``job.created`` event to
RabbitMQ. The **orchestrator** picks it up and dispatches it to the
**STT microservice** via ``job.start.stt``. Results are written back to the
Job row — poll `GET /api/jobs/{job_id}` to check progress.

**Option A — direct MinIO key:** pass `file_key`, e.g. `audio/42/uuid.mp3`.
**Option B — video record:** pass `video_id` (preferred; resolves key from DB).
""",
)
async def transcribe_async(
    file_key: Optional[str] = Query(default=None, description="MinIO object key"),
    video_id: Optional[str] = Query(default=None, description="UUID of an existing Video/Audio DB record"),
    language: Optional[str] = Query(default=None, description="ISO-639-1 code. None = auto-detect"),
    target_lang: Optional[str] = Query(default="arb_Arab", description="Target language for NMT, e.g. 'arb_Arab'"),
    current_user=Depends(get_current_user),
    svc: TranscriptionService = Depends(get_stt_service),
):
    if not file_key and not video_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file_key' (MinIO object key) or 'video_id'.",
        )

    job = await svc.submit_async_transcription(
        file_key=file_key or "",
        user_id=current_user.user_id,
        language=language,
        video_id=video_id,
        target_lang=target_lang,
    )

    return AsyncJobResponse(
        task_id=job.id,
        status=job.status.value.lower(),
        message=f"STT job queued. Poll status at /api/jobs/{job.id}",
    )


# ===========================================================================
# INFO
# ===========================================================================

@router.get("/info", summary="API information")
async def api_info(current_user=Depends(get_current_user)):
    return {
        "name": "Speech-to-Text API",
        "version": "2.0.0",
        "backend": "STT microservice (Faster-Whisper) via HTTP + RabbitMQ/Orchestrator",
        "endpoints": {
            "POST /transcribe":       "Sync transcription (file upload → STT microservice)",
            "POST /transcribe-async": "Async transcription (Job + RabbitMQ → orchestrator → STT microservice)",
        },
        "job_management": "Use /api/jobs/{job_id} (GET) and /api/jobs/{job_id}/cancel (POST) for job lifecycle.",
    }
