from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from app.dependencies import connect_to_db, disconnect_from_db
from app.core.router import router as core_router
from app.core import init_db
from app.core.rate_limiter import limiter
from slowapi.errors import RateLimitExceeded
from app.shared.logging import setup_logging
from app.shared.middleware import ExceptionLoggingMiddleware
from app.config import settings
import logging

async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests, wait 1 min and after 1 min make it can send request again"}
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    
    # Get logger for startup
    logger = logging.getLogger(__name__)
    logger.info("Application starting up...")
    
    # Startup logic
    try:
        await connect_to_db()
        await init_db()
        logger.info("Database connected and initialized")
        
        # Warm up NMT model
        from app.nmt.service import init_nmt
        logger.info("Warming up NMT model...")
        await init_nmt()
        logger.info("NMT model warmed up successfully")
        
    except Exception as e:
        logger.error("Failed to connect to database or initialize NMT during startup", exc_info=True)
        raise
    
    try:
        yield
    finally:
        # Shutdown logic
        logger.info("Application shutting down...")
        try:
            await disconnect_from_db()
            logger.info("Database disconnected")
        except Exception as e:
            logger.error("Error during database disconnection", exc_info=True)

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

# Add exception logging middleware
app.add_middleware(ExceptionLoggingMiddleware)

# Global exception handler for unhandled exceptions
# Note: Exceptions are already logged by ExceptionLoggingMiddleware, so we only return the response here
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to return error response for unhandled exceptions."""
    # Exception is already logged by ExceptionLoggingMiddleware, so we just return the response
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        }
    )
# # Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*" 
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api")
async def read_root():
    return {"message": "Welcome to DabljaAR Backend"}


from app.api.media_routers import router as media_router
from app.nmt.router import router as nmt_router

app.include_router(core_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(nmt_router, prefix="/api")


# Mount static files for uploaded avatars
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)