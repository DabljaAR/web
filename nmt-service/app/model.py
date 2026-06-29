"""NLLB inference wrapper for the NMT microservice.

Loads the model lazily on first translation request and reuses it across jobs.
Model resolution: local cache → S3 download → HuggingFace Hub fallback.
"""
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Callable, List, Optional

import boto3
import torch
from botocore.config import Config as BotoConfig
from dablja_worker.s3_model_download import download_s3_prefix
from langdetect import detect, DetectorFactory
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.config import settings

DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

_REQUIRED_WEIGHT_FILES = {"model.safetensors", "pytorch_model.bin"}
_REQUIRED_TOKENIZER_FILES = {"tokenizer.json", "tokenizer_config.json"}


def _s3_download_fn(prefix: str, local_path: str, bucket: str) -> bool:
    """Download NMT weights from object storage by prefix (parallel per-key downloads)."""
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
            "[NMT] Downloaded %d files from s3://%s/%s → %s",
            downloaded, bucket, prefix.strip("/"), local_path,
        )
    return downloaded > 0


def _validate_model_dir(path: str) -> bool:
    """Return True only if *path* contains at least one weight file and one tokenizer file."""
    if not os.path.isdir(path):
        return False
    files = set(os.listdir(path))
    return bool(files & _REQUIRED_WEIGHT_FILES) and bool(files & _REQUIRED_TOKENIZER_FILES)


def resolve_default_model(
    config=None,
    download_fn: Optional[Callable] = None,
) -> tuple[str, str]:
    """Resolve NMT model path: local cache → object storage → HuggingFace Hub."""
    config = config or settings
    download_fn = download_fn or _s3_download_fn

    local_path = config.NMT_MODEL_LOCAL_PATH
    bucket = config.S3_MODELS_BUCKET
    key = config.NMT_MODEL_KEY
    hf_fallback = config.NMT_HF_FALLBACK

    logger.info("[NMT] Resolving model | local_path=%s bucket=%s key=%s", local_path, bucket, key)

    if _validate_model_dir(local_path):
        logger.info("[NMT][CACHE] source=local_disk_hit path=%s", local_path)
        return local_path, "local_disk_hit"

    if config.STORAGE_BACKEND.lower() == "s3" and key:
        logger.info("[NMT] Downloading from object storage | bucket=%s key=%s → %s", bucket, key, local_path)
        try:
            os.makedirs(local_path, exist_ok=True)
            ok = download_fn(key, local_path, bucket)
            if ok and _validate_model_dir(local_path):
                logger.info("[NMT][CACHE] source=s3_hit path=%s", local_path)
                return local_path, "s3_hit"
            logger.warning("[NMT] S3 download done but model validation failed at %s", local_path)
        except Exception as exc:
            logger.error("[NMT] Object storage download failed: %s", exc)
    else:
        logger.warning(
            "[NMT] Skipping object-storage download (STORAGE_BACKEND=%r, NMT_MODEL_KEY=%r).",
            config.STORAGE_BACKEND, key,
        )

    logger.warning("[NMT] Falling back to HuggingFace Hub: %s", hf_fallback)
    if not getattr(config, "NMT_ALLOW_HF_FALLBACK", False):
        raise RuntimeError(
            f"NMT model not available at {local_path!r} and HuggingFace fallback is disabled "
            f"(NMT_ALLOW_HF_FALLBACK=false). Upload the model to S3 or populate the local cache."
        )
    logger.info("[NMT][CACHE] source=hf_fallback model=%s", hf_fallback)
    return hf_fallback, "hf_fallback"


