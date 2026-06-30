"""Media microservice entry point (HTTP API + merge stage consumer)."""
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.config import settings
from app import db
from app.routes.videos import router as videos_router
from app.routes.ffmpeg_ops import router as ffmpeg_router
from app.worker import start_consumer
from dablja_worker.logging import setup_logging
from dablja_worker.tracing import setup_tracing

setup_logging("media", level=settings.LOG_LEVEL)
setup_tracing("media")
logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_thread
    logger.info("[media] Starting on port %d", settings.PORT)
    db.init_db(settings.sqlalchemy_url)
    logger.info("[media] Database pool created")

    _consumer_thread = threading.Thread(
        target=start_consumer, name="merge-consumer", daemon=True
    )
    _consumer_thread.start()
    logger.info("[media] RabbitMQ merge consumer thread started")

    yield

    if db._engine:
        await db._engine.dispose()
        logger.info("[media] Database pool closed")


app = FastAPI(title="Media Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos_router)
app.include_router(ffmpeg_router)
app.mount("/metrics", make_asgi_app())


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "healthy", "service": "media", "version": "1.0.0"}


@app.get("/readiness", summary="Readiness check")
def readiness():
    alive = _consumer_thread is not None and _consumer_thread.is_alive()
    if not alive:
        raise HTTPException(status_code=503, detail="Merge consumer thread is not running")
    return {"status": "ready", "service": "media", "consumer_alive": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
