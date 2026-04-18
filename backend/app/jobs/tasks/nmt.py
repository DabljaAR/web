"""NMT Celery tasks.

Parallel-chord approach:
  nmt_translate         — reads STT segments from VideoTask, fans out one
                          nmt_translate_segment per segment via a Celery chord.
  nmt_translate_segment — translates a single segment; immediately dispatches
                          its TTS segment when output_type requires it.
  nmt_combine_results   — chord callback: sorts segment results, writes one
                          combined DB record, updates VideoTask status.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from celery import chord, group

from app.jobs.celery_app import celery_app
from app.jobs.models import Job, JobStatus, JobType
from app.jobs.tasks.base import BaseJobTask
from app.nmt.service import translator

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

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
    enqueued_at: Optional[float] = None,
    *,
    source_lang: str = "auto",
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Fan out one nmt_translate_segment task per STT segment, then let
    nmt_combine_results write a single combined DB record when all finish.

    Returns {"_skip_completion": True} so BaseJobTask.on_success does not
    mark the job COMPLETED prematurely — nmt_combine_results does that.
    """
    if isinstance(job_id, dict):
        job_id = job_id.get("job_id")

    orchestrator_started_at = time.time()
    if enqueued_at:
        logger.info(
            "[NMT][TIMING] orchestrator_queue_wait_ms=%.1f | job=%s",
            (orchestrator_started_at - enqueued_at) * 1000.0,
            job_id,
        )

    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=_utcnow(),
    )

    # ── 1. Load STT output from VideoTask ────────────────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            nmt_job = db.get(Job, job_id)
            if not nmt_job:
                raise ValueError(f"NMT job {job_id} not found")
            task_id = (nmt_job.input_data or {}).get("task_id")
            if not task_id:
                raise ValueError(f"NMT job {job_id} has no task_id in input_data")
            from app.tasks.models import VideoTask
            task = db.get(VideoTask, task_id)
            if not task or task.stt_segments is None:
                raise ValueError(f"VideoTask {task_id} has no STT segments yet")
            stt_segments = list(task.stt_segments)
            full_transcript = task.transcript or ""
            resolved_source_lang = task.source_lang or source_lang
            resolved_target_lang = task.target_lang or target_lang
            output_type = task.output_type
            num_beams = task.num_beams
            english_ratio_threshold = task.english_ratio_threshold
            video_id = nmt_job.video_id
    finally:
        engine.dispose()

    actual_src_lang = None if resolved_source_lang == "auto" else resolved_source_lang

    logger.info(
        "[NMT] job=%s | segments=%d | %s → %s",
        job_id, len(stt_segments), resolved_source_lang, resolved_target_lang,
    )

    # ── 2. Short-circuit when there are no segments ──────────────────────────
    if not stt_segments:
        logger.info("[NMT] No segments to translate | job=%s", job_id)
        output = {
            "job_id": job_id,
            "video_id": video_id,
            "transcript": full_transcript,
            "translated_transcript": full_transcript,
            "segments": [],
            "metadata": {
                "source_lang": resolved_source_lang,
                "target_lang": resolved_target_lang,
                "segment_count": 0,
            },
        }
        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
        return output

    self.update_progress(job_id, 5.0)

    # ── 3. Pre-create TTS job if output_type requires it ────────────────────
    # Each nmt_translate_segment will dispatch its own tts_synthesize_segment
    # immediately after translation, so TTS runs in parallel with remaining NMT.
    TTS_REQUIRED = {"translationAndTTS", "fullDubbing"}
    tts_context: Optional[dict] = None

    if output_type in TTS_REQUIRED and stt_segments:
        tts_job_id = BaseJobTask._create_next_job(
            job_id,
            JobType.TTS_SYNTHESIZE,
            input_data={
                "task_id": task_id,
                "target_lang": resolved_target_lang,
                "output_type": output_type,
            },
        )
        tts_context = {
            "tts_job_id": tts_job_id,
            "total_segments": len(stt_segments),
            "ref_clip_minio_key": None,
            "task_id": task_id,
            "output_type": output_type,
            "video_id": str(video_id),
            "metadata": {
                "source_lang": resolved_source_lang,
                "target_lang": resolved_target_lang,
            },
        }
        logger.info(
            "[NMT] TTS job %s pre-created | job=%s | segments=%d",
            tts_job_id, job_id, len(stt_segments),
        )

    # ── 4. Fan out segment tasks via chord ───────────────────────────────────
    segment_tasks = [
        nmt_translate_segment.s(
            idx,
            str(job_id),
            seg.get("text", "").strip(),
            seg.get("start"),
            seg.get("end"),
            actual_src_lang,
            resolved_target_lang,
            num_beams,
            english_ratio_threshold,
            tts_context,
            time.time(),
        )
        for idx, seg in enumerate(stt_segments)
    ]

    chord(group(segment_tasks))(
        nmt_combine_results.s(
            job_id=job_id,
            task_id=task_id,
            video_id=video_id,
            full_transcript=full_transcript,
            resolved_source_lang=resolved_source_lang,
            resolved_target_lang=resolved_target_lang,
            output_type=output_type,
        )
    )

    logger.info(
        "[NMT] chord dispatched | job=%s | segment_tasks=%d | tts_pre_created=%s",
        job_id, len(segment_tasks), bool(tts_context),
    )
    return {"_skip_completion": True, "job_id": job_id, "segment_count": len(segment_tasks)}


