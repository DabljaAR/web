"""Tests for NMT translation fallback stages (stage-3 word-by-word guard)."""
from unittest.mock import MagicMock, patch

from app.model import NLLBTranslatorWrapper


def _make_wrapper(fallback_mode: str) -> NLLBTranslatorWrapper:
    cfg = MagicMock()
    cfg.NMT_FALLBACK_MODE = fallback_mode
    return NLLBTranslatorWrapper(config=cfg)


def test_stage3_skipped_when_fallback_mode_stage2_only():
    wrapper = _make_wrapper("stage2_only")

    with patch.object(wrapper, "_run_inference", return_value="hello") as run_inf, \
         patch.object(wrapper, "_translate_word_by_word") as word_by_word, \
         patch.object(wrapper, "_english_ratio", return_value=0.0), \
         patch.object(wrapper, "_updated_quality_score", return_value=1.0):
        result = wrapper._translate_item(
            "Hello world",
            src_lang="eng_Latn",
            tgt_lang="arb_Arab",
            num_beams=5,
            english_ratio_threshold=0.5,
        )

    assert result == "hello"
    run_inf.assert_called()
    word_by_word.assert_not_called()


def test_stage3_runs_only_when_fallback_mode_stage3_updated():
    wrapper = _make_wrapper("stage3_updated")

    with patch.object(wrapper, "_run_inference", return_value="bad mix") as run_inf, \
         patch.object(wrapper, "_translate_word_by_word", return_value="fixed") as word_by_word, \
         patch.object(wrapper, "_english_ratio", return_value=0.0), \
         patch.object(wrapper, "_updated_quality_score", return_value=0.9):
        result = wrapper._translate_item(
            "Hello world",
            src_lang="eng_Latn",
            tgt_lang="arb_Arab",
            num_beams=5,
            english_ratio_threshold=0.5,
        )

    assert result == "fixed"
    run_inf.assert_called()
    word_by_word.assert_called_once()


def test_invalid_fallback_mode_treated_as_stage2_only_via_settings():
    """Config validator maps unknown env values to stage2_only before model use."""
    import os

    os.environ["NMT_FALLBACK_MODE"] = "false"
    try:
        from app.config import Settings

        settings = Settings()
        assert settings.NMT_FALLBACK_MODE == "stage2_only"

        wrapper = NLLBTranslatorWrapper(config=settings)
        with patch.object(wrapper, "_run_inference", return_value="ok") as run_inf, \
             patch.object(wrapper, "_translate_word_by_word") as word_by_word, \
             patch.object(wrapper, "_english_ratio", return_value=0.0), \
             patch.object(wrapper, "_updated_quality_score", return_value=1.0):
            result = wrapper._translate_item(
                "Hello",
                src_lang="eng_Latn",
                tgt_lang="arb_Arab",
            )

        assert result == "ok"
        word_by_word.assert_not_called()
        run_inf.assert_called()
    finally:
        os.environ.pop("NMT_FALLBACK_MODE", None)
