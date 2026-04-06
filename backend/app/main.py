import gc
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.api.job_router import router as job_router
from app.api.media_routers import router as media_router
from app.config import settings
from app.core import init_db
from app.core.rate_limiter import limiter
from app.core.router import router as core_router
from app.dependencies import connect_to_db, disconnect_from_db
from app.nmt.router import router as nmt_router
from app.stt.router import router as stt_router
from app.tts.router import router as tts_router
from app.shared.logging import setup_logging
from app.shared.middleware import ExceptionLoggingMiddleware

logger = logging.getLogger(__name__)


async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests, wait 1 min and after 1 min make it can send request again"
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize logging
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_dir=settings.LOG_DIR,
        log_file=settings.LOG_FILE,
        max_bytes=settings.LOG_MAX_BYTES,
        backup_count=settings.LOG_BACKUP_COUNT,
        enable_console=settings.LOG_ENABLE_CONSOLE,
        enable_file=settings.LOG_ENABLE_FILE,
        json_format=settings.LOG_JSON_FORMAT,
    )

    logger.info("=" * 80)
    logger.info("🚀 Application starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    logger.info("=" * 80)

    try:
        logger.info("🔌 Connecting to database...")
        await connect_to_db()
        await init_db()
        logger.info("Database connected and initialized")
    except Exception as e:
        logger.error("Failed to connect to database during startup", exc_info=True)
        raise

    try:
        yield
    finally:
        logger.info("🛑 Application shutting down...")

        try:
            await disconnect_from_db()
            logger.info("✅ Database disconnected")
        except Exception:
            logger.error("❌ Error during database disconnection", exc_info=True)

        try:
            gc.collect()
            logger.info("✅ Garbage collection completed")
        except Exception:
            logger.error("❌ Error during garbage collection", exc_info=True)

        logger.info("=" * 80)


# ===========================================================================
# App
# ===========================================================================

app = FastAPI(
    title="DabljaAR Backend",
    description="Combined API for User Management and Speech-to-Text",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware & exception handlers
# ---------------------------------------------------------------------------

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.add_middleware(ExceptionLoggingMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers  (each registered exactly once)
# ---------------------------------------------------------------------------

app.include_router(core_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(job_router, prefix="/api")
app.include_router(stt_router)  # Re-enabled, has prefix="/api/transcription"
app.include_router(nmt_router, prefix="/api")
app.include_router(tts_router, prefix="/api/tts")  # Re-enabled

# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------


@app.get("/api")
async def read_root():
    return {"message": "Welcome to DabljaAR Backend"}


# Mount static files for uploaded avatars
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS if settings.ENVIRONMENT == "production" else 1,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower(),
    )
