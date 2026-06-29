"""TTS Microservice entry point (OmniVoice).

Starts a RabbitMQ consumer (daemon thread) alongside a FastAPI server:

  POST /synthesize        — synchronous single-string TTS
  POST /synthesize/batch  — batch TTS for multiple segments
  GET  /health            — liveness check
  GET  /readiness         — readiness check (consumer alive)
  GET  /health/model      — OmniVoice model load status
"""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.synthesize import router as synthesize_router
from app.worker import start_consumer

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s \u2014 %(message)s",
)
logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_thread
    logger.info("[TTS] Starting RabbitMQ consumer thread")
    _consumer_thread = threading.Thread(
        target=start_consumer, name="tts-consumer", daemon=True
    )
    _consumer_thread.start()
    yield
    logger.info("[TTS] Shutting down")


app = FastAPI(
    title="TTS Microservice (OmniVoice)",
    version="1.0.0",
    description="Text-to-Speech via OmniVoice. Exposes sync HTTP endpoints and a RabbitMQ consumer.",
    lifespan=lifespan,
)
app.include_router(synthesize_router)


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "healthy", "service": "tts", "version": "1.0.0"}


@app.get("/readiness", summary="Readiness check")
def readiness():
    from fastapi import HTTPException

    alive = _consumer_thread is not None and _consumer_thread.is_alive()
    if not alive:
        raise HTTPException(status_code=503, detail="Consumer thread is not running")
    return {"status": "ready", "service": "tts", "consumer_alive": True}


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "TTS Microservice (OmniVoice)",
        "endpoints": {
            "POST /synthesize": "Synchronous TTS (single string)",
            "POST /synthesize/batch": "Batch TTS (multiple segments)",
            "GET  /health": "Liveness check",
            "GET  /readiness": "Readiness check",
            "GET  /health/model": "OmniVoice model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
