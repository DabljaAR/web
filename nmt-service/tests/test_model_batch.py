"""Tests for batched NMT inference (F11)."""
from unittest.mock import MagicMock, PropertyMock, patch

from app.model import NLLBTranslatorWrapper


def _make_wrapper() -> NLLBTranslatorWrapper:
    cfg = MagicMock()
    cfg.NMT_FALLBACK_MODE = "stage2_only"
    cfg.HF_TOKEN = ""
    return NLLBTranslatorWrapper(config=cfg)


def test_run_inference_batch_calls_generate_once():
    wrapper = _make_wrapper()
    mock_tokenizer = MagicMock()
    mock_model = MagicMock()
    mock_tokenizer.convert_tokens_to_ids.return_value = 42
    mock_tokenizer.return_value.to.return_value = {"input_ids": "tensor"}
    mock_model.generate.return_value = ["out0", "out1"]
    mock_tokenizer.decode.side_effect = lambda out, **_: f"decoded-{out}"

    with patch.object(NLLBTranslatorWrapper, "tokenizer", new_callable=PropertyMock) as tp, \
         patch.object(NLLBTranslatorWrapper, "model", new_callable=PropertyMock) as mp, \
         patch.object(NLLBTranslatorWrapper, "device", new_callable=PropertyMock) as dp:
        tp.return_value = mock_tokenizer
        mp.return_value = mock_model
        dp.return_value = "cpu"
        results = wrapper._run_inference_batch(
            ["hello", "world"],
            "eng_Latn",
            "arb_Arab",
            max_length=128,
            num_beams=5,
        )

    assert results == ["decoded-out0", "decoded-out1"]
    mock_tokenizer.assert_called_once()
    tokenizer_kwargs = mock_tokenizer.call_args.kwargs
    assert tokenizer_kwargs["padding"] is True
    assert tokenizer_kwargs["truncation"] is True
    mock_model.generate.assert_called_once()


def test_translate_segments_batch_groups_by_src_lang():
    wrapper = _make_wrapper()

    with patch.object(
        wrapper,
        "_resolve_item_src_lang",
        side_effect=[
            ("eng_Latn", "one"),
            ("eng_Latn", "two"),
            ("fra_Latn", "trois"),
        ],
    ), patch.object(
        wrapper,
        "_run_inference_batch",
        side_effect=[
            ["ar-one", "ar-two"],
            ["ar-trois"],
        ],
    ) as batch_inf, patch.object(
        wrapper, "_english_ratio", return_value=0.0
    ), patch.object(
        wrapper, "_updated_quality_score", return_value=0.0
    ):
        results = wrapper.translate_segments_batch(
            ["one", "two", "trois"],
            tgt_lang="arb_Arab",
            batch_size=8,
        )

    assert results == ["ar-one", "ar-two", "ar-trois"]
    assert batch_inf.call_count == 2
    assert batch_inf.call_args_list[0].args[1] == "eng_Latn"
    assert batch_inf.call_args_list[1].args[1] == "fra_Latn"


def test_translate_segments_batch_returns_none_when_cancelled():
    wrapper = _make_wrapper()

    with patch.object(
        wrapper,
        "_resolve_item_src_lang",
        return_value=("eng_Latn", "hello"),
    ), patch.object(wrapper, "_run_inference_batch", return_value=["مرحبا"]):
        results = wrapper.translate_segments_batch(
            ["hello"],
            is_cancelled=lambda: True,
        )

    assert results is None
