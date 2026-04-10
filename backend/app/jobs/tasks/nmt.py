"""NMT Celery task.

Parallel-chord approach:
  nmt_translate       — reads STT segments, fans out one translate_segment task
                        per segment via a Celery chord, then returns.
  nmt_translate_segment — translates a single segment (unchanged helper).
  nmt_combine_results — chord callback: receives all segment results, sorts
                        them, writes ONE combined DB record, dispatches TTS.
"""
import logging
import os
from datetime import datetime
from typing import Any, Optional

from celery import chord, group

from app.jobs.celery_app import celery_app
from app.jobs.models import Job, JobStatus, JobType
from app.jobs.tasks.base import BaseJobTask
from app.nmt.service import translator

logger = logging.getLogger(__name__)


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
    *,
    source_lang: str = "auto",
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Fan out one nmt_translate_segment task per STT segment, then let
    nmt_combine_results write a single combined DB record when all finish.
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

    input_data                = nmt_job.input_data or {}
    resolved_source_lang      = input_data.get("source_lang", source_lang)
    resolved_target_lang      = input_data.get("target_lang", target_lang)
    actual_src_lang           = None if resolved_source_lang == "auto" else resolved_source_lang
    output_type               = input_data.get("output_type", "fullDubbing")
    num_beams                 = int(input_data.get("num_beams", 5))
    english_ratio_threshold   = float(input_data.get("english_ratio_threshold", 0.5))
    task_id                   = input_data.get("task_id")

    logger.info(
        "[NMT] job=%s | segments=%d | %s → %s",
        job_id, len(stt_segments), resolved_source_lang, resolved_target_lang,
    )

    # ── 2. Short-circuit when there are no segments ──────────────────────────
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

    # ── 3 + 4. Build TTS context first, then fan out segments with it ───────── so each segment can dispatch TTS immediately ──
    TTS_REQUIRED = {"translationAndTTS", "fullDubbing"}
    tts_context: Optional[dict] = None

    if output_type in TTS_REQUIRED and stt_segments:
        import asyncio
        import subprocess
        import tempfile

        tts_job_id = BaseJobTask._create_next_job(
            job_id,
            JobType.TTS_SYNTHESIZE,
            input_data={
                "task_id":    task_id,
                "target_lang": resolved_target_lang,
                "output_type": output_type,
            },
        )

        # Extract 15-second voice clip from the video and upload to MinIO.
        # Voice cloning with SILMA only works when the reference audio is in the
        # same language as the output (Arabic). If the source is not Arabic,
        # skip extraction — tts_synthesize_segment will fall back to the bundled
        # Arabic sample which produces clean, consistent Arabic speech.
        _source_is_arabic = resolved_source_lang in {"auto", "arb_Arab", "ar", "ara"}
        ref_clip_minio_key: Optional[str] = None

        if _source_is_arabic:
            ref_clip_minio_key = f"tts/{nmt_job.video_id}/ref_clip_{tts_job_id}.wav"
            try:
                engine_v, SL_v = BaseJobTask._make_db()
                try:
                    with SL_v() as db:
                        from app.media.models import Video as _V
                        _vrow = db.get(_V, nmt_job.video_id)
                        _audio_key = (_vrow.audio_path or _vrow.file_path) if _vrow else None
                finally:
                    engine_v.dispose()

                if not _audio_key:
                    raise ValueError("no audio key on video")

                from app.media.storage import get_storage_service
                with tempfile.TemporaryDirectory() as _td:
                    _raw  = os.path.join(_td, "src")
                    _clip = os.path.join(_td, "ref.wav")
                    _loop = asyncio.new_event_loop()
                    try:
                        _loop.run_until_complete(get_storage_service().download(_audio_key, _raw))
                    finally:
                        _loop.close()
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", _raw, "-t", "15", "-ar", "24000", "-ac", "1", _clip],
                        check=True, capture_output=True,
                    )
                    with open(_clip, "rb") as _f:
                        _clip_bytes = _f.read()

                _loop2 = asyncio.new_event_loop()
                try:
                    _loop2.run_until_complete(
                        get_storage_service().upload_bytes(_clip_bytes, ref_clip_minio_key, "audio/wav")
                    )
                finally:
                    _loop2.close()
                logger.info("[NMT] TTS ref clip uploaded | key=%s | job=%s", ref_clip_minio_key, job_id)

            except Exception as _exc:
                logger.warning("[NMT] could not extract TTS ref clip: %s", _exc)
                ref_clip_minio_key = None
        else:
            logger.info(
                "[NMT] source_lang=%s is not Arabic — skipping voice cloning, "
                "TTS will use bundled Arabic reference | job=%s",
                resolved_source_lang, job_id,
            )

        # Redis counter so tts_synthesize_segment knows when all N segments finish
        try:
            celery_app.backend.client.set(
                f"tts:pending:{tts_job_id}", len(stt_segments), ex=7200
            )
        except Exception as _exc:
            logger.warning("[NMT] could not set TTS Redis counter: %s", _exc)

        tts_context = {
            "tts_job_id":          tts_job_id,
            "total_segments":      len(stt_segments),
            "ref_clip_minio_key":  ref_clip_minio_key,
            "task_id":             task_id,
            "output_type":         output_type,
            "video_id":            str(nmt_job.video_id),
            "metadata": {
                "source_lang": resolved_source_lang,
                "target_lang": resolved_target_lang,
            },
        }
        logger.info("[NMT] TTS job %s pre-created | job=%s | segments=%d",
                    tts_job_id, job_id, len(stt_segments))

    # Rebuild segment_tasks with tts_context appended
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
        )
        for idx, seg in enumerate(stt_segments)
    ]

    chord(group(segment_tasks))(
        nmt_combine_results.s(
            job_id=job_id,
            task_id=task_id,
            video_id=nmt_job.video_id,
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
) -> dict:
    """Translate a single segment, then immediately dispatch its TTS segment."""
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

    # ── Dispatch TTS for this segment immediately ────────────────────────────
    if tts_context:
        try:
            from app.jobs.tasks.pipeline import tts_synthesize_segment
            tts_synthesize_segment.apply_async(
                kwargs={
                    "segment_id":         segment_id,
                    "job_id":             tts_context["tts_job_id"],
                    "text":               translated_text,
                    "start":              start,
                    "end":                end,
                    "minio_segment_key":  f"tts/{tts_context['tts_job_id']}/segment_{segment_id}.wav",
                    "ref_clip_minio_key": tts_context.get("ref_clip_minio_key"),
                    "tts_job_id":         tts_context["tts_job_id"],
                    "total_segments":     tts_context["total_segments"],
                    "task_id":            tts_context.get("task_id"),
                    "tts_metadata":       tts_context.get("metadata"),
                    "output_type":        tts_context.get("output_type", "fullDubbing"),
                    "video_id":           tts_context.get("video_id"),
                },
                queue="ai_tts",
            )
            logger.debug("[NMT] TTS dispatched for segment %d | tts_job=%s",
                         segment_id, tts_context["tts_job_id"])
        except Exception as exc:
            logger.error("[NMT] failed to dispatch TTS for segment %d: %s", segment_id, exc)

    return {
        "segment_id":      segment_id,
        "job_id":          job_id,
        "original_text":   text,
        "translated_text": translated_text,
        "start":           start,
        "end":             end,
        "source_lang":     source_lang or "auto",
        "target_lang":     target_lang,
        "status":          status,
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
    Chord callback: receives a list of nmt_translate_segment results,
    sorts them by segment_id, and writes a single combined record to the DB.
    """
    # Sort back to original order regardless of task completion order
    sorted_results = sorted(segment_results, key=lambda r: r["segment_id"])

    translated_segments = [
        {
            "start":           r["start"],
            "end":             r["end"],
            "original_text":   r["original_text"],
            "translated_text": r["translated_text"],
        }
        for r in sorted_results
    ]

    translated_transcript = " ".join(
        s["translated_text"] for s in translated_segments
    ).strip()

    output = {
        "job_id":                job_id,
        "video_id":              video_id,
        "transcript":            full_transcript,
        "translated_transcript": translated_transcript,
        "segments":              translated_segments,
        "metadata": {
            "source_lang":   resolved_source_lang,
            "target_lang":   resolved_target_lang,
            "segment_count": len(translated_segments),
        },
    }

    # ── Write to Job row ─────────────────────────────────────────────────────
    BaseJobTask._patch_job(
        job_id,
        JobStatus.COMPLETED,
        output_data=output,
        progress=100.0,
        completed_at=datetime.utcnow(),
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
            completed_at=datetime.utcnow() if captions_and_translation else None,
        )

    logger.info(
        "[NMT] combined | job=%s | segments=%d | failed=%d",
        job_id,
        len(translated_segments),
        sum(1 for r in sorted_results if r.get("status") == "failed"),
    )

    # TTS is already running — each nmt_translate_segment dispatched its own
    # tts_synthesize_segment immediately after translation. Nothing to do here.
    logger.info("[NMT] combined | job=%s | NMT done, TTS running in parallel", job_id)
    return output
