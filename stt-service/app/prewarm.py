"""Startup model pre-warm for STT (F8)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_model_ready = threading.Event()
_prewarm_error: Optional[str] = None
_prewarm_thread: Optional[threading.Thread] = None


def mark_ready_without_prewarm() -> None:
    """Skip model load at startup; readiness does not wait for the model."""
    _model_ready.set()


def _load_model() -> None:
    global _prewarm_error
    from app.model import WhisperModelManager

    try:
        t0 = time.perf_counter()
        manager = WhisperModelManager()
        _ = manager.model
        logger.info(
            "[STT][PREWARM] Model ready in %.1fs | device=%s compute=%s",
            time.perf_counter() - t0,
            manager.device,
            manager.compute_type,
        )
        _model_ready.set()
    except Exception as exc:
        _prewarm_error = str(exc)
        logger.exception("[STT][PREWARM] Model load failed: %s", exc)


def start_prewarm() -> None:
    """Load Whisper in a background thread during service startup."""
    global _prewarm_thread
    _prewarm_thread = threading.Thread(
        target=_load_model,
        name="stt-prewarm",
        daemon=True,
    )
    _prewarm_thread.start()


def is_model_ready() -> bool:
    return _model_ready.is_set()


def prewarm_error() -> Optional[str]:
    return _prewarm_error
