"""NMT Microservice entry point.

Starts a RabbitMQ consumer (in a daemon thread) alongside a FastAPI server that
exposes:
  POST /translate      — synchronous single-string translation
  GET  /health         — liveness check
  GET  /readiness      — readiness check (consumer thread alive)
  GET  /health/model   — NLLB model load status
"""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.translate import router as translate_router
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
    logger.info("[NMT] Starting RabbitMQ consumer thread")
    _consumer_thread = threading.Thread(target=start_consumer, name="nmt-consumer", daemon=True)
    _consumer_thread.start()
    yield
    logger.info("[NMT] Shutting down")


app = FastAPI(
    title="NMT Microservice",
    version="1.0.0",
    description="Neural Machine Translation via NLLB. Exposes a sync HTTP endpoint and a RabbitMQ consumer.",
    lifespan=lifespan,
)

app.include_router(translate_router)


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "healthy", "service": "nmt", "version": "1.0.0"}


@app.get("/readiness", summary="Readiness check")
def readiness():
    from fastapi import HTTPException
    alive = _consumer_thread is not None and _consumer_thread.is_alive()
    if not alive:
        raise HTTPException(status_code=503, detail="Consumer thread is not running")
    return {"status": "ready", "service": "nmt", "consumer_alive": True}


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "NMT Microservice",
        "endpoints": {
            "POST /translate": "Synchronous translation (single string)",
            "GET  /health": "Liveness check",
            "GET  /readiness": "Readiness check",
            "GET  /health/model": "NLLB model load status",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
