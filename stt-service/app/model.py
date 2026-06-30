"""WhisperModelManager for the STT microservice.

Loads the model lazily on first transcription request and reuses it across jobs.
"""
import logging
import os
import time
from threading import Lock
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from dablja_worker.s3_model_download import download_s3_prefix

from app.config import settings

logger = logging.getLogger(__name__)


def _download_model_from_s3(prefix: str, local_path: str, bucket: str) -> int:
    """Download Whisper weights from object storage (parallel per-key downloads).

    Returns the number of files downloaded.
    """
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint(),
        aws_access_key_id=settings.s3_access_key(),
        aws_secret_access_key=settings.s3_secret_key(),
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    downloaded = download_s3_prefix(
        client,
        bucket,
        prefix,
        local_path,
        max_workers=settings.S3_MODEL_DOWNLOAD_WORKERS,
    )
    if downloaded > 0:
        logger.info(
            "[STT] Downloaded %d files from s3://%s/%s → %s",
            downloaded, bucket, prefix.strip("/"), local_path,
        )
    return downloaded


def _resolve_model_path() -> str:
    """Return local cache path if valid, otherwise S3 download or HuggingFace model id."""
    local = (settings.STT_MODEL_LOCAL_PATH or "").strip()
    if local and os.path.isdir(local) and _has_model_files(local):
        logger.info("[STT] Using cached model at %s", local)
        return local

    model_key = (settings.STT_MODEL_KEY or "").strip()
    bucket = (settings.S3_MODELS_BUCKET or "").strip()
    if local and model_key and bucket:
        try:
            os.makedirs(local, exist_ok=True)
            downloaded = _download_model_from_s3(model_key, local, bucket)
            if downloaded == 0:
                logger.warning(
                    "[STT] No objects found at s3://%s/%s — check STT_MODEL_KEY prefix and bucket IAM",
                    bucket,
                    model_key.strip("/"),
                )
            elif _has_model_files(local):
                logger.info("[STT] Model downloaded from S3 to %s", local)
                return local
            else:
                logger.warning(
                    "[STT] Downloaded %d file(s) from s3://%s/%s but missing model.bin/config.json at %s",
                    downloaded,
                    bucket,
                    model_key.strip("/"),
                    local,
                )
        except Exception as exc:
            logger.error("[STT] S3 model download failed: %s", exc)

    if not settings.STT_ALLOW_HF_FALLBACK:
        raise RuntimeError(
            f"STT model not available at {local!r} and HuggingFace fallback is disabled "
            f"(STT_ALLOW_HF_FALLBACK=false). Upload the model to S3 or populate the local cache."
        )

    logger.info("[STT] Falling back to HuggingFace model id: %s", settings.STT_MODEL_SIZE)
    return settings.STT_MODEL_SIZE


def _has_model_files(path: str) -> bool:
    try:
        names = set(os.listdir(path))
        return bool({"model.bin", "config.json"} & names)
    except OSError:
        return False


class WhisperModelManager:
    _model = None
    _lock = Lock()

    def __init__(self):
        self.model_size = settings.STT_MODEL_SIZE
        self._device: Optional[str] = None
        self._compute_type: Optional[str] = None

    @property
    def device(self) -> str:
        if self._device is None:
            configured = (settings.STT_DEVICE or "auto").strip().lower()
            if configured != "auto":
                self._device = configured
            else:
                try:
                    import torch
                    self._device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    self._device = "cpu"
        return self._device

    @property
    def compute_type(self) -> str:
        if self._compute_type is None:
            if self.device == "cuda":
                try:
                    import torch
                    major, _ = torch.cuda.get_device_capability()
                    self._compute_type = "float16" if major >= 7 else "int8_float32"
                except Exception:
                    self._compute_type = "int8_float32"
            else:
                self._compute_type = "int8"
        return self._compute_type

    @property
    def model(self):
        if WhisperModelManager._model is not None:
            return WhisperModelManager._model
        with WhisperModelManager._lock:
            if WhisperModelManager._model is None:
                from faster_whisper import WhisperModel
                path = _resolve_model_path()
                logger.info(
                    "[STT] Loading Whisper | path=%s device=%s compute=%s",
                    path, self.device, self.compute_type,
                )
                t0 = time.perf_counter()
                WhisperModelManager._model = WhisperModel(
                    path, device=self.device, compute_type=self.compute_type
                )
                logger.info("[STT] Model loaded in %.1fs", time.perf_counter() - t0)
        return WhisperModelManager._model

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> dict:
        start = time.time()
        segments_gen, info = self.model.transcribe(
            audio_path,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 50},
            word_timestamps=True,
        )

        if info.duration > settings.STT_MAX_AUDIO_DURATION:
            raise ValueError(
                f"Audio too long: {info.duration:.0f}s (max {settings.STT_MAX_AUDIO_DURATION}s)"
            )

        structured_segments = []
        for seg in segments_gen:
            structured_segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": " ".join(seg.text.split()),
            })

        transcript = " ".join(s["text"] for s in structured_segments)
        processing_time = time.time() - start

        logger.info(
            "[STT] Transcription done | duration=%.1fs | segments=%d | time=%.1fs",
            info.duration, len(structured_segments), processing_time,
        )

        return {
            "transcript": transcript,
            "segments": structured_segments,
            "metadata": {
                "language": info.language,
                "duration": round(info.duration, 2),
                "model_size": self.model_size,
                "device": self.device,
                "compute_type": self.compute_type,
                "processing_time": round(processing_time, 2),
                "segment_count": len(structured_segments),
            },
        }
