"""TTS Microservice entry point."""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException

from app import prewarm
from app.config import settings
from app.routes import router as tts_router
from app.worker import start_consumer
from dablja_worker import __version__ as DABLJA_WORKER_VERSION

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_thread
    logger.info("[TTS] Starting RabbitMQ consumer thread (dablja-worker=%s)", DABLJA_WORKER_VERSION)
    _consumer_thread = threading.Thread(target=start_consumer, name="tts-consumer", daemon=True)
    _consumer_thread.start()

    if settings.PREWARM_TTS_MODEL:
        logger.info("[TTS] PREWARM_TTS_MODEL=true — loading SILMA at startup")
        prewarm.start_prewarm()
    else:
        logger.info("[TTS] PREWARM_TTS_MODEL=false — model loads on first request")
        prewarm.mark_ready_without_prewarm()

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
    alive = _consumer_thread is not None and _consumer_thread.is_alive()
    if not alive:
        raise HTTPException(status_code=503, detail="Consumer thread is not running")

    if settings.PREWARM_TTS_MODEL and not prewarm.is_model_ready():
        err = prewarm.prewarm_error()
        detail = f"Model not ready{f': {err}' if err else ''}"
        raise HTTPException(status_code=503, detail=detail)

    return {
        "status": "ready",
        "service": "tts",
        "consumer_alive": True,
        "model_ready": prewarm.is_model_ready(),
    }


@app.get("/health/model", summary="TTS model load status")
def health_model():
    try:
        from app.model import _tts

        return {
            "status": "ok",
            "model_loaded": _tts._model is not None,
            "device": _tts.device,
            "prewarm_ready": prewarm.is_model_ready(),
            "prewarm_error": prewarm.prewarm_error(),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "TTS Microservice",
        "port": settings.PORT,
        "endpoints": {
            "POST /synthesize": "Standalone TTS synthesis",
            "GET  /status/{job_id}": "Job status",
            "GET  /health": "Liveness check",
            "GET  /readiness": "Readiness check",
            "GET  /health/model": "SILMA model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
