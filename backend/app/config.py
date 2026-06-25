import hashlib
import logging
import os
from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Cache S3-downloaded SILMA reference paths by object key (worker process lifetime).
_silma_ref_audio_cache: dict[str, str] = {}
PIPELINE_SEGMENTS_MODE_ALLOWED = {"stt_focused", "single", "tts_focused"}
PIPELINE_SEGMENTS_MODE_DEFAULT = "single"
NMT_FALLBACK_MODE_ALLOWED = {"stage2_only", "stage3_updated"}
NMT_FALLBACK_MODE_DEFAULT = "stage2_only"


def _env_s3_media_bucket() -> str:
    """Resolve primary bucket for user media (uploads, pipeline, presigned URLs)."""
    return (
        os.getenv("S3_MEDIA_BUCKET")
        or os.getenv("S3_BUCKET_NAME")
        or os.getenv("MINIO_BUCKET_NAME")
        or "dablaja-videos"
    )


def _env_s3_models_bucket() -> str:
    """Resolve bucket for AI model artifacts (NMT weights from object storage; STT/TTS if added)."""
    return os.getenv("S3_MODELS_BUCKET") or os.getenv("NMT_MODEL_BUCKET") or "model"


def _download_silma_reference(s3_key: str) -> str:
    """Download SILMA reference audio from object storage (media bucket) to a temp file."""
    if s3_key in _silma_ref_audio_cache:
        cached = _silma_ref_audio_cache[s3_key]
        if os.path.exists(cached):
            return cached

    import asyncio as _asyncio
    import tempfile as _tmp

    from app.media.storage import get_storage_service

    digest = hashlib.sha256(s3_key.encode("utf-8")).hexdigest()[:16]
    ext = os.path.splitext(s3_key)[1] or ".wav"
    dest_dir = os.path.join(_tmp.gettempdir(), "dabljaar", "silma_ref")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"ref_{digest}{ext}")

    try:
        ok = _asyncio.run(get_storage_service().download(s3_key, dest))
        if ok and os.path.exists(dest):
            _silma_ref_audio_cache[s3_key] = dest
            logger.info(
                "[TTS] Downloaded SILMA reference audio key=%s → %s", s3_key, dest
            )
            return dest
    except Exception as exc:
        logger.error("[TTS] S3 reference audio download failed: %s", exc)
    return ""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    # ========== DATABASE ==========
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar"
    )

    # ========== AUTHENTICATION ==========
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "your-secret-key-change-this-in-production"
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "300")
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Auth0 / Social configuration
    GOOGLE_REDIRECT_URL: str = os.getenv("GOOGLE_REDIRECT_URL", "")
    FACEBOOK_REDIRECT_URL: str = os.getenv("FACEBOOK_REDIRECT_URL", "")
    AUTH0_DOMAIN: str = os.getenv("AUTH0_DOMAIN", "")
    AUTH0_CLIENT_ID: str = os.getenv("AUTH0_CLIENT_ID", "")
    AUTH0_CLIENT_SECRET: str = os.getenv("AUTH0_CLIENT_SECRET", "")
    AUTH0_AUDIENCE: str = os.getenv("AUTH0_AUDIENCE", "")

    # ========== MINIO / S3 CONFIGURATION (legacy names, still supported) ==========
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET_NAME: str = os.getenv("MINIO_BUCKET_NAME", "dablaja-videos")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "False").lower() == "true"

    # ========== STORAGE BACKEND (S3-compatible: MinIO, GCP interop, AWS S3) ==========
    # Choices: "local" | "s3". Default: s3 if MINIO_ENDPOINT is set in the environment.
    STORAGE_BACKEND: str = os.getenv(
        "STORAGE_BACKEND",
        "s3" if os.getenv("MINIO_ENDPOINT") else "local",
    )
    # Generic S3 credentials — S3_* override MINIO_* when set (empty string = unset, for Docker Compose).
    S3_ENDPOINT_URL: str = (os.getenv("S3_ENDPOINT_URL") or "").strip() or os.getenv(
        "MINIO_ENDPOINT", ""
    )
    S3_ACCESS_KEY_ID: str = (os.getenv("S3_ACCESS_KEY_ID") or "").strip() or os.getenv(
        "MINIO_ACCESS_KEY", ""
    )
    S3_SECRET_ACCESS_KEY: str = (
        os.getenv("S3_SECRET_ACCESS_KEY") or ""
    ).strip() or os.getenv("MINIO_SECRET_KEY", "")
    # Media vs models buckets (may be the same name). Primary env: S3_MEDIA_BUCKET / S3_MODELS_BUCKET.
    S3_MEDIA_BUCKET: str = _env_s3_media_bucket()
    S3_BUCKET_NAME: str = (
        _env_s3_media_bucket()
    )  # alias of S3_MEDIA_BUCKET for backward compatibility
    # NMT (and future STT/TTS weights in object storage) use this bucket + model-specific keys/prefixes.
    S3_MODELS_BUCKET: str = _env_s3_models_bucket()
    NMT_MODEL_BUCKET: str = (
        _env_s3_models_bucket()
    )  # alias of S3_MODELS_BUCKET for backward compatibility
    S3_REGION: str = os.getenv("S3_REGION", "")
    S3_SECURE: bool = (
        os.getenv("S3_SECURE") or os.getenv("MINIO_SECURE", "False")
    ).lower() == "true"

    @model_validator(mode="after")
    def _s3_empty_env_falls_back_to_minio(self) -> "Settings":
        """Docker Compose may set S3_* to empty strings; treat as unset and use MinIO_*."""
        if not (self.S3_ENDPOINT_URL or "").strip():
            object.__setattr__(self, "S3_ENDPOINT_URL", self.MINIO_ENDPOINT)
        if not (self.S3_ACCESS_KEY_ID or "").strip():
            object.__setattr__(self, "S3_ACCESS_KEY_ID", self.MINIO_ACCESS_KEY)
        if not (self.S3_SECRET_ACCESS_KEY or "").strip():
            object.__setattr__(self, "S3_SECRET_ACCESS_KEY", self.MINIO_SECRET_KEY)
        return self

    # ========== LOCAL STORAGE CONFIGURATION ==========
    # Used when STORAGE_BACKEND=local (filesystem under LOCAL_STORAGE_DIR).
    LOCAL_STORAGE_DIR: str = os.getenv("LOCAL_STORAGE_DIR", "uploads")
    LOCAL_STORAGE_URL_PREFIX: str = os.getenv("LOCAL_STORAGE_URL_PREFIX", "/uploads")

    # ========== LOGGING CONFIGURATION ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    LOG_ENABLE_CONSOLE: bool = os.getenv("LOG_ENABLE_CONSOLE", "True").lower() == "true"
    LOG_TO_FILE: bool = (
        os.getenv("LOG_TO_FILE", "True").lower() == "true"
    )  # Set to False in production for stdout-only (12-factor app)
    LOG_JSON_FORMAT: bool = os.getenv("LOG_JSON_FORMAT", "False").lower() == "true"
    LOG_ENABLE_SUCCESS: bool = os.getenv("LOG_ENABLE_SUCCESS", "True").lower() == "true"

    # ========== SPEECH-TO-TEXT (STT) ==========
    STT_MODEL_SIZE: str = os.getenv("STT_MODEL_SIZE", "small")
    STT_DEVICE: str = os.getenv("STT_DEVICE", "auto")
    STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "auto")
    STT_MAX_CONCURRENT: int = int(os.getenv("STT_MAX_CONCURRENT", "1"))
    STT_MAX_AUDIO_DURATION: int = int(os.getenv("STT_MAX_AUDIO_DURATION", "3600"))
    STT_MAX_FILE_SIZE_GB: float = float(os.getenv("STT_MAX_FILE_SIZE_GB", "5"))
    STT_GPU_MEMORY_THRESHOLD: float = float(
        os.getenv("STT_GPU_MEMORY_THRESHOLD", "0.9")
    )
    STT_RETRY_ATTEMPTS: int = int(os.getenv("STT_RETRY_ATTEMPTS", "3"))
    STT_RETRY_DELAY: int = int(os.getenv("STT_RETRY_DELAY", "2"))
    # Whisper (faster-whisper / CTranslate2): optional S3 prefix under S3_MODELS_BUCKET → STT_MODEL_LOCAL_PATH
    STT_MODEL_KEY: str = os.getenv("STT_MODEL_KEY", "")
    STT_MODEL_LOCAL_PATH: str = os.getenv("STT_MODEL_LOCAL_PATH", "")

    # ========== TEXT-TO-SPEECH (TTS - SILMA) ==========
    SILMA_DEVICE: str = os.getenv("SILMA_DEVICE", "auto")  # "auto", "cpu", "cuda"
    SILMA_REFERENCE_AUDIO: str = os.getenv(
        "SILMA_REFERENCE_AUDIO", ""
    )  # Path to reference audio for voice cloning
    # Default: transcript of the bundled ar.ref.24k.wav shipped with silma_tts
    SILMA_REFERENCE_TEXT: str = os.getenv(
        "SILMA_REFERENCE_TEXT",
        "ويدقق النظر في القرآن الكريم وسائر الكتب السماوية ويتبع مسالك الرسل العظام عليهم الصلاة والسلام.",
    )
    TTS_DEFAULT_SPEED: float = float(
        os.getenv("TTS_DEFAULT_SPEED", "0.9")
    )  # Slightly slower = more natural Arabic pacing
    TTS_DEFAULT_CFG_STRENGTH: float = float(
        os.getenv("TTS_DEFAULT_CFG_STRENGTH", "2.0")
    )  # F5-TTS paper default; 1.0 too weak
    TTS_DEFAULT_NFE_STEP: int = int(
        os.getenv("TTS_DEFAULT_NFE_STEP", "64")
    )  # More diffusion steps = fewer robotic artifacts
    TTS_DEFAULT_SWAY_COEF: float = float(
        os.getenv("TTS_DEFAULT_SWAY_COEF", "-1.0")
    )  # Sway sampling coefficient
    TTS_DEFAULT_TARGET_RMS: float = float(
        os.getenv("TTS_DEFAULT_TARGET_RMS", "0.12")
    )  # Target RMS for audio normalization
    TTS_ENABLE_NORMALIZER: bool = (
        os.getenv("TTS_ENABLE_NORMALIZER", "True").lower() == "true"
    )  # Enable text normalizer for better handling of numbers, dates, etc. in Arabic input text
    TTS_FORCE_TASHKEEL: bool = (
        os.getenv("TTS_FORCE_TASHKEEL", "False").lower() == "true"
    )  # Force inclusion of Arabic diacritics (tashkeel) in input text for better pronunciation, at the cost of requiring properly formatted input

    # ========== NEURAL MACHINE TRANSLATION (NMT) ==========
    NMT_MODEL_LOCAL_PATH: str = os.getenv("NMT_MODEL_LOCAL_PATH", "/model-cache/nmt-v4")
    # Model object-storage prefix (bucket = S3_MODELS_BUCKET / NMT_MODEL_BUCKET above)
    NMT_MODEL_KEY: str = os.getenv("NMT_MODEL_KEY", "nmt-v4")
    NMT_HF_FALLBACK: str = os.getenv(
        "NMT_HF_FALLBACK", "facebook/nllb-200-distilled-600M"
    )
    # stage2_only: stop after stage-2 retry
    # stage3_updated: continue to stage-3 only when updated Arabic/mixed-token score is high
    NMT_FALLBACK_MODE: str = os.getenv(
        "NMT_FALLBACK_MODE", NMT_FALLBACK_MODE_DEFAULT
    )

    # ========== GROQ (NMT length adjustment) ==========
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ── NMT length adjustment knobs ──────────────────────────────────────────
    # Enabled: adjusts Arabic translation length to match English speaking duration.
    # Scale: target AR-letter count = EN-syllable count × scale (0.9 = 90 %).
    # MaxIters: max Groq rewrite rounds per segment.
    NMT_LENGTH_ADJUST_ENABLED: bool = (
        os.getenv("NMT_LENGTH_ADJUST_ENABLED", "true").lower() == "true"
    )
    NMT_LENGTH_ADJUST_SCALE: float = float(os.getenv("NMT_LENGTH_ADJUST_SCALE", "0.9"))
    NMT_LENGTH_ADJUST_MAX_ITERS: int = int(os.getenv("NMT_LENGTH_ADJUST_MAX_ITERS", "5"))

    # ========== HUGGINGFACE AUTHENTICATION ==========
    HF_TOKEN: str = os.getenv(
        "HF_TOKEN", ""
    )  # HuggingFace access token for model downloads
    HF_HOME: str = os.getenv(
        "HF_HOME", os.path.expanduser("/model-cache/hf")
    )  # HuggingFace cache directory
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

    # ========== RABBITMQ (Go orchestrator + native workers) ==========
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

    # ========== CELERY / REDIS ==========
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "2"))

    # ========== PIPELINE ==========
    # stt_focused: keep original segments generated by stt
    # single: run all segments through the pipeline as a single chunk
    # tts_focused: rebuild segments from words for better TTS output (experimental; may cause issues with timing and NMT)
    PIPELINE_SEGMENTS_MODE: str = os.getenv(
        "PIPELINE_SEGMENTS_MODE", PIPELINE_SEGMENTS_MODE_DEFAULT
    )

    @model_validator(mode="after")
    def _validate_pipeline_segments_mode(self) -> "Settings":
        """Normalize and validate pipeline mode, then warn-and-fallback on invalid values."""
        raw_mode = str(self.PIPELINE_SEGMENTS_MODE or "").strip().lower()
        if raw_mode in {"single_chunk", "true"}:
            raw_mode = "single"
        elif raw_mode in {"segmented", "false"}:
            raw_mode = "stt_focused"

        if raw_mode not in PIPELINE_SEGMENTS_MODE_ALLOWED:
            logger.warning(
                "Invalid PIPELINE_SEGMENTS_MODE=%r. Allowed=%s; falling back to %s.",
                self.PIPELINE_SEGMENTS_MODE,
                sorted(PIPELINE_SEGMENTS_MODE_ALLOWED),
                PIPELINE_SEGMENTS_MODE_DEFAULT,
            )
            raw_mode = PIPELINE_SEGMENTS_MODE_DEFAULT

        object.__setattr__(self, "PIPELINE_SEGMENTS_MODE", raw_mode)
        return self

    @model_validator(mode="after")
    def _validate_nmt_fallback_mode(self) -> "Settings":
        """Normalize and validate NMT fallback mode."""
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

    # ========== DUBBING / MERGE ==========
    # Backward-compatible: older deployments use DUBBING_MERGE_PATH.
    DUBBING_MERGE_PATH: str = os.getenv("DUBBING_MERGE_PATH", "/tmp/dubbing_merge")
    # New canonical name used by DubbingMergeService.
    DUBBING_TEMP_DIR: str = os.getenv("DUBBING_TEMP_DIR", DUBBING_MERGE_PATH)

    # Audio timing controls (used during concat / stretching).
    DUBBING_MAX_STRETCH_RATIO: float = float(
        os.getenv("DUBBING_MAX_STRETCH_RATIO", "1.2")
    )
    DUBBING_MIN_STRETCH_RATIO: float = float(
        os.getenv("DUBBING_MIN_STRETCH_RATIO", "0.8")
    )
    # If the gap between segments is smaller than this (seconds), it will be treated as 0.
    DUBBING_SILENCE_THRESHOLD: float = float(
        os.getenv("DUBBING_SILENCE_THRESHOLD", "0.1")
    )

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

    def get_silma_reference_audio(self) -> str:
        """Return the SILMA reference audio path as a WAV file.

        Resolution order:
          1. SILMA_REFERENCE_AUDIO env var (if it points to an existing file)
          2. Object storage (S3): same env value as object key in S3_MEDIA_BUCKET when not a local path
          3. Auto-detect bundled ar.ref.24k.wav shipped with silma_tts package
          4. Return empty string (caller handles missing case)
        """
        candidate = self._resolve_silma_audio_path()
        if not candidate:
            return ""
        if os.path.splitext(candidate)[1].lower() == ".wav":
            return candidate
        return self._convert_to_wav(candidate)

    def _resolve_silma_audio_path(self) -> str:
        if self.SILMA_REFERENCE_AUDIO and os.path.exists(self.SILMA_REFERENCE_AUDIO):
            return self.SILMA_REFERENCE_AUDIO

        if self.SILMA_REFERENCE_AUDIO and self.STORAGE_BACKEND.lower() == "s3":
            cached = _download_silma_reference(self.SILMA_REFERENCE_AUDIO)
            if cached:
                return cached

        try:
            import importlib.util

            spec = importlib.util.find_spec("silma_tts")
            if spec:
                pkg_root = (
                    spec.submodule_search_locations[0]
                    if spec.submodule_search_locations
                    else (os.path.dirname(spec.origin) if spec.origin else None)
                )
                if pkg_root:
                    bundled = os.path.join(
                        pkg_root, "infer", "ref_audio_samples", "ar.ref.24k.wav"
                    )
                    if os.path.exists(bundled):
                        return bundled
        except Exception:
            pass
        return ""

    def _convert_to_wav(self, src: str) -> str:
        """Convert *src* to a 24 kHz mono WAV and return the new path. Falls back to *src* on error."""
        import subprocess
        import tempfile

        wav_path = os.path.join(
            tempfile.gettempdir(),
            os.path.splitext(os.path.basename(src))[0] + "_ref.wav",
        )
        if os.path.exists(wav_path):
            return wav_path
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", src, "-ar", "24000", "-ac", "1", wav_path],
                check=True,
                capture_output=True,
            )
            return wav_path
        except Exception:
            return src

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"


settings = Settings()
