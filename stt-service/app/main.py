"""STT Microservice entry point.

Starts a RabbitMQ consumer (in a daemon thread) alongside a FastAPI server that
exposes:
  POST /transcribe        — synchronous file-upload transcription
  GET  /health            — liveness check
  GET  /readiness         — readiness check (consumer + model when prewarm enabled)
  GET  /health/model      — Whisper model load status
"""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app

from app.config import settings
from app import prewarm
from app.transcribe import router as transcribe_router
from app.worker import start_consumer
from dablja_worker.logging import setup_logging
from dablja_worker.tracing import setup_tracing

setup_logging("stt", level=settings.LOG_LEVEL)
setup_tracing("stt")
logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_thread
    logger.info("[STT] Starting RabbitMQ consumer thread")
    _consumer_thread = threading.Thread(target=start_consumer, name="stt-consumer", daemon=True)
    _consumer_thread.start()

    if settings.PREWARM_STT_MODEL:
        logger.info("[STT] PREWARM_STT_MODEL=true — loading Whisper at startup")
        prewarm.start_prewarm()
    else:
        logger.info("[STT] PREWARM_STT_MODEL=false — model loads on first request")
        prewarm.mark_ready_without_prewarm()

    yield
    logger.info("[STT] Shutting down")


app = FastAPI(
    title="STT Microservice",
    version="1.0.0",
    description="Speech-to-Text via Faster-Whisper. Exposes a sync HTTP endpoint and a RabbitMQ consumer.",
    lifespan=lifespan,
)

app.include_router(transcribe_router)
app.mount("/metrics", make_asgi_app())


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "healthy", "service": "stt", "version": "1.0.0"}


@app.get("/readiness", summary="Readiness check")
def readiness():
    """Returns 200 when the consumer is alive and (if enabled) the model is loaded."""
    alive = _consumer_thread is not None and _consumer_thread.is_alive()
    if not alive:
        raise HTTPException(status_code=503, detail="Consumer thread is not running")

    if settings.PREWARM_STT_MODEL and not prewarm.is_model_ready():
        detail = "Whisper model is still loading"
        if prewarm.prewarm_error():
            detail = f"Whisper model load failed: {prewarm.prewarm_error()}"
        raise HTTPException(status_code=503, detail=detail)

    return {
        "status": "ready",
        "service": "stt",
        "consumer_alive": True,
        "model_loaded": prewarm.is_model_ready() if settings.PREWARM_STT_MODEL else False,
    }


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "STT Microservice",
        "endpoints": {
            "POST /transcribe": "Synchronous transcription (file upload)",
            "GET  /health": "Liveness check",
            "GET  /readiness": "Readiness check",
            "GET  /health/model": "Whisper model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
