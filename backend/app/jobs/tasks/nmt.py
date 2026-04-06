"""NMT Celery task.

Single-job approach:
  nmt_translate  — reads STT segments from parent job, translates each
                   segment individually, stores one combined result, then
                   dispatches tts_pipeline.
"""
import logging
from datetime import datetime
from typing import Any, Optional

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
    """
    Translate STT segments one by one and store a single combined result.

    Reads segments from the parent STT job, translates each segment
    individually via the NMT model, then saves one output_data dict:
        {
            "transcript":            str,   # original full text
            "translated_transcript": str,   # full translated text
            "segments": [
                {
                    "start":           float,
                    "end":             float,
                    "original_text":   str,
                    "translated_text": str,
                },
                ...
            ],
            "metadata": { "source_lang", "target_lang", "segment_count" }
        }

    On completion dispatches tts_pipeline with one TTS job.
    """
    if isinstance(job_id, dict):
        job_id = job_id.get("job_id")

    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 1. Load parent STT output ────────────────────────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            nmt_job = db.get(Job, job_id)
            if not nmt_job:
                raise ValueError(f"NMT job {job_id} not found")
            parent = db.get(Job, nmt_job.parent_job_id) if nmt_job.parent_job_id else None
    finally:
        engine.dispose()

    if not parent or not parent.output_data:
        raise ValueError(f"NMT job {job_id} has no parent STT output")

    parent_output    = dict(parent.output_data)
    stt_segments     = parent_output.get("segments") or []
    full_transcript  = parent_output.get("transcript", "")

    input_data           = nmt_job.input_data or {}
    resolved_source_lang = input_data.get("source_lang", source_lang)
    resolved_target_lang = input_data.get("target_lang", target_lang)
    actual_src_lang      = None if resolved_source_lang == "auto" else resolved_source_lang
    output_type          = input_data.get("output_type", "fullDubbing")

    logger.info(
        "[NMT] job=%s | segments=%d | %s → %s",
        job_id, len(stt_segments), resolved_source_lang, resolved_target_lang,
    )

    if not stt_segments:
        logger.info("[NMT] No segments to translate | job=%s", job_id)
        output = {
            "job_id":                job_id,
            "video_id":              nmt_job.video_id,
            "transcript":            full_transcript,
            "translated_transcript": full_transcript,
            "segments":              [],
            "metadata": {
                "source_lang":   resolved_source_lang,
                "target_lang":   resolved_target_lang,
                "segment_count": 0,
            },
        }
        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
        return output

    self.update_progress(job_id, 5.0)

    # ── 2. Translate segment by segment ─────────────────────────────────────
    translated_segments = []
    total = len(stt_segments)

    for idx, seg in enumerate(stt_segments):
        original_text = seg.get("text", "").strip()

        if original_text:
            try:
                translated_text = translator._translate_item(
                    original_text,
                    actual_src_lang,
                    resolved_target_lang,
                    512,
                )
            except Exception as exc:
                logger.error("[NMT] segment %d failed | job=%s: %s", idx, job_id, exc)
                translated_text = original_text   # fall back to original
        else:
            translated_text = original_text

        translated_segments.append({
            "start":           seg.get("start"),
            "end":             seg.get("end"),
            "original_text":   original_text,
            "translated_text": translated_text,
        })

        # Progress from 5 % → 95 % as segments complete
        progress = 5.0 + (90.0 * (idx + 1) / total)
        self.update_progress(job_id, round(progress, 1))

    # ── 3. Build combined output ─────────────────────────────────────────────
    translated_transcript = " ".join(
        s["translated_text"] for s in translated_segments
    ).strip()

    output = {
        "job_id":                job_id,
        "video_id":              nmt_job.video_id,
        "transcript":            full_transcript,
        "translated_transcript": translated_transcript,
        "segments":              translated_segments,
        "metadata": {
            "source_lang":   resolved_source_lang,
            "target_lang":   resolved_target_lang,
            "segment_count": len(translated_segments),
        },
    }

    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

    # ── 4. Conditionally dispatch TTS based on output_type ──────────────────
    TTS_REQUIRED = {"translationAndTTS", "fullDubbing"}
    if output_type in TTS_REQUIRED and any(s["translated_text"].strip() for s in translated_segments):
        from app.jobs.tasks.pipeline import tts_pipeline

        tts_job_id = self._create_next_job(
            job_id,
            JobType.TTS_SYNTHESIZE,
            input_data={"target_lang": resolved_target_lang, "output_type": output_type},
        )
        tts_pipeline.apply_async(args=[tts_job_id], queue="ai_tts")
        logger.info("[NMT] TTS job %s dispatched | job=%s | output_type=%s", tts_job_id, job_id, output_type)
    else:
        if output_type not in TTS_REQUIRED:
            logger.info("[NMT] output_type=%s — skipping TTS | job=%s", output_type, job_id)
        else:
            logger.info("[NMT] No translatable segments; pipeline ends | job=%s", job_id)

    logger.info("[NMT] done | job=%s | segments=%d", job_id, len(translated_segments))
    return output


# ---------------------------------------------------------------------------
# Standalone single-segment helper (not used by the pipeline)
# ---------------------------------------------------------------------------

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
    """Standalone helper: translate a single segment without DB tracking."""
    actual_src_lang = None if (source_lang in {None, "auto"}) else source_lang
    try:
        translated_text = translator._translate_item(text, actual_src_lang, target_lang, 512)
        return {
            "segment_id": segment_id, "job_id": job_id,
            "original_text": text, "translated_text": translated_text,
            "start": start, "end": end,
            "source_lang": source_lang or "auto", "target_lang": target_lang,
            "status": "completed",
        }
    except Exception as exc:
        logger.error("[NMT] segment %d failed job=%s: %s", segment_id, job_id, exc)
        return {
            "segment_id": segment_id, "job_id": job_id,
            "original_text": text, "translated_text": text,
            "start": start, "end": end,
            "source_lang": source_lang or "auto", "target_lang": target_lang,
            "status": "failed", "error": str(exc),
        }
