import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables
    )
    
    # ========== DATABASE ==========
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar"
    )
    
    # ========== AUTHENTICATION ==========
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "300"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Auth0 / Social configuration
    GOOGLE_REDIRECT_URL: str = os.getenv("GOOGLE_REDIRECT_URL", "")
    FACEBOOK_REDIRECT_URL: str = os.getenv("FACEBOOK_REDIRECT_URL", "")
    AUTH0_DOMAIN: str = os.getenv("AUTH0_DOMAIN", "")
    AUTH0_CLIENT_ID: str = os.getenv("AUTH0_CLIENT_ID", "")
    AUTH0_CLIENT_SECRET: str = os.getenv("AUTH0_CLIENT_SECRET", "")
    AUTH0_AUDIENCE: str = os.getenv("AUTH0_AUDIENCE", "")

    # ========== MINIO / S3 CONFIGURATION ==========
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET_NAME: str = os.getenv("MINIO_BUCKET_NAME", "dablaja-videos")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "False").lower() == "true"
    
    # ========== LOCAL STORAGE CONFIGURATION ==========
    # Used only when MINIO_ENDPOINT is not configured. 
    # For local development fallback only; production should use MinIO.
    LOCAL_STORAGE_DIR: str = os.getenv("LOCAL_STORAGE_DIR", "uploads")
    LOCAL_STORAGE_URL_PREFIX: str = os.getenv("LOCAL_STORAGE_URL_PREFIX", "/uploads")
    
    # ========== LOGGING CONFIGURATION ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    LOG_ENABLE_CONSOLE: bool = os.getenv("LOG_ENABLE_CONSOLE", "True").lower() == "true"
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "True").lower() == "true"  # Set to False in production for stdout-only (12-factor app)
    LOG_JSON_FORMAT: bool = os.getenv("LOG_JSON_FORMAT", "False").lower() == "true"
    LOG_ENABLE_SUCCESS: bool = os.getenv("LOG_ENABLE_SUCCESS", "True").lower() == "true"
    
    # ========== SPEECH-TO-TEXT (STT) ==========
    STT_MODEL_SIZE: str = os.getenv("STT_MODEL_SIZE", "small")
    STT_DEVICE: str = os.getenv("STT_DEVICE", "auto")
    STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "auto")
    STT_MAX_CONCURRENT: int = int(os.getenv("STT_MAX_CONCURRENT", "1"))
    STT_MAX_AUDIO_DURATION: int = int(os.getenv("STT_MAX_AUDIO_DURATION", "3600"))
    STT_MAX_FILE_SIZE_GB: float = float(os.getenv("STT_MAX_FILE_SIZE_GB", "5"))
    STT_GPU_MEMORY_THRESHOLD: float = float(os.getenv("STT_GPU_MEMORY_THRESHOLD", "0.9"))
    STT_RETRY_ATTEMPTS: int = int(os.getenv("STT_RETRY_ATTEMPTS", "3"))
    STT_RETRY_DELAY: int = int(os.getenv("STT_RETRY_DELAY", "2"))
    
    # ========== TEXT-TO-SPEECH (TTS - SILMA) ==========
    SILMA_DEVICE: str = os.getenv("SILMA_DEVICE", "auto")  # "auto", "cpu", "cuda"
    SILMA_REFERENCE_AUDIO: str = os.getenv("SILMA_REFERENCE_AUDIO", "")  # Path to reference audio for voice cloning
    SILMA_REFERENCE_TEXT: str = os.getenv("SILMA_REFERENCE_TEXT", "")  # Transcript of reference audio
    TTS_DEFAULT_SPEED: float = float(os.getenv("TTS_DEFAULT_SPEED", "1.0"))  # Speech rate multiplier (1.0 = normal)
    TTS_DEFAULT_CFG_STRENGTH: float = float(os.getenv("TTS_DEFAULT_CFG_STRENGTH", "1.0"))  # Guidance strength
    TTS_DEFAULT_NFE_STEP: int = int(os.getenv("TTS_DEFAULT_NFE_STEP", "32"))  # Number of function evaluations
    TTS_DEFAULT_SWAY_COEF: float = float(os.getenv("TTS_DEFAULT_SWAY_COEF", "-1.0"))  # Sway sampling coefficient
    TTS_DEFAULT_TARGET_RMS: float = float(os.getenv("TTS_DEFAULT_TARGET_RMS", "0.12"))  # Target RMS for audio normalization
    
    # ========== NEURAL MACHINE TRANSLATION (NMT) ==========
    NMT_MODEL_LOCAL_PATH: str = os.getenv("NMT_MODEL_LOCAL_PATH", "/model-cache/nmt-v4")
    NMT_MODEL_BUCKET: str     = os.getenv("NMT_MODEL_BUCKET", "model")
    NMT_MODEL_KEY: str        = os.getenv("NMT_MODEL_KEY", "nmt-v4")
    NMT_HF_FALLBACK: str      = os.getenv("NMT_HF_FALLBACK", "facebook/nllb-200-distilled-600M")

    # ========== HUGGINGFACE AUTHENTICATION ==========
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")  # HuggingFace access token for model downloads
    
    # ========== SERVER ==========
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    WORKERS: int = int(os.getenv("WORKERS", "1"))
    
    # ========== CORS ==========
    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    # ========== ENVIRONMENT ==========
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # ========== CELERY / REDIS ==========
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "2"))
    
    def get_device(self) -> str:
        """Get the device (auto-detect if set to 'auto')."""
        if self.STT_DEVICE == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except:
                return "cpu"
        return self.STT_DEVICE
    
    def get_compute_type(self) -> str:
        """Get compute type (auto-select based on device and capability)."""
        if self.STT_COMPUTE_TYPE == "auto":
            device = self.get_device()
            if device == "cuda":
                try:
                    import torch
                    major, _ = torch.cuda.get_device_capability()
                    # Pascal (6.x) and older don't support efficient float16
                    if major >= 7:
                        return "float16"
                    return "int8_float32"
                except:
                    return "int8_float32"
            return "int8"
        return self.STT_COMPUTE_TYPE
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"


settings = Settings()