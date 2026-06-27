import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/dabljaar"

    RABBITMQ_HEARTBEAT: int = 600
    RABBITMQ_BLOCKED_TIMEOUT: int = 300
    RABBITMQ_MAX_RETRIES: int = 30
    RABBITMQ_PREFETCH: int = 1

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_MEDIA_BUCKET: str = "dablaja-videos"

    SILMA_DEVICE: str = "auto"
    SILMA_REFERENCE_AUDIO: str = ""
    SILMA_REFERENCE_TEXT: str = (
        "مرحبا بك في موقع جملة. استمتع بالتسوق الإلكتروني عبر الإنترنت "
        "بكل سهولة وأمان مع خدمة التوصيل لكل ولايات الوطن"
    )
    TTS_DEFAULT_SPEED: float = 0.9
    TTS_DEFAULT_CFG_STRENGTH: float = 2.0
    TTS_DEFAULT_NFE_STEP: int = 64
    TTS_DEFAULT_SWAY_COEF: float = -1.0
    TTS_DEFAULT_TARGET_RMS: float = 0.12
    TTS_ENABLE_NORMALIZER: bool = True
    TTS_FORCE_TASHKEEL: bool = False

    HF_HOME: str = "/model-cache/hf"
    HF_TOKEN: str = ""

    PORT: int = 8004
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

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
