import re
import os
import uuid
import logging
import asyncio
import tempfile
import torch
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from langdetect import detect, DetectorFactory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.nmt.models import Translation, TranslationStatus
from app.media.models import Video, MediaType
from app.media.storage import get_storage_service
from app.core.db import AsyncSessionLocal

# Seed for consistent langdetect results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# v4 model path - Priority for finetuned model
# Since we are using FUSE (s3fs), the MinIO bucket is mounted to a local folder.
# We mount the 'dablajaar' bucket into '~/minio-model'.
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

    def _translate_list(self, texts: List[str], src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512) -> List[str]:
        """
        Translates a list of strings efficiently by:
        1. Detecting language per item.
        2. Chunking items that exceed 100 tokens.
        3. Batching short items by source language for model inference.
        """
        if not texts:
            return []
        
        results = [None] * len(texts)
        to_translate_groups = {}
        
        for idx, text in enumerate(texts):
            stripped = text.strip()
            if not stripped:
                results[idx] = text # Preserve empty strings
                continue
            
            # 1. Detect language for this specific text
            try:
                detected_code = detect(stripped)
                line_src_lang = self.LANG_MAP.get(detected_code)
                
                # Check for Latin characters to prevent misdetecting English as Arabic
                has_latin = bool(re.search(r'[a-zA-Z]', stripped))
                if has_latin and line_src_lang == "arb_Arab":
                    line_src_lang = "eng_Latn"
                
                if not line_src_lang:
                    line_src_lang = src_lang or "eng_Latn"
            except Exception:
                line_src_lang = src_lang or "eng_Latn"
                
            # 2. If already in target language, don't translate
            if line_src_lang == tgt_lang:
                results[idx] = text
                continue
                
            # 3. Check for long text chunking (token count > 100)
            tokens = self.tokenizer(stripped, return_tensors="pt")
            if tokens.input_ids.shape[1] > 100:
                results[idx] = self._translate_long_text(stripped, line_src_lang, tgt_lang, max_length)
                continue

            # 4. Group by source language for batching
            if line_src_lang not in to_translate_groups:
                to_translate_groups[line_src_lang] = []
            to_translate_groups[line_src_lang].append((idx, stripped))

        # Process each language group in batches
        for lang_code, items in to_translate_groups.items():
            self.tokenizer.src_lang = lang_code
            indices = [item[0] for item in items]
            texts_to_batch = [item[1] for item in items]
            
            batch_size = 4
            for i in range(0, len(texts_to_batch), batch_size):
                batch_texts = texts_to_batch[i:i + batch_size]
                batch_indices = indices[i:i + batch_size]
                translated_batch = self._run_inference_batch(batch_texts, tgt_lang, max_length)
                for local_idx, translated_text in enumerate(translated_batch):
                    results[batch_indices[local_idx]] = translated_text
                    
        return [res if res is not None else texts[i] for i, res in enumerate(results)]

    def translate(self, text: str, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512):
        """
        Translates text by detecting language per line. 
        This is CRITICAL for finetuned models that fail on mixed-language input.
        """
        if not text:
            return ""
        
        lines = text.splitlines()
        translated_lines = self._translate_list(lines, src_lang=src_lang, tgt_lang=tgt_lang, max_length=max_length)
        return "\n".join(translated_lines)

    def _run_inference_batch(self, texts, tgt_lang, max_length):
        """Internal method to perform batch model inference."""
        inputs = self.tokenizer(texts, return_tensors="pt", padding=True, truncation=True).to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_lang),
            max_length=max_length,
            num_beams=2,  # Faster on CPU
            early_stopping=True
        )
        return self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

    def _translate_long_text(self, text, src_lang, tgt_lang, max_length):
        """Chunking logic to handle very long single lines."""
        self.tokenizer.src_lang = src_lang
        words = text.split(' ')
        chunks = []
        current_words = []
        
        # Safe threshold for finetuned models is around 80-100 tokens
        chunk_threshold = 100
        
        for word in words:
            if not word: continue
            test_words = current_words + [word]
            test_str = " ".join(test_words)
            token_count = self.tokenizer(test_str, return_tensors="pt").input_ids.shape[1]
            
            if token_count > chunk_threshold:
                if current_words:
                    chunk_str = " ".join(current_words)
                    # Use batch method for single chunk
                    chunks.append(self._run_inference_batch([chunk_str], tgt_lang, max_length)[0])
                    current_words = [word]
                else:
                    # Single word is too long (rare but possible)
                    chunks.append(self._run_inference_batch([word], tgt_lang, max_length)[0])
                    current_words = []
            else:
                current_words = test_words
        
        if current_words:
            chunk_str = " ".join(current_words)
            chunks.append(self._run_inference_batch([chunk_str], tgt_lang, max_length)[0])
            
        return " ".join(chunks)

    def _translate_segments(self, segments: List[dict], src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512):
        """Translates STT segments efficiently using batching and chunking."""
        if not segments:
            return
            
        texts = [s.get("text", "") for s in segments]
        translated_texts = self._translate_list(texts, src_lang=src_lang, tgt_lang=tgt_lang, max_length=max_length)
        
        for i, segment in enumerate(segments):
            if i < len(translated_texts):
                segment["text"] = translated_texts[i]

    def translate_stt_result(self, stt_result: dict, src_lang: Optional[str] = None, tgt_lang: str = "arb_Arab", max_length: int = 512):
        """
        Translates a full STT result (transcript and segments) while maintaining structure.
        Ensures perfect alignment by translating segments first and reconstructing transcript.
        """
        if not stt_result:
            return stt_result

        # Map short target/source lang code to long NLLB format if needed (e.g., 'ar' -> 'arb_Arab')
        full_tgt_lang = self.LANG_MAP.get(tgt_lang, tgt_lang)
        if not full_tgt_lang and len(tgt_lang) == 2:
             full_tgt_lang = tgt_lang
             
        full_src_lang = None
        if src_lang:
            full_src_lang = self.LANG_MAP.get(src_lang, src_lang)

        # 1. Process Segments
        segments = stt_result.get("segments", [])
        if segments:
            # Efficiently translate all segments at once (batching + chunking)
            self._translate_segments(
                segments, 
                src_lang=full_src_lang, 
                tgt_lang=full_tgt_lang, 
                max_length=max_length
            )
            
            # 2. RECONSTRUCT Transcript (Higher quality, perfect alignment)
            stt_result["transcript"] = " ".join([s.get("text", "") for s in segments]).strip()
        
        else:
            # 3. FALLBACK: Translate Transcript if segments are missing
            transcript = stt_result.get("transcript", "")
            if transcript:
                stt_result["transcript"] = self.translate(
                    transcript, 
                    src_lang=full_src_lang, 
                    tgt_lang=full_tgt_lang, 
                    max_length=max_length
                )
        
        # 4. Update metadata language if present
        if "metadata" in stt_result and isinstance(stt_result["metadata"], dict):
            stt_result["metadata"]["language"] = tgt_lang
            
        return stt_result


