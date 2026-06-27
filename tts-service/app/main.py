"""TTS Microservice entry point.

Starts a RabbitMQ consumer (daemon thread) alongside a FastAPI server that exposes:
  POST /synthesize    — standalone TTS synthesis
  GET  /status/{id}   — job status
  GET  /jobs/{id}     — job detail
  GET  /health        — liveness
  GET  /readiness     — consumer thread alive check
  GET  /health/model  — SILMA model load status
"""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.routes import router as tts_router
from app.worker import start_consumer

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_thread
    logger.info("[TTS] Starting RabbitMQ consumer thread")
    _consumer_thread = threading.Thread(target=start_consumer, name="tts-consumer", daemon=True)
    _consumer_thread.start()
    yield
    logger.info("[TTS] Shutting down")


app = FastAPI(
    title="TTS Microservice",
    version="1.0.0",
    description="SILMA-TTS Arabic speech synthesis. RabbitMQ consumer + HTTP API.",
    lifespan=lifespan,
)

app.include_router(tts_router)


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


@app.get("/health/model", summary="TTS model load status")
def health_model():
    try:
        from app.model import _tts
        model_loaded = _tts._model is not None
        return {"status": "ok", "model_loaded": model_loaded, "device": _tts.device}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "TTS Microservice",
        "endpoints": {
            "POST /synthesize": "Standalone TTS synthesis",
            "GET  /status/{job_id}": "Job status",
            "GET  /jobs/{job_id}": "Job detail",
            "GET  /health": "Liveness check",
            "GET  /readiness": "Readiness check",
            "GET  /health/model": "SILMA model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
