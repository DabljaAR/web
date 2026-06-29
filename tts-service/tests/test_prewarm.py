"""Unit tests for TTS prewarm readiness gating."""
from app import prewarm


def test_mark_ready_without_prewarm():
    prewarm._model_ready.clear()
    prewarm.mark_ready_without_prewarm()
    assert prewarm.is_model_ready()


def test_prewarm_error_initially_none():
    assert prewarm.prewarm_error() is None
