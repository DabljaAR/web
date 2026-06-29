"""Tests for startup pre-warm and readiness gating (F8)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import prewarm
from app.main import readiness


@pytest.fixture(autouse=True)
def reset_prewarm_state():
    prewarm._model_ready.clear()
    prewarm._prewarm_error = None
    yield
    prewarm._model_ready.clear()
    prewarm._prewarm_error = None


def test_readiness_waits_for_model_when_prewarm_enabled():
    mock_settings = MagicMock()
    mock_settings.PREWARM_NMT_MODEL = True

    with patch("app.main.settings", mock_settings), patch("app.main._consumer_thread") as consumer:
        consumer.is_alive.return_value = True
        with pytest.raises(HTTPException) as exc:
            readiness()
        assert exc.value.status_code == 503
        assert "loading" in exc.value.detail.lower()


def test_readiness_ok_when_prewarm_complete():
    mock_settings = MagicMock()
    mock_settings.PREWARM_NMT_MODEL = True
    prewarm._model_ready.set()

    with patch("app.main.settings", mock_settings), patch("app.main._consumer_thread") as consumer:
        consumer.is_alive.return_value = True
        result = readiness()

    assert result["status"] == "ready"
    assert result["model_loaded"] is True


def test_readiness_skips_model_when_prewarm_disabled():
    mock_settings = MagicMock()
    mock_settings.PREWARM_NMT_MODEL = False

    with patch("app.main.settings", mock_settings), patch("app.main._consumer_thread") as consumer:
        consumer.is_alive.return_value = True
        prewarm.mark_ready_without_prewarm()
        result = readiness()

    assert result["status"] == "ready"
    assert result["model_loaded"] is False