class NLLBTranslatorWrapper:
    """Lazy-loaded NLLB model shared across worker and HTTP endpoints."""

    _model = None
    _tokenizer = None
    _lock = Lock()
    _tokenizer_lock = Lock()

    def __init__(
        self,
        model_name: Optional[str] = None,
        config=None,
        download_fn: Optional[Callable] = None,
    ):
        self._model_name = model_name
        self._config = config or settings
        self._download_fn = download_fn or _s3_download_fn
        self._model_source: Optional[str] = None
        self._device: Optional[str] = None

    def _cfg(self):
        return self._config

    @property
    def model_name(self) -> str:
        if self._model_name is None:
            self._model_name, self._model_source = resolve_default_model(
                config=self._cfg(), download_fn=self._download_fn
            )
        return self._model_name

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = self._get_device()
        return self._device

    @property
    def tokenizer(self):
        if NLLBTranslatorWrapper._tokenizer is not None:
            logger.info("[NMT][CACHE] source=in_memory_hit component=tokenizer")
            return NLLBTranslatorWrapper._tokenizer

        if NLLBTranslatorWrapper._tokenizer is None:
            with NLLBTranslatorWrapper._lock:
                if NLLBTranslatorWrapper._tokenizer is None:
                    logger.info("[NMT] Loading tokenizer from '%s'", self.model_name)
                    _local = os.path.isdir(self.model_name)
                    NLLBTranslatorWrapper._tokenizer = AutoTokenizer.from_pretrained(
                        self.model_name,
                        local_files_only=_local,
                        token=self._cfg().HF_TOKEN or None,
                    )
        return NLLBTranslatorWrapper._tokenizer

    @property
    def model(self):
        if NLLBTranslatorWrapper._model is not None:
            logger.info("[NMT][CACHE] source=in_memory_hit component=model")
            return NLLBTranslatorWrapper._model

        if NLLBTranslatorWrapper._model is None:
            with NLLBTranslatorWrapper._lock:
                if NLLBTranslatorWrapper._model is None:
                    logger.info(
                        "[NMT] Loading model from '%s' on %s | cache_source=%s",
                        self.model_name,
                        self.device,
                        self._model_source or "unknown",
                    )
                    _local = os.path.isdir(self.model_name)

                    model_kwargs: dict = {
                        "local_files_only": _local,
                        "token": self._cfg().HF_TOKEN or None,
                    }
                    if "cuda" in self.device:
                        model_kwargs["torch_dtype"] = torch.float16

                    NLLBTranslatorWrapper._model = AutoModelForSeq2SeqLM.from_pretrained(
                        self.model_name,
                        **model_kwargs,
                    ).to(self.device)
                    logger.info("[NMT] Model loaded successfully (float16 if GPU)")
        return NLLBTranslatorWrapper._model

    def _get_device(self):
        if torch.cuda.is_available():
            return "cuda:0"
        return "cpu"

    LANG_MAP = {
        "en": "eng_Latn",
        "ar": "arb_Arab",
        "fr": "fra_Latn",
        "es": "spa_Latn",
        "de": "deu_Latn",
        "it": "ita_Latn",
        "pt": "por_Latn",
        "ru": "rus_Cyrl",
        "zh": "zho_Hans",
        "ja": "jpn_Jpan",
        "ko": "kor_Hang",
    }

    @staticmethod
    def _is_english_word(word: str) -> bool:
        return any(c.isascii() and c.isalpha() for c in word)

    @staticmethod
    def _english_ratio(text: str) -> float:
        words = text.split()
        if not words:
            return 0.0
        return sum(NLLBTranslatorWrapper._is_english_word(w) for w in words) / len(words)

    @staticmethod
    def _is_arabic_letter(char: str) -> bool:
        code = ord(char)
        return (
            0x0600 <= code <= 0x06FF
            or 0x0750 <= code <= 0x077F
            or 0x08A0 <= code <= 0x08FF
            or 0xFB50 <= code <= 0xFDFF
            or 0xFE70 <= code <= 0xFEFF
        )

    @staticmethod
    def _arabic_script_ratio(text: str) -> float:
        arabic_letters = 0
        alphabetic_letters = 0

        for char in text:
            if char.isalpha():
                alphabetic_letters += 1
                if NLLBTranslatorWrapper._is_arabic_letter(char):
                    arabic_letters += 1

        if alphabetic_letters == 0:
            return 0.0
        return arabic_letters / alphabetic_letters

    @staticmethod
    def _mixed_token_penalty(text: str) -> float:
        tokens = text.split()
        if not tokens:
            return 0.0

        eligible_tokens = 0
        mixed_tokens = 0
        for token in tokens:
            has_ascii_alpha = any(c.isascii() and c.isalpha() for c in token)
            has_arabic_alpha = any(
                NLLBTranslatorWrapper._is_arabic_letter(c) for c in token
            )

            if has_ascii_alpha or has_arabic_alpha:
                eligible_tokens += 1
                if has_ascii_alpha and has_arabic_alpha:
                    mixed_tokens += 1

        if eligible_tokens == 0:
            return 0.0
        return mixed_tokens / eligible_tokens

    @staticmethod
    def _updated_quality_score(text: str) -> float:
        arabic_ratio = NLLBTranslatorWrapper._arabic_script_ratio(text)
        mixed_penalty = NLLBTranslatorWrapper._mixed_token_penalty(text)
        return min(1.0, (1.0 - arabic_ratio) + mixed_penalty)

    def _resolve_item_src_lang(
        self,
        text: str,
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
    ) -> tuple[Optional[str], str]:
        """Return (src_lang, stripped). None src_lang means skip translation."""
        tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if src_lang:
            src_lang = self.LANG_MAP.get(src_lang, src_lang)

        stripped = text.strip()
        if not stripped:
            return None, text

        try:
            detected_code = detect(stripped)
            item_src_lang = self.LANG_MAP.get(detected_code)

            has_latin = any("a" <= c <= "z" or "A" <= c <= "Z" for c in stripped)
            if has_latin and item_src_lang == "arb_Arab":
                item_src_lang = "eng_Latn"

            if not item_src_lang:
                item_src_lang = src_lang or "eng_Latn"
        except Exception:
            item_src_lang = src_lang or "eng_Latn"

        if item_src_lang == tgt_lang:
            return None, stripped

        return item_src_lang, stripped

    def _translate_word_by_word(self, text: str, src_lang: str, tgt_lang: str) -> str:
        translated_words = []
        tgt_token_id = self.tokenizer.convert_tokens_to_ids(tgt_lang)
        for word in text.split():
            with NLLBTranslatorWrapper._tokenizer_lock:
                self.tokenizer.src_lang = src_lang
                inputs = self.tokenizer(word, return_tensors="pt").to(self.device)
            outputs = self.model.generate(
                **inputs,
                forced_bos_token_id=tgt_token_id,
                max_length=20,
                num_beams=1,
            )
            translated_words.append(self.tokenizer.decode(outputs[0], skip_special_tokens=True))
        return " ".join(translated_words)

    def _run_inference(
        self,
        text: str,
        src_lang: str,
        tgt_lang: str,
        max_length: int,
        num_beams: int = 5,
    ) -> str:
        tgt_token_id = self.tokenizer.convert_tokens_to_ids(tgt_lang)
        with NLLBTranslatorWrapper._tokenizer_lock:
            self.tokenizer.src_lang = src_lang
            inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=tgt_token_id,
            max_length=max_length,
            num_beams=num_beams,
            early_stopping=True,
        )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def _run_inference_batch(
        self,
        texts: list[str],
        src_lang: str,
        tgt_lang: str,
        max_length: int,
        num_beams: int = 5,
    ) -> list[str]:
        if not texts:
            return []

        tgt_token_id = self.tokenizer.convert_tokens_to_ids(tgt_lang)
        with NLLBTranslatorWrapper._tokenizer_lock:
            self.tokenizer.src_lang = src_lang
            inputs = self.tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            ).to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=tgt_token_id,
            max_length=max_length,
            num_beams=num_beams,
            early_stopping=True,
        )
        return [
            self.tokenizer.decode(out, skip_special_tokens=True)
            for out in outputs
        ]

    def translate_segment(
        self,
        text: str,
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
        max_length: int = 512,
        num_beams: int = 5,
        english_ratio_threshold: float = 0.5,
    ) -> str:
        return self._translate_item(
            text, src_lang, tgt_lang, max_length, num_beams, english_ratio_threshold
        )

    def _translate_item(
        self,
        text: str,
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
        max_length: int = 512,
        num_beams: int = 5,
        english_ratio_threshold: float = 0.5,
    ) -> str:
        tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if src_lang:
            src_lang = self.LANG_MAP.get(src_lang, src_lang)

        item_src_lang, stripped = self._resolve_item_src_lang(text, src_lang, tgt_lang)
        if item_src_lang is None:
            return text

        result = self._run_inference(stripped, item_src_lang, tgt_lang, max_length, num_beams)
        logger.debug(
            "[NMT] stage-1 beams=%d english_ratio=%.2f | %r",
            num_beams, self._english_ratio(result), stripped[:60],
        )

        if num_beams != 1 and self._english_ratio(result) > english_ratio_threshold:
            logger.info(
                "[NMT] stage-2: english_ratio high (%.2f) → retrying num_beams=1",
                self._english_ratio(result),
            )
            result = self._run_inference(stripped, item_src_lang, tgt_lang, max_length, num_beams=1)

        fallback_mode = self._cfg().NMT_FALLBACK_MODE
        if fallback_mode == "stage2_only":
            logger.debug("[NMT] stage-3 skipped (NMT_FALLBACK_MODE=stage2_only)")
            return result

        updated_score = self._updated_quality_score(result)
        if updated_score > english_ratio_threshold:
            logger.info(
                "[NMT] stage-3: updated_score high (%.2f) → word-by-word",
                updated_score,
            )
            result = self._translate_word_by_word(stripped, item_src_lang, tgt_lang)

        return result

    def translate_segments_batch(
        self,
        texts: list[str],
        *,
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
        max_length: int = 512,
        num_beams: int = 5,
        english_ratio_threshold: float = 0.5,
        batch_size: int = 8,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Optional[list[str]]:
        """Translate many segments with batched generate(), grouped by detected src_lang."""
        if not texts:
            return []

        full_tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        results: list[str] = list(texts)
        work_items: list[tuple[int, str, str]] = []

        for idx, text in enumerate(texts):
            item_src_lang, stripped = self._resolve_item_src_lang(text, src_lang, full_tgt_lang)
            if item_src_lang is None:
                continue
            work_items.append((idx, stripped, item_src_lang))

        by_src_lang: dict[str, list[tuple[int, str]]] = {}
        for idx, stripped, item_src_lang in work_items:
            by_src_lang.setdefault(item_src_lang, []).append((idx, stripped))

        effective_batch_size = max(1, batch_size)
        fallback_mode = self._cfg().NMT_FALLBACK_MODE

        for item_src_lang, items in by_src_lang.items():
            for batch_start in range(0, len(items), effective_batch_size):
                if is_cancelled and is_cancelled():
                    return None

                batch = items[batch_start : batch_start + effective_batch_size]
                indices = [idx for idx, _ in batch]
                batch_texts = [stripped for _, stripped in batch]

                try:
                    batch_results = self._run_inference_batch(
                        batch_texts,
                        item_src_lang,
                        full_tgt_lang,
                        max_length,
                        num_beams,
                    )
                except Exception as exc:
                    logger.warning(
                        "[NMT] batch inference failed (%d segments), falling back per-segment: %s",
                        len(batch_texts),
                        exc,
                    )
                    batch_results = [
                        self._run_inference(
                            stripped,
                            item_src_lang,
                            full_tgt_lang,
                            max_length,
                            num_beams,
                        )
                        for stripped in batch_texts
                    ]

                stage2_indices: list[int] = []
                stage2_texts: list[str] = []
                for local_idx, global_idx in enumerate(indices):
                    result = batch_results[local_idx]
                    if num_beams != 1 and self._english_ratio(result) > english_ratio_threshold:
                        stage2_indices.append(global_idx)
                        stage2_texts.append(batch_texts[local_idx])
                    else:
                        results[global_idx] = result

                if stage2_texts:
                    try:
                        stage2_results = self._run_inference_batch(
                            stage2_texts,
                            item_src_lang,
                            full_tgt_lang,
                            max_length,
                            num_beams=1,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[NMT] stage-2 batch failed (%d segments), falling back per-segment: %s",
                            len(stage2_texts),
                            exc,
                        )
                        stage2_results = [
                            self._run_inference(
                                stripped,
                                item_src_lang,
                                full_tgt_lang,
                                max_length,
                                num_beams=1,
                            )
                            for stripped in stage2_texts
                        ]

                    for global_idx, result in zip(stage2_indices, stage2_results):
                        results[global_idx] = result

                if fallback_mode != "stage2_only":
                    for global_idx, stripped in zip(indices, batch_texts):
                        result = results[global_idx]
                        if self._updated_quality_score(result) > english_ratio_threshold:
                            logger.info(
                                "[NMT] stage-3: updated_score high (%.2f) → word-by-word seg=%d",
                                self._updated_quality_score(result),
                                global_idx,
                            )
                            results[global_idx] = self._translate_word_by_word(
                                stripped, item_src_lang, full_tgt_lang
                            )

        return results

    def _translate_segments(
        self,
        segments: List[dict],
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
        max_length: int = 512,
    ):
        if not segments:
            return

        for segment in segments:
            text = segment.get("text", "")
            if text:
                segment["text"] = self._translate_item(text, src_lang, tgt_lang, max_length)

    def translate_stt_result(
        self,
        stt_result: dict,
        src_lang: Optional[str] = None,
        tgt_lang: str = "arb_Arab",
        max_length: int = 512,
    ):
        if not stt_result:
            return stt_result

        full_tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if not full_tgt_lang and len(tgt_lang) == 2:
            full_tgt_lang = tgt_lang

        full_src_lang = None
        if src_lang:
            full_src_lang = self.LANG_MAP.get(src_lang, src_lang)

        segments = stt_result.get("segments", [])
        if segments:
            self._translate_segments(segments, full_src_lang, full_tgt_lang, max_length)
            stt_result["transcript"] = " ".join(s.get("text", "") for s in segments).strip()
        else:
            transcript = stt_result.get("transcript", "")
            if transcript:
                stt_result["transcript"] = self._translate_item(
                    transcript, full_src_lang, full_tgt_lang, max_length
                )

        if "metadata" in stt_result and isinstance(stt_result["metadata"], dict):
            stt_result["metadata"]["language"] = tgt_lang

        return stt_result
