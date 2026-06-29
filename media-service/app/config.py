import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/dabljaar"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_HEARTBEAT: int = 600
    RABBITMQ_BLOCKED_TIMEOUT: int = 300
    RABBITMQ_MAX_RETRIES: int = 30
    RABBITMQ_PREFETCH: int = 1

    AWS_ENDPOINT_URL: str = "http://localhost:9000"
    AWS_ACCESS_KEY_ID: str = "minioadmin"
    AWS_SECRET_ACCESS_KEY: str = "minioadmin"
    AWS_DEFAULT_REGION: str = "us-east-1"
    S3_MEDIA_BUCKET: str = "dablaja-videos"

    MERGE_TEMP_DIR: str = "/tmp/dubbing_merge"
    DUBBING_OUTPUT_AUDIO_CODEC: str = "aac"
    DUBBING_OUTPUT_AUDIO_BITRATE: str = "192k"

    PORT: int = 8003
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and "+asyncpg" not in url and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_db_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url


settings = Settings()
