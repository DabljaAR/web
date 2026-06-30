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
    S3_REGION: str = "us-east-1"
    S3_MEDIA_BUCKET: str = "dablaja-videos"

    OMNIVOICE_MODEL_NAME: str = "k2-fsa/OmniVoice"
    OMNIVOICE_DEVICE: str = "auto"
    OMNIVOICE_DTYPE: str = "float16"
    OMNIVOICE_NUM_STEP: int = 32
    OMNIVOICE_GUIDANCE_SCALE: float = 2.0
    OMNIVOICE_SPEED: float = 1.0

    SAMPLE_RATE: int = 24000

    TTS_REFERENCE_AUDIO_PATH: str = ""
    TTS_REFERENCE_AUDIO_TEXT: str = ""
    TTS_VOICE_INSTRUCT: str = ""

    DUBBING_MAX_STRETCH_RATIO: float = 1.2
    DUBBING_MIN_STRETCH_RATIO: float = 0.8
    DUBBING_SILENCE_THRESHOLD: float = 0.1
    DUBBING_TEMP_DIR: str = "/tmp/dubbing_merge"

    HF_HOME: str = "/model-cache/hf"
    HF_TOKEN: str = ""
    CATT_TASHKEEL_MODEL_DIR: str = ""

    PORT: int = 8005
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

    def s3_region(self) -> str:
        return (self.S3_REGION or "us-east-1").strip() or "us-east-1"

    def catt_tashkeel_dir(self) -> str:
        if self.CATT_TASHKEEL_MODEL_DIR:
            return self.CATT_TASHKEEL_MODEL_DIR
        return os.path.join(self.HF_HOME, "..", "catt_tashkeel", "onnx_models")


settings = Settings()
