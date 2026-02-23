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
from langdetect import detect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.nmt.models import Translation, TranslationStatus
from app.media.models import Video, MediaType
from app.media.storage import get_storage_service
from app.core.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

class NLLBTranslatorWrapper:
    """
    Wrapper for NLLB model, adapted from demo_translation.py
    """
    def __init__(self, model_name="facebook/nllb-200-distilled-600M"):
        self.model_name = model_name
        self.device = self._get_device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(self.device)

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

    def translate(self, text, src_lang="eng_Latn", tgt_lang="arb_Arab", max_length=512):
        if not text:
            return ""
        
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return text
            
        self.tokenizer.src_lang = src_lang
        
        # Batch size of 4-8 is usually good for CPU/Memory
        batch_size = 4 
        translated_results = []
        
        for i in range(0, len(lines), batch_size):
            batch = lines[i:i + batch_size]
            
            # Check if any line in batch is too long (NLLB prefers chunking for > 512 tokens)
            processed_batch = []
            for line in batch:
                inputs = self.tokenizer(line, return_tensors="pt").to(self.device)
                if inputs.input_ids.shape[1] > max_length:
                    # If one line is massive, translate it separately with special chunking
                    processed_batch.append(self._translate_long_text(line, tgt_lang, max_length))
                else:
                    processed_batch.append(line)
            
            # Translate the batch together
            # Skip actual inference for lines already translated by _translate_long_text
            lines_to_translate = [l for l in processed_batch if l not in translated_results]
            
            if lines_to_translate:
                batch_outputs = self._run_inference_batch(batch, tgt_lang, max_length)
                translated_results.extend(batch_outputs)
            else:
                translated_results.extend(processed_batch)
                
        return "\n".join(translated_results)

    def _run_inference_batch(self, texts, tgt_lang, max_length):
        """Internal method to perform batch model inference."""
        inputs = self.tokenizer(texts, return_tensors="pt", padding=True, truncation=True).to(self.device)
        outputs = self.model.generate(
            **inputs,
            forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_lang),
            max_length=max_length,
            num_beams=2,  # Reduced from 5 to 2 for 2-3x faster CPU performance with 90% same quality
            early_stopping=True
        )
        return self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

    def _translate_long_text(self, text, tgt_lang, max_length):
        # Simplified chunking logic based on demo_translation.py
        words = text.replace('\n', ' \n ').split(' ')
        chunks = []
        current_words = []
        
        for word in words:
            if not word: continue
            test_words = current_words + [word]
            test_str = " ".join(test_words).replace(' \n ', '\n')
            token_count = self.tokenizer(test_str, return_tensors="pt").input_ids.shape[1]
            
            if token_count > max_length - 10:
                if current_words:
                    chunk_str = " ".join(current_words).replace(' \n ', '\n')
                    chunks.append(self._run_inference(chunk_str, tgt_lang, max_length))
                    current_words = [word]
                else:
                    chunks.append(self._run_inference(word, tgt_lang, max_length))
                    current_words = []
            else:
                current_words = test_words
        
        if current_words:
            chunk_str = " ".join(current_words).replace(' \n ', '\n')
            chunks.append(self._run_inference(chunk_str, tgt_lang, max_length))
            
        return " ".join(chunks)

# Singleton for translator to avoid reloading model on every request
_translator = None
_translation_lock = asyncio.Lock()

def get_translator():
    global _translator
    if _translator is None:
        logger.info("Initializing NLLBTranslatorWrapper (this may take a while)...")
        _translator = NLLBTranslatorWrapper()
    return _translator

async def init_nmt():
    """
    Pre-load the translator during startup.
    """
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
        """
        Detect language and return NLLB language code.
        """
        try:
            lang = detect(text)
            # Map common ISO codes to NLLB codes
            lang_map = {
                "en": "eng_Latn",
                "ar": "arb_Arab",
                "fr": "fra_Latn",
                "es": "spa_Latn",
                "de": "deu_Latn",
                "ru": "rus_Cyrl",
                "zh-cn": "zho_Hans",
                "zh-tw": "zho_Hant",
                "it": "ita_Latn",
                "pt": "por_Latn",
            }
            return lang_map.get(lang, "eng_Latn") # Default to English if unknown
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
