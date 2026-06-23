"""STT Microservice entry point.

Starts a RabbitMQ consumer (in a daemon thread) alongside a FastAPI server that
exposes:
  POST /transcribe        — synchronous file-upload transcription
  GET  /health            — liveness check
  GET  /health/model      — Whisper model load status
"""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.transcribe import router as transcribe_router
from app.worker import start_consumer

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[STT] Starting RabbitMQ consumer thread")
    t = threading.Thread(target=start_consumer, name="stt-consumer", daemon=True)
    t.start()
    yield
    logger.info("[STT] Shutting down")


app = FastAPI(
    title="STT Microservice",
    version="1.0.0",
    description="Speech-to-Text via Faster-Whisper. Exposes a sync HTTP endpoint and a RabbitMQ consumer.",
    lifespan=lifespan,
)

app.include_router(transcribe_router)


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "healthy", "service": "stt", "version": "1.0.0"}


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "STT Microservice",
        "endpoints": {
            "POST /transcribe": "Synchronous transcription (file upload)",
            "GET  /health": "Liveness check",
            "GET  /health/model": "Whisper model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
