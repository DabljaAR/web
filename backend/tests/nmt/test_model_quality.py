from unittest.mock import patch

from app.nmt.model import NLLBTranslatorWrapper


class TestNmtQualityHelpers:
    def test_arabic_script_ratio_pure_arabic(self):
        assert NLLBTranslatorWrapper._arabic_script_ratio("مرحبا بالعالم") == 1.0

    def test_arabic_script_ratio_pure_english(self):
        assert NLLBTranslatorWrapper._arabic_script_ratio("hello world") == 0.0

    def test_arabic_script_ratio_mixed(self):
        ratio = NLLBTranslatorWrapper._arabic_script_ratio("hello مرحبا")
        assert 0.3 < ratio < 0.7

    def test_arabic_script_ratio_ignores_non_letters(self):
        assert NLLBTranslatorWrapper._arabic_script_ratio("1234 !!! 😊") == 0.0

    def test_mixed_token_penalty_detects_mixed_script_token(self):
        penalty = NLLBTranslatorWrapper._mixed_token_penalty("Redis multi-النموذج")
        assert penalty > 0.0

    def test_mixed_token_penalty_zero_for_clean_tokens(self):
        penalty = NLLBTranslatorWrapper._mixed_token_penalty("مرحبا بالعالم")
        assert penalty == 0.0


class TestNmtFallbackModeBehavior:
    def test_stage2_only_skips_stage3_word_by_word(self):
        translator = NLLBTranslatorWrapper(model_name="dummy")

        with patch("app.nmt.model.detect", return_value="en"), \
             patch("app.nmt.model.settings.NMT_FALLBACK_MODE", "stage2_only"), \
             patch.object(translator, "_run_inference", side_effect=["Hello world", "Hello world again"]), \
             patch.object(translator, "_translate_word_by_word") as wbw:
            result = translator._translate_item(
                "source text",
                src_lang="eng_Latn",
                tgt_lang="arb_Arab",
                english_ratio_threshold=0.5,
            )

        wbw.assert_not_called()
        assert result == "Hello world again"

    def test_stage3_updated_can_run_word_by_word(self):
        translator = NLLBTranslatorWrapper(model_name="dummy")

        with patch("app.nmt.model.detect", return_value="en"), \
             patch("app.nmt.model.settings.NMT_FALLBACK_MODE", "stage3_updated"), \
             patch.object(translator, "_run_inference", side_effect=["Hello world", "Redis multi-النموذج"]), \
             patch.object(translator, "_translate_word_by_word", return_value="نتيجة عربية") as wbw:
            result = translator._translate_item(
                "source text",
                src_lang="eng_Latn",
                tgt_lang="arb_Arab",
                english_ratio_threshold=0.5,
            )

        wbw.assert_called_once()
        assert result == "نتيجة عربية"
