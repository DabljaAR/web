# -*- coding: utf-8 -*-
"""
SILMA-TTS model manager and Celery synthesis task.

Supports Arabic text-to-speech with voice cloning from reference audio.

Worker must be launched with --pool=solo (same reason as Whisper —
TTS inference is blocking and not fork-safe).
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional

import soundfile as sf
import torch
from celery import Task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Model manager
# ---------------------------------------------------------------------------

class SilmaTTSModelManager(Task):
    """
    Celery Task subclass that owns the SILMA-TTS model lifecycle.

    The model is loaded lazily on first use and kept in memory for the
    lifetime of the worker process.

    Usage (as Celery task):
        synthesize_tts.apply_async(
            kwargs=dict(
                text="النص المراد تحويله",
                ref_audio_path="/path/to/reference.wav",
                ref_text="النص المرجعي",
                job_id="123",
            ),
            queue="ai_tts",
        )
    """

    abstract = True  # not auto-registered; subclassed below as the real task

    # Lazy model slot
    _model: Optional[object] = None
    _device: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def device(self) -> str:
        """Auto-detect device if not already set."""
        if self._device is None:
            from app.config import settings
            silma_device = settings.SILMA_DEVICE.lower()
            
            if silma_device == "cpu":
                self._device = "cpu"
            elif silma_device == "cuda":
                self._device = "cuda"
            else:  # "auto"
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            
            logger.info("SILMA-TTS using device: %s (SILMA_DEVICE=%s)", self._device, silma_device)
        return self._device

    def _load_model(self):
        """Load SILMA-TTS model (lazy initialization)."""
        if self._model is None:
            try:
                from silma_tts.api import SilmaTTS
            except ImportError as e:
                logger.error("Failed to import silma_tts: %s", e)
                raise RuntimeError(
                    "SILMA-TTS not installed. Install with: pip install silma-tts"
                ) from e

            # Set HuggingFace token if available
            from app.config import settings
            if settings.HF_TOKEN:
                os.environ["HF_TOKEN"] = settings.HF_TOKEN
                logger.info("HF_TOKEN configured for model download authentication")
            else:
                logger.warning("HF_TOKEN not found - large model downloads may fail")

            logger.info("Loading SILMA-TTS model...")
            self._model = SilmaTTS()
            logger.info("SILMA-TTS model loaded successfully.")

        return self._model

    # ------------------------------------------------------------------
    # Public synthesis API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        *,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        nfe_step: Optional[int] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        sway_sampling_coef: Optional[float] = None,
        target_rms: Optional[float] = None,
        seed: Optional[int] = None,
        output_format: str = "wav",
    ) -> bytes:
        """
        Synthesize Arabic speech and return raw audio bytes.

        Parameters
        ----------
        text:                Arabic text to synthesize (can include English).
        ref_audio_path:      Path to a reference WAV/MP3 for voice cloning.
                             Required if not set in settings.
        ref_text:            Transcript of the reference audio.
                             Can be None - will be transcribed automatically.
        nfe_step:            Number of function evaluations (higher = better quality).
                             Default: 32
        speed:               Speech rate multiplier (1.0 = normal).
                             Default: 1.0
        cfg_strength:        Classifier-free guidance strength.
                             Default: 1.0
        sway_sampling_coef:  Sway sampling coefficient.
                             Default: -1.0
        target_rms:          Target RMS for audio normalization.
                             Default: 0.12
        seed:                Random seed for reproducibility (None = random).
        output_format:       "wav" (default) or "flac".

        Returns
        -------
        bytes: Audio data in the requested format.
        """
        from app.config import settings

        # Load model
        model = self._load_model()

        # Resolve reference audio and text
        _ref_audio = ref_audio_path or settings.SILMA_REFERENCE_AUDIO
        _ref_text = ref_text or settings.SILMA_REFERENCE_TEXT or None

        if not _ref_audio:
            raise ValueError(
                "Reference audio path is required. "
                "Either pass ref_audio_path or set SILMA_REFERENCE_AUDIO in .env"
            )

        if not os.path.exists(_ref_audio):
            raise FileNotFoundError(f"Reference audio not found: {_ref_audio}")

        # Use defaults from settings if not provided
        _nfe_step = nfe_step if nfe_step is not None else settings.TTS_DEFAULT_NFE_STEP
        _speed = speed if speed is not None else settings.TTS_DEFAULT_SPEED
        _cfg = cfg_strength if cfg_strength is not None else settings.TTS_DEFAULT_CFG_STRENGTH
        _sway = sway_sampling_coef if sway_sampling_coef is not None else settings.TTS_DEFAULT_SWAY_COEF
        _rms = target_rms if target_rms is not None else settings.TTS_DEFAULT_TARGET_RMS

        # Clean text — strip stray double-quotes
        clean_text = text.replace('"', '').strip()
        if not clean_text:
            raise ValueError("TTS synthesis received empty text after cleaning.")

        logger.info(
            "Synthesizing [nfe=%d, speed=%.2f, cfg=%.2f, sway=%.2f, rms=%.2f], "
            "text length=%d chars",
            _nfe_step, _speed, _cfg, _sway, _rms, len(clean_text),
        )

        # Create temp file for output (SILMA requires file_wave parameter)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Run SILMA inference
            wav, sr, spec = model.infer(
                ref_file=_ref_audio,
                ref_text=_ref_text,
                gen_text=clean_text,
                file_wave=tmp_path,
                seed=seed,
                speed=_speed,
                cfg_strength=_cfg,
                nfe_step=_nfe_step,
                sway_sampling_coef=_sway,
                target_rms=_rms,
            )

            # Read the generated audio file
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            logger.info("SILMA synthesis completed, output size: %d bytes", len(audio_bytes))

        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # If output format is not WAV, convert it
        if output_format.lower() != "wav":
            buf = io.BytesIO()
            # Read the WAV data and re-encode to requested format
            with sf.SoundFile(io.BytesIO(audio_bytes)) as sf_file:
                data = sf_file.read()
                sample_rate = sf_file.samplerate
            sf.write(buf, data, sample_rate, format=output_format.upper())
            buf.seek(0)
            audio_bytes = buf.read()

        return audio_bytes


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

def register_tts_task(celery_app):
    """
    Call this from your Celery app factory to register the TTS synthesis task.

    Example (in celery_app.py / worker entrypoint):

        from app.tts.models import register_tts_task
        register_tts_task(celery_app)

    Then dispatch with:

        synthesize_tts.apply_async(
            kwargs=dict(
                text="النص",
                ref_audio_path="/path/to/ref.wav",
                ref_text="النص المرجعي",
                job_id="42",
            ),
            queue="ai_tts",
        )
    """

    @celery_app.task(
        bind=True,
        base=SilmaTTSModelManager,
        name="app.jobs.tasks.tts.synthesize",
        max_retries=2,
        default_retry_delay=5,
    )
    def synthesize_tts(
        self: SilmaTTSModelManager,
        *,
        text: str,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        nfe_step: Optional[int] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        sway_sampling_coef: Optional[float] = None,
        target_rms: Optional[float] = None,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
        upload_to_minio: bool = False,
        minio_key: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> dict:
        """
        Celery task: synthesize Arabic TTS and write the result to disk
        (or return raw bytes if output_path is None).

        Returns a dict:
            {
                "status":       "success",
                "job_id":       <job_id>,
                "output_path":  "/path/to/output.wav",  # or None
                "minio_key":    "tts/xxx/output.wav",   # if uploaded
                "audio_url":    "https://...",          # presigned URL if uploaded
                "bytes_size":   <int>,
            }
        """
        audio_bytes = self.synthesize(
            text=text,
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            nfe_step=nfe_step,
            speed=speed,
            cfg_strength=cfg_strength,
            sway_sampling_coef=sway_sampling_coef,
            target_rms=target_rms,
            seed=seed,
        )

        audio_url = None
        final_minio_key = None

        # Save locally if path provided
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            logger.info("TTS output written to %s (%d bytes)", output_path, len(audio_bytes))

        # Upload to MinIO if requested
        if upload_to_minio:
            try:
                from app.media.storage import get_storage_service
                storage = get_storage_service()
                final_minio_key = minio_key or f"tts/{job_id}/output.wav"
                
                # Run async upload in sync context
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        storage.upload_bytes(audio_bytes, final_minio_key, "audio/wav")
                    )
                    
                    # Get presigned URL
                    audio_url = loop.run_until_complete(
                        storage.get_url(final_minio_key)
                    )
                finally:
                    loop.close()
                
                logger.info("TTS output uploaded to MinIO: %s", final_minio_key)
            except Exception as e:
                logger.warning("Failed to upload TTS to MinIO: %s", e)

        return {
            "status":      "success",
            "job_id":      job_id,
            "output_path": output_path,
            "minio_key":   final_minio_key,
            "audio_url":   audio_url,
            "bytes_size":  len(audio_bytes),
        }

    return synthesize_tts
