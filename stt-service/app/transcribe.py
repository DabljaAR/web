"""Sync transcription endpoint for the STT microservice.

POST /transcribe   — upload a file, get a transcript back immediately.
GET  /health/model — report whether the Whisper model is loaded.
"""
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.model import WhisperModelManager

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_EXTENSIONS = {
    ".mp3", ".mp4", ".wav", ".m4a", ".flac",
    ".ogg", ".wma", ".aac", ".mov", ".mkv", ".webm",
    ".opus", ".oga", ".mpeg", ".mpga",
}

# One shared manager instance — loads the model on first use
_manager = WhisperModelManager()


def _validate_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in _VALID_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: '{ext}'. Supported: {sorted(_VALID_EXTENSIONS)}",
        )


@router.post("/transcribe", summary="Synchronous transcription (file upload)")
async def transcribe_sync(
    file: UploadFile = File(..., description="Audio or video file"),
    language: Optional[str] = Query(
        default=None,
        description="ISO-639-1 language code (e.g. 'en', 'ar'). None = auto-detect.",
    ),
):
    """Upload a file and receive the transcript immediately.

    Runs Whisper in a thread pool so the async event loop is not blocked.
    Best for files under ~10 minutes.
    """
    filename = file.filename or "upload"
    _validate_extension(filename)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    suffix = Path(filename).suffix or ".mp3"
    tmp_path = Path(tempfile.gettempdir()) / f"stt_{uuid.uuid4().hex}{suffix}"

    try:
        tmp_path.write_bytes(content)
        result = await run_in_threadpool(_manager.transcribe, str(tmp_path), language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("[STT] Sync transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed.")
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


@router.get("/health/model", summary="Whisper model load status")
def health_model():
    loaded = WhisperModelManager._model is not None
    return {
        "model_loaded": loaded,
        "model_size": _manager.model_size,
        "device": _manager.device,
        "compute_type": _manager.compute_type,
    }
