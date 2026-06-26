import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app import db
from app.routes.health import router as health_router
from app.routes.videos import router as videos_router
from app.routes.ffmpeg_ops import router as ffmpeg_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting media-service on port %d", settings.PORT)
    db.init_db(settings.sqlalchemy_url)
    logger.info("Database pool created.")

    # Start RabbitMQ consumer for merge stage
    from app.worker import start_consumer
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    logger.info("RabbitMQ merge consumer thread started")

    yield

    if db._engine:
        await db._engine.dispose()
        logger.info("Database pool closed.")


app = FastAPI(title="Media Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(videos_router)
app.include_router(ffmpeg_router)
