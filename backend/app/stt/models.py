"""
app/stt/models.py

WhisperModelManager extends celery.Task so that one model instance is held
per worker process and reused across every STT task invocation.

The model is loaded lazily via a @property — nothing loads at import time.
All original WhisperModelManager logic is unchanged.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import torch
from celery import Task
from faster_whisper import WhisperModel

from app.config import settings
from app.media_service.client import MediaServiceClient
from app.shared.enums import AudioVideoExtension

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WHISPER_REQUIRED_FILES = frozenset({"model.bin", "config.json"})


def _normalize_storage_prefix(prefix: str) -> str:
    """Normalize object-storage prefix to avoid accidental leading slash mismatches."""
    return (prefix or "").strip().lstrip("/")


def _sample_downloaded_files(path: str, limit: int = 8) -> list[str]:
    """Return a small sample of downloaded files to aid cache-debugging logs."""
    if not path or not os.path.isdir(path):
        return []
    sampled: list[str] = []
    for root, _, files in os.walk(path):
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), path)
            sampled.append(rel)
            if len(sampled) >= limit:
                return sampled
    return sampled


def _missing_required_files(path: str) -> list[str]:
    if not path or not os.path.isdir(path):
        return sorted(_WHISPER_REQUIRED_FILES)
    try:
        names = set(os.listdir(path))
    except OSError:
        return sorted(_WHISPER_REQUIRED_FILES)
    return sorted(_WHISPER_REQUIRED_FILES - names)


def _validate_whisper_model_dir(path: str) -> bool:
    """True if *path* looks like a CTranslate2 / faster-whisper model directory."""
    if not path or not os.path.isdir(path):
        return False
    try:
        names = set(os.listdir(path))
    except OSError:
        return False
    return bool(names & _WHISPER_REQUIRED_FILES)


def resolve_whisper_model() -> tuple[str, str]:
    """
    Resolve Whisper model path / id: local cache → S3 (S3_MODELS_BUCKET + STT_MODEL_KEY) → HuggingFace Hub.
    """
    local_path = (settings.STT_MODEL_LOCAL_PATH or "").strip()
    raw_key = (settings.STT_MODEL_KEY or "").strip()
    key = _normalize_storage_prefix(raw_key)
    bucket = settings.S3_MODELS_BUCKET
    hf_name = settings.STT_MODEL_SIZE

    if raw_key and key != raw_key:
        logger.warning(
            "[STT] Normalized STT_MODEL_KEY from %r to %r to match object-prefix contract.",
            raw_key,
            key,
        )

    logger.info(
        "[STT] Resolving Whisper model | local_path=%s key=%s bucket=%s hf=%s",
        local_path or "(none)",
        key or "(none)",
        bucket,
        hf_name,
    )

    if local_path and _validate_whisper_model_dir(local_path):
        logger.info("[STT][CACHE] source=local_disk_hit path=%s", local_path)
        return local_path, "local_disk_hit"

    if settings.STORAGE_BACKEND.lower() == "s3" and key and local_path:
        logger.info(
            "[STT] Downloading Whisper from object storage | bucket=%s key=%s → %s",
            bucket,
            key,
            local_path,
        )
        try:
            os.makedirs(local_path, exist_ok=True)
            client = MediaServiceClient()
            ok = asyncio.run(client.download_prefix(key, Path(local_path)))
            if not ok:
                logger.warning(
                    "[STT] Rust media-service download_prefix returned no files | bucket=%s key=%s. "
                    "Expected prefix to contain model.bin and config.json. Falling back to HuggingFace Hub.",
                    bucket,
                    key,
                )
            elif _validate_whisper_model_dir(local_path):
                logger.info("[STT][CACHE] source=s3_hit path=%s", local_path)
                return local_path, "s3_hit"
            else:
                missing = _missing_required_files(local_path)
                sampled = _sample_downloaded_files(local_path)
                logger.warning(
                    "[STT] Rust media-service download finished but validation failed at %s "
                    "(missing=%s sampled_files=%s). Falling back to HuggingFace Hub.",
                    local_path,
                    missing,
                    sampled,
                )
        except Exception as exc:
            logger.error("[STT] Rust media-service download failed: %s", exc)
    elif key and not local_path:
        logger.warning(
            "[STT] STT_MODEL_KEY is set but STT_MODEL_LOCAL_PATH is empty; "
            "skipping S3 download. Set STT_MODEL_LOCAL_PATH to enable cache + S3 pull.",
        )
    elif not key and local_path:
        logger.warning(
            "[STT] STT_MODEL_LOCAL_PATH is set but STT_MODEL_KEY is empty; skipping S3 download.",
        )

    logger.warning(
        "[STT] Falling back to HuggingFace Hub / size id: %s. "
        "Configure S3_MODELS_BUCKET + STT_MODEL_KEY + STT_MODEL_LOCAL_PATH to avoid this.",
        hf_name,
    )
    logger.info("[STT][CACHE] source=hf_fallback model=%s", hf_name)
    return hf_name, "hf_fallback"


def clean_text(text: str) -> str:
    """Strip and collapse whitespace in transcribed text."""
    return " ".join(text.split())


VALID_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    e.value for e in AudioVideoExtension
)

MAX_AUDIO_DURATION   = settings.STT_MAX_AUDIO_DURATION
MAX_RETRIES          = settings.STT_RETRY_ATTEMPTS
RETRY_DELAY          = settings.STT_RETRY_DELAY
GPU_MEMORY_THRESHOLD = settings.STT_GPU_MEMORY_THRESHOLD


# ===========================================================================
# WhisperModelManager — also the Celery base task
# ===========================================================================

class WhisperModelManager(Task):
    """
    Production-grade Whisper transcription manager.

    Extends celery.Task so pipeline tasks (e.g. ``stt_transcribe``) can bind
    a WhisperModelManager instance for model reuse. This class is ``abstract``
    so Celery does not register it as its own task name.
    """

    abstract = True  # tells Celery: base class only, don't register as a task

    # Class-level holders so the model survives across task invocations
    _model: Optional[WhisperModel] = None
    _lock             = Lock()
    _is_transcribing  = False

    def __init__(self):
        # Resolve config — do NOT load the model here
        self.model_size    = settings.STT_MODEL_SIZE
        self._device       = None
        self._compute_type = None

        self.metrics = {
            "total_requests":            0,
            "successful_transcriptions": 0,
            "failed_transcriptions":     0,
            "total_processing_time":     0,
            "avg_processing_time":       0,
        }

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = settings.get_device()
        return self._device

    @property
    def compute_type(self) -> str:
        if self._compute_type is None:
            self._compute_type = settings.get_compute_type()
        return self._compute_type

    @property
    def model(self) -> WhisperModel:
        """Load the Whisper model once per worker process (lazy)."""
        if WhisperModelManager._model is not None:
            logger.info("[STT][CACHE] source=in_memory_hit")
            return WhisperModelManager._model

        if WhisperModelManager._model is None:
            logger.info(
                f"[STT] Loading Whisper | size={self.model_size} | "
                f"device={self.device} | compute_type={self.compute_type}"
            )
            resolved, cache_source = resolve_whisper_model()
            local_cache = os.path.isdir(resolved)
            logger.info(
                "[STT] Whisper model source: %s (%s) | cache_source=%s",
                resolved,
                "local directory" if local_cache else "HuggingFace Hub id — first load may take minutes",
                cache_source,
            )
            if settings.HF_TOKEN:
                os.environ["HF_TOKEN"] = settings.HF_TOKEN
                logger.info("[STT] HF_TOKEN set for Hub authentication")
            logger.info(
                "[STT] Constructing WhisperModel (large Hub downloads log little until complete)…"
            )
            t0 = time.perf_counter()
            try:
                WhisperModelManager._model = WhisperModel(
                    resolved,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                elapsed = time.perf_counter() - t0
                logger.info(
                    "[STT] Whisper model loaded successfully in %.1fs",
                    elapsed,
                )
            except Exception as e:
                logger.error(f"❌ Failed to load Whisper model: {e}")
                raise
        return WhisperModelManager._model

    # ------------------------------------------------------------------
    # Validation  (unchanged)
    # ------------------------------------------------------------------

    def _validate_audio_file(self, audio_path: str) -> None:
        path = Path(audio_path)

        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not os.access(audio_path, os.R_OK):
            raise PermissionError(f"Cannot read audio file: {audio_path}")

        max_size_gb  = settings.STT_MAX_FILE_SIZE_GB
        file_size_gb = path.stat().st_size / (1024 ** 3)
        if file_size_gb > max_size_gb:
            raise ValueError(
                f"File too large: {file_size_gb:.2f} GB (max {max_size_gb} GB)"
            )

        if path.suffix.lower() not in VALID_AUDIO_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {path.suffix}. "
                f"Supported: {VALID_AUDIO_EXTENSIONS}"
            )

    # ------------------------------------------------------------------
    # GPU helpers  (unchanged)
    # ------------------------------------------------------------------

    def _check_gpu_memory(self) -> bool:
        if self.device != "cuda":
            return True
        try:
            allocated = (
                torch.cuda.memory_allocated()
                / torch.cuda.get_device_properties(0).total_memory
            )
            if allocated > GPU_MEMORY_THRESHOLD:
                logger.warning(
                    f"GPU memory {allocated*100:.1f}% > "
                    f"threshold {GPU_MEMORY_THRESHOLD*100:.0f}%"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Could not check GPU memory: {e}")
            return True

    def _cleanup_gpu_memory(self) -> None:
        if self.device == "cuda":
            try:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public transcribe  (unchanged)
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs,
    ) -> dict:
        self._validate_audio_file(audio_path)

        if not self._check_gpu_memory():
            raise RuntimeError("Insufficient GPU memory. Please try again later.")

        with self._lock:
            if self._is_transcribing:
                raise RuntimeError(
                    "Transcription already in progress. Use async endpoint."
                )
            self._is_transcribing = True

        try:
            self.metrics["total_requests"] += 1
            return self._transcribe_with_retry(audio_path, language, **kwargs)
        finally:
            self._is_transcribing = False
            self._cleanup_gpu_memory()

    def _transcribe_with_retry(
        self,
        audio_path: str,
        language: Optional[str],
        **kwargs,
    ) -> dict:
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Transcription attempt {attempt + 1}/{MAX_RETRIES} | "
                    f"file={Path(audio_path).name}"
                )
                start_time = time.time()

                segments_generator, info = self.model.transcribe(
                    audio_path,
                    language=language,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 50},
                    **kwargs,
                )

                if info.duration > settings.STT_MAX_AUDIO_DURATION:
                    raise ValueError(
                        f"Audio too long: {info.duration:.0f}s "
                        f"(max {settings.STT_MAX_AUDIO_DURATION}s)"
                    )

                segments = list(segments_generator)
                structured_segments = [
                    {
                        "start": round(seg.start, 2),
                        "end":   round(seg.end,   2),
                        "text":  clean_text(seg.text),
                    }
                    for seg in segments
                ]

                transcript      = " ".join(s["text"] for s in structured_segments)
                processing_time = time.time() - start_time

                self.metrics["successful_transcriptions"] += 1
                self.metrics["total_processing_time"]     += processing_time
                self.metrics["avg_processing_time"]        = (
                    self.metrics["total_processing_time"]
                    / self.metrics["successful_transcriptions"]
                )

                result = {
                    "transcript": transcript,
                    "segments":   structured_segments,
                    "metadata": {
                        "language":        info.language,
                        "duration":        round(info.duration, 2),
                        "model_size":      self.model_size,
                        "device":          self.device,
                        "compute_type":    self.compute_type,
                        "processing_time": round(processing_time, 2),
                        "segment_count":   len(structured_segments),
                    },
                }

                logger.info(
                    f"✅ Transcription done | duration={info.duration:.1f}s | "
                    f"time={processing_time:.1f}s | "
                    f"speed={info.duration/processing_time:.2f}x"
                )
                return result

            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                last_exception = e
                logger.warning(f"GPU error attempt {attempt + 1}: {e}")
                self._cleanup_gpu_memory()
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)

            except Exception as e:
                logger.exception(f"Transcription failed: {e}")
                raise RuntimeError("STT inference failed") from e

        self.metrics["failed_transcriptions"] += 1
        raise RuntimeError(
            f"Transcription failed after {MAX_RETRIES} retries: {last_exception}"
        )

    # ------------------------------------------------------------------
    # Metrics / health / cleanup  (unchanged)
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        return {
            **self.metrics,
            "device":          self.device,
            "model_size":      self.model_size,
            "compute_type":    self.compute_type,
            "is_transcribing": self._is_transcribing,
        }

    def get_health(self) -> dict:
        return {
            "status":       "healthy",
            "model_loaded": WhisperModelManager._model is not None,
            "device":       self.device,
            "model_size":   self.model_size,
            "version":      "2.0.0",
        }

    def cleanup(self) -> None:
        try:
            self._cleanup_gpu_memory()
            logger.info("WhisperModelManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
