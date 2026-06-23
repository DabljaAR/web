import os
from pydantic_settings import BaseSettings


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
    S3_MEDIA_BUCKET: str = "dablaja-videos"
    S3_MODELS_BUCKET: str = "model"

    # Whisper
    STT_MODEL_SIZE: str = "small"
    STT_MODEL_KEY: str = ""
    STT_MODEL_LOCAL_PATH: str = ""
    STT_MAX_AUDIO_DURATION: int = 3600
    STT_DEVICE: str = "auto"

    # HTTP health endpoint
    PORT: int = 8001
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
