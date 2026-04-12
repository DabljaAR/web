import os
import logging
import torch
from typing import List, Optional
from threading import Lock

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from langdetect import detect, DetectorFactory

from pathlib import Path
from app.media.storage import get_storage_service
from app.config import settings

# Seed for consistent langdetect results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_model_files(
    storage,
    file_key: str,
    local_path: Path,
    bucket_name: Optional[str] = None,
) -> bool:
    """
    Download all objects under *file_key* prefix into *local_path*.

    Uses ``StorageService.download_prefix`` (S3-compatible or local uploads dir).
    Safe in Celery: isolated ``asyncio.run()`` with no shared loop state.
    """
    import asyncio as _asyncio

    ok = _asyncio.run(
        storage.download_prefix(file_key, str(local_path), bucket_name=bucket_name or "")
    )
    if ok:
        logger.info(
            "[NMT] Downloaded model prefix=%s bucket=%s → %s",
            file_key,
            bucket_name or getattr(storage, "bucket_name", ""),
            local_path,
        )
    else:
        logger.warning(
            "[NMT] download_prefix returned no data for prefix=%s (bucket=%s)",
            file_key,
            bucket_name or getattr(storage, "bucket_name", ""),
        )
    return ok

# ---------------------------------------------------------------------------
# Model integrity validation
# ---------------------------------------------------------------------------

_REQUIRED_WEIGHT_FILES    = {"model.safetensors", "pytorch_model.bin"}
_REQUIRED_TOKENIZER_FILES = {"tokenizer.json", "tokenizer_config.json"}


def _validate_model_dir(path: str) -> bool:
    """Return True only if *path* contains at least one weight file and one tokenizer file."""
    if not os.path.isdir(path):
        return False
    files = set(os.listdir(path))
    return bool(files & _REQUIRED_WEIGHT_FILES) and bool(files & _REQUIRED_TOKENIZER_FILES)


def resolve_default_model() -> str:
    """
    Resolve the NMT model path using a priority chain:

    1. Local cache (``NMT_MODEL_LOCAL_PATH``) — fast, no network.
    2. Object storage download → populate local cache (requires ``STORAGE_BACKEND=s3`` + ``NMT_MODEL_KEY``).
    3. HuggingFace Hub (``NMT_HF_FALLBACK``) — requires internet access.
    """
    local_path  = settings.NMT_MODEL_LOCAL_PATH
    bucket      = settings.S3_MODELS_BUCKET
    key         = settings.NMT_MODEL_KEY
    hf_fallback = settings.NMT_HF_FALLBACK

    logger.info(
        "[NMT] Resolving model | local_path=%s bucket=%s key=%s",
        local_path, bucket, key,
    )

    # 1. Local cache hit — fastest path, no I/O beyond a directory listing
    if _validate_model_dir(local_path):
        logger.info("[NMT] Using verified local cache: %s", local_path)
        return local_path

    # 2. Object storage download (S3-compatible: MinIO, GCP interop, AWS)
    if settings.STORAGE_BACKEND.lower() == "s3" and key:
        logger.info(
            "[NMT] Downloading from object storage | bucket=%s key=%s → %s",
            bucket, key, local_path,
        )
        try:
            os.makedirs(local_path, exist_ok=True)
            storage = get_storage_service()
            _download_model_files(storage, key, Path(local_path), bucket_name=bucket)
            if _validate_model_dir(local_path):
                logger.info("[NMT] Object storage download complete — using %s", local_path)
                return local_path
            logger.warning(
                "[NMT] Object storage download finished but model validation failed at %s "
                "(missing weight or tokenizer files). Falling back to HF Hub.",
                local_path,
            )
        except Exception as exc:
            logger.error("[NMT] Object storage download failed: %s", exc)
    else:
        logger.warning(
            "[NMT] Skipping object-storage download (STORAGE_BACKEND=%r, NMT_MODEL_KEY=%r). "
            "Use STORAGE_BACKEND=s3 and set NMT_MODEL_KEY to use a custom model without internet access.",
            settings.STORAGE_BACKEND, key,
        )

    # 3. HuggingFace Hub — last resort
    logger.warning(
        "[NMT] Falling back to HuggingFace Hub: %s. "
        "Configure S3_MODELS_BUCKET + NMT_MODEL_KEY to avoid this.",
        hf_fallback,
    )
    return hf_fallback


# ===========================================================================
# NLLBTranslatorWrapper
# ===========================================================================

