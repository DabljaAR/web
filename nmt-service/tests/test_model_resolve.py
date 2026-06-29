"""Tests for HF fallback guard (F9)."""
from unittest.mock import MagicMock

import pytest

from app.model import resolve_default_model


def test_resolve_default_model_raises_when_hf_fallback_disabled():
    cfg = MagicMock()
    cfg.NMT_MODEL_LOCAL_PATH = "/missing/nmt"
    cfg.S3_MODELS_BUCKET = "model"
    cfg.NMT_MODEL_KEY = "nmt-v4"
    cfg.NMT_HF_FALLBACK = "facebook/nllb-200-distilled-600M"
    cfg.NMT_ALLOW_HF_FALLBACK = False
    cfg.STORAGE_BACKEND = "local"

    with pytest.raises(RuntimeError, match="HuggingFace fallback is disabled"):
        resolve_default_model(config=cfg, download_fn=lambda *_: False)
