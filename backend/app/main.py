from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import logging

from app.dependencies import connect_to_db, disconnect_from_db
from app.core.router import router as core_router
from app.core import init_db
from app.core.rate_limiter import limiter
from slowapi.errors import RateLimitExceeded
from app.shared.logging import setup_logging
from app.shared.middleware import ExceptionLoggingMiddleware
from app.shared.enums import modelSize
from app.config import settings

# Import SST router and service
from app.stt.router import router as sst_router, set_service
from app.stt.services import TranscriptionService
from app.stt.models import WhisperModelManager


logger = logging.getLogger(__name__)


async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests, wait 1 min and after 1 min make it can send request again"}
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown logic for the application.
    """
    # Initialize logging system
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_dir=settings.LOG_DIR,
        log_file=settings.LOG_FILE,
        max_bytes=settings.LOG_MAX_BYTES,
        backup_count=settings.LOG_BACKUP_COUNT,
        enable_console=settings.LOG_ENABLE_CONSOLE,
        enable_file=settings.LOG_ENABLE_FILE,
        json_format=settings.LOG_JSON_FORMAT
    )
    
    logger.info("=" * 80)
    logger.info("🚀 Application starting up...")
    logger.info("=" * 80)
    
    # Startup logic
    try:
        # Initialize database
        logger.info("🔌 Connecting to database...")
        await connect_to_db()
        await init_db()
        logger.info("✅ Database connected and initialized")
        
        # Initialize Speech-to-Text service
        logger.info("🎤 Initializing Speech-to-Text service...")
        
        model_manager = WhisperModelManager(
            model_size=modelSize.MEDIUM.value
        )
        transcription_service = TranscriptionService(model_manager)
        set_service(transcription_service)  # Pass service to router
        logger.info("✅ Speech-to-Text service initialized")
        
        logger.info("=" * 80)
        logger.info("✅ Application ready!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error("❌ Failed to initialize application during startup", exc_info=True)
        raise
    
    try:
        yield
    finally:
        # Shutdown logic
        logger.info("=" * 80)
        logger.info("🛑 Application shutting down...")
        logger.info("=" * 80)
        
        try:
            await disconnect_from_db()
            logger.info("✅ Database disconnected")
        except Exception as e:
            logger.error("❌ Error during database disconnection", exc_info=True)
        
        try:
            # Clean up Speech-to-Text service if needed
            logger.info("🧹 Cleaning up Speech-to-Text service...")
            logger.info("✅ Speech-to-Text service cleaned up")
        except Exception as e:
            logger.error("❌ Error during service cleanup", exc_info=True)
        
        logger.info("=" * 80)


# ============================================================================
# FastAPI App Initialization
# ============================================================================

app = FastAPI(
    title="DabljaAR Backend",
    description="Combined API for User Management and Speech-to-Text",
    version="1.0.0",
    lifespan=lifespan
)

# ============================================================================
# Middleware & Exception Handling
# ============================================================================

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

# Add exception logging middleware
app.add_middleware(ExceptionLoggingMiddleware)

# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to return error response for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        }
    )

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",      # Vite default port
        "http://localhost:3000",      # Alternative frontend port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# API Root Endpoint
# ============================================================================

@app.get("/api")
async def read_root():
    """Root API endpoint."""
    return {
        "message": "Welcome to DabljaAR Backend",
        "available_services": {
            "user_management": "/api/users, /api/signup, /api/login, /api/subscriptions, /api/payments",
            "speech_to_text": "/api/transcription",
            "documentation": "/docs",
            "openapi": "/openapi.json"
        }
    }


# ============================================================================
# Router Registration
# ============================================================================

# Include Core Router (User Management, Auth, Subscriptions, Payments)
logger.info("📋 Registering core router...")
app.include_router(core_router, prefix="/api")

# Include SST Router (Speech-to-Text API)
# Already has prefix="/api/transcription" defined in sst/router.py
logger.info("📋 Registering SST (Speech-to-Text) router...")
app.include_router(sst_router)


# ============================================================================
# Static Files
# ============================================================================

# Mount static files for uploaded avatars
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)