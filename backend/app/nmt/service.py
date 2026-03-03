import os
import logging
import asyncio
import torch
from typing import List, Optional

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from langdetect import detect, DetectorFactory
from sqlalchemy.ext.asyncio import AsyncSession

# Seed for consistent langdetect results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# v4 model path - Priority for finetuned model
MODEL_MOUNT_V4 = os.path.expanduser("~/minio-model/model")

DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"

def resolve_default_model():
    """
    Decide which model to use based on available paths.
    """
    global DEFAULT_MODEL
    if os.path.exists(MODEL_MOUNT_V4):
        DEFAULT_MODEL = MODEL_MOUNT_V4
        logger.info(f"Using model from mounted drive: {DEFAULT_MODEL}")
    elif os.path.exists("nllb-edu-en-ar-finetuned-v3"):
        DEFAULT_MODEL = "nllb-edu-en-ar-finetuned-v3"
    else:
        DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"
    return DEFAULT_MODEL


class NLLBTranslatorWrapper:
    """
    Wrapper for NLLB model, adapted from demo_translation.py
    Simplified to translate segments one by one.
    """
    def __init__(self, model_name=DEFAULT_MODEL):
        self.model_name = model_name
        self.device = self._get_device()
        logger.info(f"Loading tokenizer and model from '{model_name}' on {self.device}...")
        local_files_only = os.path.isdir(model_name)
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            local_files_only=local_files_only
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name, 
            local_files_only=local_files_only
        ).to(self.device)
        
    def _get_device(self):
        if torch.cuda.is_available():
            try:
                major, minor = torch.cuda.get_device_capability()
                gpu_arch = f"sm_{major}{minor}"
                if gpu_arch in torch.cuda.get_arch_list():
                    return "cuda:0"
            except Exception:
                pass
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
            num_beams=2,
            early_stopping=True
        )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def _translate_item(self, text: str, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512) -> str:
        """Translates a single string after detecting its language."""
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

    def translate(self, text: str, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512) -> str:
        """Translates multi-line text by processing line by line."""
        if not text:
            return ""
        
        lines = text.splitlines()
        translated_lines = [self._translate_item(line, src_lang, tgt_lang, max_length) for line in lines]
        return "\n".join(translated_lines)

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
                stt_result["transcript"] = self.translate(transcript, full_src_lang, full_tgt_lang, max_length)
        
        # 4. Update metadata language
        if "metadata" in stt_result and isinstance(stt_result["metadata"], dict):
            stt_result["metadata"]["language"] = tgt_lang
            
        return stt_result


# Singleton for translator
_translator = None
_translation_lock = asyncio.Lock()

def get_translator():
    global _translator
    if _translator is None:
        model_name = resolve_default_model()
        logger.info(f"Initializing NLLBTranslatorWrapper with model '{model_name}'...")
        _translator = NLLBTranslatorWrapper(model_name=model_name)
    return _translator

async def init_nmt():
    """Pre-load the translator during startup."""
    resolve_default_model()
    await asyncio.to_thread(get_translator)


class TranslationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def translate_stt_result(self, stt_data: dict, target_lang: str, source_lang: Optional[str] = None):
        """Translates STT results without batching or chunking."""
        translator = await asyncio.to_thread(get_translator)
        return await asyncio.to_thread(
            translator.translate_stt_result,
            stt_data,
            src_lang=source_lang,
            tgt_lang=target_lang
        )