class NLLBTranslatorWrapper:
    """
    Wrapper for NLLB model, following the lazy-loading pattern of WhisperModelManager.
    One instance of the model/tokenizer is shared across instances of the wrapper.
    """
    _model = None
    _tokenizer = None
    _lock = Lock()

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name
        self._device     = None

    @property
    def model_name(self) -> str:
        if self._model_name is None:
            self._model_name = resolve_default_model()
        return self._model_name

    @property
    def device(self) -> str:
        """Lazy resolve device to avoid premature CUDA initialization in Celery parent."""
        if self._device is None:
            self._device = self._get_device()
        return self._device

    @property
    def tokenizer(self):
        """Lazy load the tokenizer once."""
        if NLLBTranslatorWrapper._tokenizer is None:
            with NLLBTranslatorWrapper._lock:
                if NLLBTranslatorWrapper._tokenizer is None:
                    logger.info("[NMT] Loading tokenizer from '%s'", self.model_name)
                    _local = os.path.isdir(self.model_name)
                    NLLBTranslatorWrapper._tokenizer = AutoTokenizer.from_pretrained(
                        self.model_name,
                        local_files_only=_local,
                        token=settings.HF_TOKEN or None,
                    )
        return NLLBTranslatorWrapper._tokenizer

    @property
    def model(self):
        """Lazy load the NLLB model once."""
        if NLLBTranslatorWrapper._model is None:
            with NLLBTranslatorWrapper._lock:
                if NLLBTranslatorWrapper._model is None:
                    logger.info("[NMT] Loading model from '%s' on %s", self.model_name, self.device)
                    _local = os.path.isdir(self.model_name)

                    # float16 saves ~1.3 GB VRAM on GPU
                    model_kwargs: dict = {
                        "local_files_only": _local,
                        "token": settings.HF_TOKEN or None,
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
            # Return cuda:0 if available, bypassing the strict arch check
            # which sometimes omits sm_61 even if compatible cards are present.
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

    def _run_inference(self, text: str, src_lang: str, tgt_lang: str, max_length: int) -> str:
        """Performs model inference for a single text string."""
        self.tokenizer.src_lang = src_lang
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_lang),
            max_length=max_length,
            num_beams=5,
            early_stopping=True
        )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def _translate_item(self, text: str, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512) -> str:
        """Translates a single string after detecting its language."""
        # 0. Robust language mapping (ensures "ar" -> "arb_Arab")
        tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if src_lang:
            src_lang = self.LANG_MAP.get(src_lang, src_lang)

        stripped = text.strip()
        if not stripped:
            return text

        # 1. Detect language
        try:
            detected_code = detect(stripped)
            item_src_lang = self.LANG_MAP.get(detected_code)
            
            # Prevent misdetecting English as Arabic if Latin chars exist
            has_latin = any('a' <= c <= 'z' or 'A' <= c <= 'Z' for c in stripped)
            if has_latin and item_src_lang == "arb_Arab":
                item_src_lang = "eng_Latn"
            
            if not item_src_lang:
                item_src_lang = src_lang or "eng_Latn"
        except Exception:
            item_src_lang = src_lang or "eng_Latn"

        # 2. Skip if already in target language
        if item_src_lang == tgt_lang:
            return text

        # 3. Translate
        return self._run_inference(stripped, item_src_lang, tgt_lang, max_length)

    def _translate_segments(self, segments: List[dict], src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512):
        """Translates list of segments one by one in a simple loop."""
        if not segments:
            return
            
        for segment in segments:
            text = segment.get("text", "")
            if text:
                segment["text"] = self._translate_item(text, src_lang, tgt_lang, max_length)

    def translate_stt_result(self, stt_result: dict, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512):
        """
        Translates a full STT result (transcript and segments).
        Iterates through segments one by one for maximum simplicity.
        """
        if not stt_result:
            return stt_result

        # Map short target/source lang code to long NLLB format
        full_tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if not full_tgt_lang and len(tgt_lang) == 2:
             full_tgt_lang = tgt_lang
             
        full_src_lang = None
        if src_lang:
            full_src_lang = self.LANG_MAP.get(src_lang, src_lang)

        # 1. Process Segments one by one
        segments = stt_result.get("segments", [])
        if segments:
            self._translate_segments(segments, full_src_lang, full_tgt_lang, max_length)
            
            # 2. Reconstruct transcript from translated segments
            stt_result["transcript"] = " ".join([s.get("text", "") for s in segments]).strip()
        
        else:
            # 3. Fallback: Translate transcript if no segments
            transcript = stt_result.get("transcript", "")
            if transcript:
                stt_result["transcript"] = self._translate_item(transcript, full_src_lang, full_tgt_lang, max_length)
        
        # 4. Update metadata language
        if "metadata" in stt_result and isinstance(stt_result["metadata"], dict):
            stt_result["metadata"]["language"] = tgt_lang
            
        return stt_result