# Singleton for translator to avoid reloading model on every request
_translator = None
_translation_lock = asyncio.Lock()

def get_translator():
    global _translator
    if _translator is None:
        model_name = resolve_default_model()
        logger.info(f"Initializing NLLBTranslatorWrapper with model '{model_name}' (this may take a while)...")
        _translator = NLLBTranslatorWrapper(model_name=model_name)
    return _translator

async def init_nmt():
    """
    Pre-load the translator during startup.
    """
    # Simply decide which model to use based on mounted path
    resolve_default_model()
    
    await asyncio.to_thread(get_translator)

async def process_translation_task(translation_id: str):
    """
    Background task for NMT processing.
    Ensures model loading and inference happen in a separate thread to avoid blocking the event loop.
    Uses a lock to prevent concurrent translations from overwhelming memory/GPU.
    """
    logger.info(f"NMT task queued: {translation_id}")
    
    async with _translation_lock:
        logger.info(f"Starting NMT processing for translation {translation_id}")
        storage = get_storage_service()
        
        # Load model in thread if not already loaded
        translator = await asyncio.to_thread(get_translator)
        
        async with AsyncSessionLocal() as db:
            try:
                translation = await db.get(Translation, translation_id)
                if not translation:
                    return
                
                translation.status = TranslationStatus.PROCESSING
                await db.commit()

                # 1. Prepare Workspace
                with tempfile.TemporaryDirectory() as temp_dir:
                    source_local_path = Path(temp_dir) / "source.txt"
                    translated_local_path = Path(temp_dir) / "translated.txt"
                    
                    # 2. Download source file
                    await storage.download(translation.source_text_path, str(source_local_path))
                    
                    # 3. Read content
                    with open(source_local_path, "r", encoding="utf-8") as f:
                        source_content = f.read()
                    
                    # 4. Translate in a separate thread
                    translated_content = await asyncio.to_thread(
                        translator.translate,
                        source_content, 
                        src_lang=translation.source_lang, 
                        tgt_lang=translation.target_lang
                    )
                    
                    # 5. Save translated text locally
                    with open(translated_local_path, "w", encoding="utf-8") as f:
                        f.write(translated_content)
                    
                    # 6. Upload to Storage
                    sub_dir = f"{translation.video_id}" if translation.video_id else "direct"
                    translated_key = await storage.save_file(
                        str(translated_local_path), 
                        directory=f"translations/{translation.user_id}/{sub_dir}"
                    )
                    
                    translation.translated_text_path = translated_key
                    translation.status = TranslationStatus.COMPLETED
                    await db.commit()
                    logger.info(f"NMT processing COMPLETED for translation {translation_id}")

            except Exception as e:
                logger.error(f"NMT processing FAILED for {translation_id}: {e}", exc_info=True)
                translation = await db.get(Translation, translation_id)
                if translation:
                    translation.status = TranslationStatus.FAILED
                    translation.error_message = str(e)
                    await db.commit()

class TranslationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_service()

    def detect_language(self, text: str) -> str:
        try:
            lang = detect(text)
            return NLLBTranslatorWrapper.LANG_MAP.get(lang, "eng_Latn")
        except Exception:
            return "eng_Latn"

    async def create_job(self, video_id: str, user_id: int, target_lang: str, background_tasks):
        # 1. Verify Video exists and has content
        video = await self.db.get(Video, video_id)
        if not video:
            raise Exception("Video not found")
            
        if video.media_type != MediaType.TEXT:
            raise Exception("NMT currently only supports TEXT media type directly.")

        # 2. Detect Language
        # For simplicity, we assume we know it or it's English, but we could read file snippet
        source_lang = "eng_Latn" 
        
        # 3. Create Record
        job_id = str(uuid.uuid4())
        new_job = Translation(
            id=job_id,
            video_id=video_id,
            user_id=user_id,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text_path=video.file_path,
            status=TranslationStatus.PENDING
        )
        self.db.add(new_job)
        await self.db.commit()
        await self.db.refresh(new_job)
        
        background_tasks.add_task(process_translation_task, job_id)
        return new_job

    async def create_direct_job(self, text: str, user_id: int, target_lang: str, background_tasks, source_lang: Optional[str] = None):
        logger.info(f"service: create_direct_job started for user {user_id}")
        # 1. Handle Language Detection
        if not source_lang:
            logger.info("service: detecting language...")
            source_lang = self.detect_language(text)
            logger.info(f"service: detected language: {source_lang}")
            
        # 2. Save source text to temporary file and upload to storage
        job_id = str(uuid.uuid4())
        logger.info(f"service: job_id generated: {job_id}")
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = tmp.name
            
        try:
            logger.info(f"service: saving source file to storage (path={tmp_path})...")
            source_key = await self.storage.save_file(tmp_path, directory=f"translations/{user_id}/direct/source")
            logger.info(f"service: source file saved with key: {source_key}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        # 3. Create Record
        logger.info("service: creating DB record...")
        new_job = Translation(
            id=job_id,
            video_id=None,
            user_id=user_id,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text_path=source_key,
            status=TranslationStatus.PENDING
        )
        self.db.add(new_job)
        await self.db.commit()
        logger.info("service: DB commit successful")
        await self.db.refresh(new_job)
        logger.info("service: DB refresh successful")
        
        logger.info(f"service: adding background task process_translation_task for job {job_id}")
        background_tasks.add_task(process_translation_task, job_id)
        return new_job

    async def get_job(self, job_id: str):
        result = await self.db.execute(select(Translation).where(Translation.id == job_id))
        return result.scalar_one_or_none()

    async def get_video_translations(self, video_id: str):
        result = await self.db.execute(select(Translation).where(Translation.video_id == video_id))
        return result.scalars().all()

    async def get_queue_stats(self):
        """
        Returns stats about the current translation queue.
        """
        from sqlalchemy import func
        # Count pending
        stmt_pending = select(func.count()).select_from(Translation).where(Translation.status == TranslationStatus.PENDING)
        pending_count = (await self.db.execute(stmt_pending)).scalar()
        
        # Count processing
        stmt_processing = select(func.count()).select_from(Translation).where(Translation.status == TranslationStatus.PROCESSING)
        processing_count = (await self.db.execute(stmt_processing)).scalar()
        
        return {
            "pending_jobs": pending_count,
            "processing_jobs": processing_count,
            "is_busy": processing_count > 0,
            "total_queued": pending_count + processing_count
        }

    async def translate_stt_result(self, stt_data: dict, target_lang: str, source_lang: Optional[str] = None):
        """
        Fast path for translating STT results without background jobs.
        """
        translator = await asyncio.to_thread(get_translator)
        return await asyncio.to_thread(
            translator.translate_stt_result,
            stt_data,
            src_lang=source_lang,
            tgt_lang=target_lang
        )

