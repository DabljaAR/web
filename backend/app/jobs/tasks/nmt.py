import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from app.core.db import AsyncSessionLocal
from app.jobs.celery_app import celery_app
from app.jobs.models import Job, JobStatus, JobType
from app.jobs.tasks.base import BaseJobTask
from app.nmt.service import translator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.nmt.nmt_translate",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
    soft_time_limit=1800,
    time_limit=2100,
)
def nmt_translate(
    self,
    job_id: Any,
    *,
    source_lang: str = "auto",
    target_lang: str = "arb_Arab",
) -> dict:
    """Translate the STT segments for a given NMT Job.

    Fileless + segmented:
      - Reads STT segments from the parent STT Job.output_data
      - Writes translated segments to this Job.output_data
      - Creates the next TTS job row as QUEUED (does not dispatch)

    Notes:
      - The dispatcher is the only component allowed to enqueue Celery tasks.
      - This task is invoked with ``job_id`` as the first argument.
    """
    # Compatibility: if someone calls this with a dict (legacy chain), extract job_id.
    if isinstance(job_id, dict):
        job_id = job_id.get("job_id")

    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )

    async def _load_context():
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if not job:
                raise ValueError(f"NMT job {job_id} not found")

            parent = None
            if job.parent_job_id:
                parent = await db.get(Job, job.parent_job_id)
            return job, parent

    nmt_job, parent_job = self._run_sync(_load_context())

    if not parent_job or not parent_job.output_data:
        raise ValueError(f"NMT job {job_id} has no parent STT output")

    parent_output = parent_job.output_data or {}
    stt_segments = parent_output.get("segments") or []
    stt_meta = parent_output.get("metadata") or {}

    # Determine langs/output_type from this job's input_data if present.
    input_data = nmt_job.input_data or {}
    output_type = input_data.get("output_type", "fullDubbing")
    resolved_source_lang = input_data.get("source_lang", source_lang)
    resolved_target_lang = input_data.get("target_lang", target_lang)

    # Build a minimal STT result for the translator.
    stt_data = {
        "segments": [
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg.get("text", ""),
                "original_text": seg.get("text", ""),
            }
            for seg in stt_segments
        ],
        "metadata": {**stt_meta},
    }

    actual_src_lang = None if resolved_source_lang == "auto" else resolved_source_lang

    try:
        translated = self._run_sync(
            asyncio.to_thread(
                translator.translate_stt_result,
                stt_data,
                src_lang=actual_src_lang,
                tgt_lang=resolved_target_lang,
            )
        )
    except Exception as exc:
        logger.error("[NMT] translation error job=%s: %s", job_id, exc)
        raise self.retry(exc=exc)

    translated_segments = translated.get("segments") or []
    output_segments = []
    for seg in translated_segments:
        output_segments.append(
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "original_text": seg.get("original_text") or "",
                "translated_text": seg.get("text") or "",
            }
        )

    output = {
        "job_id": job_id,
        "video_id": nmt_job.video_id,
        "source_job_id": parent_job.id,
        "source_lang": resolved_source_lang,
        "target_lang": resolved_target_lang,
        "segments": output_segments,
        "metadata": {
            **(translated.get("metadata") or {}),
            "source_lang": resolved_source_lang,
            "target_lang": resolved_target_lang,
        },
    }

    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
    self.update_progress(job_id, 95.0)

    return output


@celery_app.task(
    bind=True,
    name="app.jobs.tasks.nmt.translate_segment",
    max_retries=3,
    default_retry_delay=30,
    queue="ai_nmt",
)
def nmt_translate_segment(
    self,
    segment_id: int,
    job_id: str,
    text: str,
    start: float,
    end: float,
    source_lang: Optional[str] = None,
    target_lang: str = "arb_Arab",
) -> dict:
    """Helper task to translate a single segment.

    This task is NOT a BaseJobTask, so it DOES NOT mark the entire
    job as COMPLETED. This prevents status flipping.
    """
    actual_src_lang = None if (source_lang in {None, "auto"}) else source_lang
    try:
        translated_text = translator._translate_item(
            text,
            actual_src_lang,
            target_lang,
            512,
        )
        return {
            "segment_id": segment_id,
            "job_id": job_id,
            "original_text": text,
            "translated_text": translated_text,
            "start": start,
            "end": end,
            "source_lang": source_lang or "auto",
            "target_lang": target_lang,
            "status": "completed",
        }
    except Exception as exc:
        logger.error("[NMT] segment translate failed seg=%s job=%s: %s", segment_id, job_id, exc)
        return {
            "segment_id": segment_id,
            "job_id": job_id,
            "original_text": text,
            "translated_text": text,
            "start": start,
            "end": end,
            "source_lang": source_lang or "auto",
            "target_lang": target_lang,
            "status": "failed",
            "error": str(exc),
        }
