"""Settings validation tests for nmt-service."""
import os

import pytest

from app.config import NMT_FALLBACK_MODE_DEFAULT, Settings


@pytest.fixture(autouse=True)
def _clear_nmt_fallback_env(monkeypatch):
    monkeypatch.delenv("NMT_FALLBACK_MODE", raising=False)


def test_nmt_fallback_mode_defaults_to_stage2_only():
    settings = Settings()
    assert settings.NMT_FALLBACK_MODE == NMT_FALLBACK_MODE_DEFAULT


@pytest.mark.parametrize("mode", ["stage2_only", "stage3_updated"])
def test_nmt_fallback_mode_accepts_canonical_values(mode, monkeypatch):
    monkeypatch.setenv("NMT_FALLBACK_MODE", mode)
    settings = Settings()
    assert settings.NMT_FALLBACK_MODE == mode


@pytest.mark.parametrize(
    "invalid",
    ["false", "true", "0", "1", "not_a_valid_mode", ""],
)
def test_nmt_fallback_mode_invalid_values_fail_safe(invalid, monkeypatch, caplog):
    monkeypatch.setenv("NMT_FALLBACK_MODE", invalid)
    settings = Settings()
    assert settings.NMT_FALLBACK_MODE == NMT_FALLBACK_MODE_DEFAULT
    assert "Invalid NMT_FALLBACK_MODE" in caplog.text


@pytest.mark.parametrize("mode", ["STAGE2_ONLY", "Stage3_Updated"])
def test_nmt_fallback_mode_normalizes_case(mode, monkeypatch):
    monkeypatch.setenv("NMT_FALLBACK_MODE", mode)
    settings = Settings()
    assert settings.NMT_FALLBACK_MODE == mode.lower()
