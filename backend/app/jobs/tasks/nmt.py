import logging
import asyncio
import json
import os
import tempfile
from datetime import datetime
from typing import Any, Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus

# These are the heavy imports we need for the NMT service and storage
from app.media.storage import get_storage_service
from app.nmt.service import translator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.nmt_translate",  # Using the pipeline name for orchestration
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
)
def nmt_translate(
    self,
    job_id: str,
    video_id: str,
    transcript_key: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> dict:
    """
    Translate the transcript produced by ``stt_transcribe``.
    Supports being called in a Celery chain.
    """
    stt_data = None
    
    # 1. Handle Celery chain input (if the previous task passed a dict as the first arg)
    if isinstance(job_id, dict):
        stt_result = job_id
        job_id = stt_result.get("job_id")
        video_id = video_id or stt_result.get("video_id")
        transcript_key = transcript_key or stt_result.get("transcript_key")
        # Prefer in-memory 'output' passed from STT if available
        stt_data = stt_result.get("output")

    if job_id:
        self._run_sync(
            self._patch_job(
                job_id,
                JobStatus.PROCESSING,
                celery_task_id=self.request.id,
                started_at=datetime.utcnow(),
            )
        )

    async def _do_translation():
        nonlocal stt_data
        
        # 2. If we don't have direct data, download the transcript JSON from storage
        if not stt_data:
            if not transcript_key:
                logger.warning("nmt_translate job=%s video=%s | No transcript_key or data provided, skipping", job_id, video_id)
                return None
                
            storage = get_storage_service()
            with tempfile.TemporaryDirectory() as tmpdir:
                local_src = os.path.join(tmpdir, "stt.json")
                success = await storage.download(transcript_key, local_src)
                if not success:
                    raise RuntimeError(f"Failed to download transcript from storage (key: {transcript_key})")
                
                with open(local_src, "r", encoding="utf-8") as f:
                    stt_data = json.load(f)
        
        # 3. Run NMT translation
        actual_src_lang = None if source_lang == "auto" else source_lang
        logger.info("Starting NMT translation for job=%s source=%s target=%s", job_id, source_lang, target_lang)
        
        # Since translator.translate_stt_result is a blocking ML task, offload to thread
        translated_result = await asyncio.to_thread(
            translator.translate_stt_result,
            stt_data,
            src_lang=actual_src_lang,
            tgt_lang=target_lang
        )
        return translated_result

    try:
        translated_data = self._run_sync(_do_translation())
        if translated_data is None:
             return {"job_id": job_id, "video_id": video_id, "output": None}

        logger.info(
            "nmt_translate success: job=%s video=%s %s→%s",
            job_id, video_id, source_lang, target_lang
        )
        
        # 4. Save results to the database and return
        output = {
            "job_id":         job_id,
            "video_id":       video_id,
            "transcript_key": transcript_key,
            "transcript":     translated_data.get("transcript"),
            "segments":       translated_data.get("segments"),
            "metadata":       translated_data.get("metadata"),
            "output":         translated_data, # Keeping 'output' for chain consistency
        }

        if job_id:
            # We fulfill the 'persist output_data' requirement manually since we won't change _patch_job signature
            async def _update_output():
                from app.core.db import AsyncSessionLocal
                from app.jobs.models import Job
                async with AsyncSessionLocal() as db:
                    job = await db.get(Job, job_id)
                    if job:
                        job.output_data = output
                        await db.commit()

            self._run_sync(_update_output())
            # Still call the official helper for standard state management
            self._run_sync(
                self._patch_job(job_id, JobStatus.COMPLETED)
            )

        return output
        
    except Exception as e:
        logger.error("nmt_translate failed for job %s: %s", job_id, e)
        # Re-raise so BaseJobTask can handle failure state update
        raise


