import logging
import asyncio
import json
import os
import tempfile
from datetime import datetime
from typing import Any, Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import Job, JobStatus, JobType

# 🔥 Register models globally to avoid SQLAlchemy mapper errors
import app.media.models  # noqa
import app.core.models   # noqa

# Heavy imports for NMT service and storage
from app.media.storage import get_storage_service
from app.nmt.service import translator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    # ── NOTE: We do NOT use BaseJobTask as the base class here. ──────────
    # This prevents the automatic lifecycle hooks from crashing when they
    # encounter a dictionary as the first argument in a Celery chain.
    # Instead, we use its STATIC methods manually.
    name="app.jobs.tasks.pipeline.nmt_translate",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
)
def nmt_translate(
    self,
    job_id: Any,
    video_id: Optional[str] = None,
    transcript_key: Optional[str] = None,
    source_lang: str = "auto",
    target_lang: str = "en",
    trigger_tts: bool = True,
) -> dict:
    """
    Translate the transcript produced by ``stt_transcribe``.
    Uses BaseJobTask static helpers for clean, manual lifecycle management.
    """
    stt_data = None
    
    # 1. Handle Pipeline Input (If called via Celery chain)
    if isinstance(job_id, dict):
        stt_result = job_id
        real_job_id = stt_result.get("job_id")
        video_id = video_id or stt_result.get("video_id")
        transcript_key = transcript_key or stt_result.get("transcript_key")
        # In a chain, we might have trigger_tts passed in the dict
        if trigger_tts is True and "trigger_tts" in stt_result:
             trigger_tts = stt_result["trigger_tts"]
        
        if "transcript" in stt_result and "segments" in stt_result:
            stt_data = stt_result
        else:
            stt_data = stt_result.get("output")
        
        job_id = real_job_id

    # 2. Lifecycle: Move to PROCESSING
    if job_id:
        BaseJobTask._run_sync(
            BaseJobTask._patch_job(
                job_id,
                JobStatus.PROCESSING,
                celery_task_id=self.request.id,
                started_at=datetime.utcnow(),
            )
        )

        # Persist STT data to database input_data
        if stt_data:
            async def _persist():
                from app.core.db import AsyncSessionLocal
                from app.jobs.models import Job
                async with AsyncSessionLocal() as db:
                    job = await db.get(Job, job_id)
                    if job:
                        job.input_data = {"target_lang": target_lang, "stt_data": stt_data}
                        await db.commit()
            BaseJobTask._run_sync(_persist())

    async def _do_translation():
        nonlocal stt_data
        if not stt_data:
            if not transcript_key:
                logger.warning("nmt_translate job=%s | No data provided", job_id)
                return None
            
            storage = get_storage_service()
            with tempfile.TemporaryDirectory() as tmpdir:
                local_src = os.path.join(tmpdir, "stt.json")
                if await storage.download(transcript_key, local_src):
                    with open(local_src, "r", encoding="utf-8") as f:
                        stt_data = json.load(f)
        
        # ML Inference
        actual_src_lang = None if source_lang == "auto" else source_lang
        logger.info("Starting NMT translation for job=%s target=%s", job_id, target_lang)
        
        return await asyncio.to_thread(
            translator.translate_stt_result,
            stt_data,
            src_lang=actual_src_lang,
            tgt_lang=target_lang
        )

    try:
        translated_data = BaseJobTask._run_sync(_do_translation())
        if not translated_data:
             return {"job_id": job_id, "video_id": video_id, "output": None}

        # 3. Preparation & Persist Output
        output = {
            "job_id":         job_id,
            "video_id":       video_id,
            "transcript_key": transcript_key,
            "transcript":     translated_data.get("transcript"),
            "segments":       translated_data.get("segments"),
            "metadata":       translated_data.get("metadata"),
            "output":         translated_data,
            "target_lang":    target_lang,
        }

        if job_id:
            async def _save_output():
                from app.core.db import AsyncSessionLocal
                from app.jobs.models import Job
                async with AsyncSessionLocal() as db:
                    job = await db.get(Job, job_id)
                    if job:
                        job.output_data = output
                        await db.commit()
            BaseJobTask._run_sync(_save_output())
            
            # Lifecycle: Mark COMPLETED
            BaseJobTask._run_sync(
                BaseJobTask._patch_job(
                    job_id, 
                    JobStatus.COMPLETED, 
                    progress=100.0, 
                    completed_at=datetime.utcnow()
                )
            )

        # 4. Trigger TTS if requested (Creates a separate Job row for tracked progress)
        if trigger_tts and job_id:
            from app.jobs.celery_app import celery_app
            import uuid
            
            async def _create_tts_job_row():
                from app.core.db import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    # Fetch current job for user/video context
                    current_job = await db.get(Job, job_id)
                    if not current_job:
                        return None
                    
                    new_id = str(uuid.uuid4())
                    tts_job = Job(
                        id=new_id,
                        video_id=current_job.video_id,
                        user_id=current_job.user_id,
                        job_type=JobType.TTS_SYNTHESIZE,
                        status=JobStatus.QUEUED,
                        parent_job_id=job_id,
                        input_data={"target_lang": target_lang, "nmt_job_id": job_id}
                    )
                    db.add(tts_job)
                    await db.commit()
                    return new_id

            tts_job_id = BaseJobTask._run_sync(_create_tts_job_row())
            if tts_job_id:
                # Swap the job_id in the output so TTS updates the correct row
                output["job_id"] = tts_job_id
                logger.info("Triggering TTS for job=%s (chained from %s)", tts_job_id, job_id)
                celery_app.send_task(
                    "app.jobs.tasks.pipeline.tts_synthesize",
                    args=[output], 
                    queue="ai_tts"
                )

        return output
        
    except Exception as e:
        logger.error("nmt_translate failed for job %s: %s", job_id, e)
        # Lifecycle: Mark FAILED
        if job_id:
            BaseJobTask._run_sync(
                BaseJobTask._patch_job(
                    job_id, 
                    JobStatus.FAILED, 
                    error_message=str(e),
                    completed_at=datetime.utcnow()
                )
            )
        raise
