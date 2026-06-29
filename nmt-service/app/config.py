import logging
import os

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

NMT_FALLBACK_MODE_ALLOWED = frozenset({"stage2_only", "stage3_updated"})
NMT_FALLBACK_MODE_DEFAULT = "stage2_only"


class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # PostgreSQL (sync psycopg2 for worker thread)
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/dabljaar"

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_MODELS_BUCKET: str = "model"

    # NMT model resolution (mirrors backend priority chain)
    NMT_MODEL_LOCAL_PATH: str = "/model-cache/nmt-v4"
    NMT_MODEL_KEY: str = "nmt-v4"
    NMT_HF_FALLBACK: str = "facebook/nllb-200-distilled-600M"
    STORAGE_BACKEND: str = "local"   # "s3" enables object-storage download
    HF_TOKEN: str = ""

    # Groq — Arabic length adjustment
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    NMT_LENGTH_ADJUST_ENABLED: bool = True
    NMT_LENGTH_ADJUST_SCALE: float = 0.9
    NMT_LENGTH_ADJUST_MAX_ITERS: int = 5

    # Translation quality fallback (stage2_only | stage3_updated)
    NMT_FALLBACK_MODE: str = "stage2_only"

    NMT_BATCH_SIZE: int = 8
    S3_MODEL_DOWNLOAD_WORKERS: int = 8
    NMT_ALLOW_HF_FALLBACK: bool = False
    PREWARM_NMT_MODEL: bool = True

    # HTTP health endpoint
    PORT: int = 8002
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @model_validator(mode="after")
    def _validate_nmt_fallback_mode(self) -> "Settings":
        """Normalize NMT_FALLBACK_MODE; unknown values fail safe to stage2_only."""
        raw_mode = str(self.NMT_FALLBACK_MODE or "").strip().lower()
        if raw_mode not in NMT_FALLBACK_MODE_ALLOWED:
            logger.warning(
                "Invalid NMT_FALLBACK_MODE=%r. Allowed=%s; falling back to %s.",
                self.NMT_FALLBACK_MODE,
                sorted(NMT_FALLBACK_MODE_ALLOWED),
                NMT_FALLBACK_MODE_DEFAULT,
            )
            raw_mode = NMT_FALLBACK_MODE_DEFAULT

        object.__setattr__(self, "NMT_FALLBACK_MODE", raw_mode)
        return self

    def s3_endpoint(self) -> str:
        if self.S3_ENDPOINT_URL:
            return self.S3_ENDPOINT_URL
        scheme = "https" if self.MINIO_SECURE else "http"
        return f"{scheme}://{self.MINIO_ENDPOINT}"

    def s3_access_key(self) -> str:
        return self.S3_ACCESS_KEY_ID or self.MINIO_ACCESS_KEY

    def s3_secret_key(self) -> str:
        return self.S3_SECRET_ACCESS_KEY or self.MINIO_SECRET_KEY


settings = Settings()