# ---------------------------------------------------------------------------
# Per-segment worker
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
    num_beams: int = 5,
    english_ratio_threshold: float = 0.5,
    tts_context: Optional[dict] = None,
    enqueued_at: Optional[float] = None,
) -> dict:
    """Translate a single segment, then immediately dispatch its TTS segment."""
    segment_start = time.time()
    if enqueued_at:
        logger.info(
            "[NMT][TIMING] segment_queue_wait_ms=%.1f | job=%s | segment_id=%s",
            (segment_start - enqueued_at) * 1000.0,
            job_id,
            segment_id,
        )

    actual_src_lang = None if (source_lang in {None, "auto"}) else source_lang
    try:
        translated_text = translator._translate_item(
            text, actual_src_lang, target_lang, 512,
            num_beams=num_beams,
            english_ratio_threshold=english_ratio_threshold,
        )
        status = "completed"
    except Exception as exc:
        logger.error("[NMT] segment %d failed job=%s: %s", segment_id, job_id, exc)
        translated_text = text  # fall back to original
        status = "failed"

    logger.info(
        "[NMT][TIMING] segment_translate_ms=%.1f | job=%s | segment_id=%s | status=%s",
        (time.time() - segment_start) * 1000.0,
        job_id,
        segment_id,
        status,
    )

    # ── Dispatch TTS for this segment immediately ────────────────────────────
    if tts_context:
        try:
            from app.jobs.tasks.pipeline import tts_synthesize_segment
            tts_synthesize_segment.apply_async(
                kwargs={
                    "segment_id": segment_id,
                    "job_id": tts_context["tts_job_id"],
                    "text": translated_text,
                    "start": start,
                    "end": end,
                    "minio_segment_key": f"tts/{tts_context['tts_job_id']}/segment_{segment_id}.wav",
                    "ref_clip_minio_key": tts_context.get("ref_clip_minio_key"),
                    "tts_job_id": tts_context["tts_job_id"],
                    "total_segments": tts_context["total_segments"],
                    "task_id": tts_context.get("task_id"),
                    "tts_metadata": tts_context.get("metadata"),
                    "output_type": tts_context.get("output_type", "fullDubbing"),
                    "video_id": tts_context.get("video_id"),
                    "enqueued_at": time.time(),
                },
                queue="ai_tts",
            )
            logger.debug(
                "[NMT] TTS dispatched for segment %d | tts_job=%s",
                segment_id, tts_context["tts_job_id"],
            )
        except Exception as exc:
            logger.error(
                "[NMT] failed to dispatch TTS for segment %d: %s", segment_id, exc
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
        "status": status,
    }


# ---------------------------------------------------------------------------
# Chord callback — combines all segment results into one DB record
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.jobs.tasks.nmt.nmt_combine_results",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
    soft_time_limit=300,
    time_limit=360,
)
def nmt_combine_results(
    segment_results: list,
    *,
    job_id: Any,
    task_id: Optional[str] = None,
    video_id: Any,
    full_transcript: str,
    resolved_source_lang: str,
    resolved_target_lang: str,
    output_type: str,
) -> dict:
    """
    Chord callback: receives all nmt_translate_segment results, sorts them by
    segment_id, and writes a single combined record to the DB.
    """
    sorted_results = sorted(segment_results, key=lambda r: r["segment_id"])

    translated_segments = [
        {
            "start": r["start"],
            "end": r["end"],
            "original_text": r["original_text"],
            "translated_text": r["translated_text"],
        }
        for r in sorted_results
    ]

    translated_transcript = " ".join(
        s["translated_text"] for s in translated_segments
    ).strip()

    output = {
        "job_id": job_id,
        "video_id": video_id,
        "transcript": full_transcript,
        "translated_transcript": translated_transcript,
        "segments": translated_segments,
        "metadata": {
            "source_lang": resolved_source_lang,
            "target_lang": resolved_target_lang,
            "segment_count": len(translated_segments),
        },
    }

    # ── Write to Job row ─────────────────────────────────────────────────────
    BaseJobTask._patch_job(
        job_id,
        JobStatus.COMPLETED,
        output_data=output,
        progress=100.0,
        completed_at=_utcnow(),
    )

    # ── Write translated result to VideoTask ─────────────────────────────────
    if task_id:
        from app.tasks.models import TaskStatus
        captions_and_translation = output_type == "captionsAndTranslation"
        BaseJobTask._patch_task(
            task_id,
            TaskStatus.COMPLETED if captions_and_translation else TaskStatus.PROCESSING,
            translated_transcript=translated_transcript,
            segments=translated_segments,
            progress=100.0 if captions_and_translation else 50.0,
            completed_at=_utcnow() if captions_and_translation else None,
        )

    failed_count = sum(1 for r in sorted_results if r.get("status") == "failed")
    logger.info(
        "[NMT] combined | job=%s | segments=%d | failed=%d | output_type=%s",
        job_id, len(translated_segments), failed_count, output_type,
    )
    return output
