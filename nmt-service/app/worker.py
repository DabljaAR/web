"""RabbitMQ consumer that processes NMT jobs dispatched by the orchestrator.

Design doc references:
  §8.2  D3 — batched in-process translation (F11; no Celery chord)
  §8.4  D8 — cancellation checkpoint between segments
  §10.3      — idempotency on redelivery
  §6         — queue name stage.nmt, routing keys job.start.nmt / job.results.nmt
  §4         — Claim Check: result carries lean summary only
  D1         — worker writes DB directly (jobs + video_tasks)
"""
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

import pika
from sqlalchemy import text

from app.config import settings
from dablja_worker import check_cancelled, classify_failure, consume_loop, make_engine
from app.model import NLLBTranslatorWrapper
from app.length_adjuster import adjust_ar

logger = logging.getLogger(__name__)

_translator = NLLBTranslatorWrapper()

EXCHANGE = "dablja.jobs.exchange"
NMT_QUEUE = "stage.nmt"
BINDING_KEY = "job.start.nmt"
RESULT_ROUTING_KEY = "job.results.nmt"
JOB_TYPE = "NMT_TRANSLATE"

_ENGINE, _SessionLocal = make_engine(settings.DATABASE_URL)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_db():
    return _ENGINE, _SessionLocal


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _watch_cancel(
    job_id: str,
    cancelled_flag: list,
    interval_s: float,
    stop_event: threading.Event,
) -> None:
    """Poll DB periodically; set cancelled_flag when job status is CANCELLED (H1/D8)."""
    while not stop_event.is_set():
        if stop_event.wait(interval_s):
            break
        try:
            with _SessionLocal() as db:
                if check_cancelled(db, job_id):
                    cancelled_flag[0] = True
                    logger.info("[NMT] job=%s cancelled mid-translation — watcher flagged", job_id)
                    return
        except Exception as exc:
            logger.warning("[NMT] cancel watcher DB error for job %s: %s", job_id, exc)


def _load_job(db, job_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT id, video_id, input_data, status, output_data, parent_job_id"
            " FROM jobs WHERE id = :jid"
        ),
        {"jid": job_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "video_id": row[1],
        "input_data": row[2] or {},
        "status": row[3],
        "output_data": row[4] or {},
        "parent_job_id": row[5],
    }


def _find_video_task_id(db, video_id: str) -> Optional[str]:
    """Fallback: resolve video_task when task_id is absent from input_data."""
    row = db.execute(
        text(
            "SELECT id FROM video_tasks WHERE video_id = :vid"
            " ORDER BY created_at DESC LIMIT 1"
        ),
        {"vid": video_id},
    ).fetchone()
    return row[0] if row else None


def _load_video_task(db, task_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT stt_segments, transcript, source_lang, target_lang,"
            " output_type, num_beams, english_ratio_threshold"
            " FROM video_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    ).fetchone()
    if not row:
        return None
    return {
        "stt_segments": row[0] or [],
        "transcript": row[1] or "",
        "source_lang": row[2],
        "target_lang": row[3] or "arb_Arab",
        "output_type": row[4] or "fullDubbing",
        "num_beams": row[5] if row[5] is not None else 5,
        "english_ratio_threshold": row[6] if row[6] is not None else 0.5,
    }


def _is_cancelled(db, job_id: str) -> bool:
    """D8: cooperative cancel check."""
    return check_cancelled(db, job_id)


def _update_job_processing(db, job_id: str):
    db.execute(
        text(
            "UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now"
            " WHERE id=:jid"
        ),
        {"now": _utcnow(), "jid": job_id},
    )
    db.commit()


def _update_video_task_nmt(
    db,
    task_id: str,
    translated_transcript: str,
    segments: list,
    output_type: str,
):
    """D1: write NMT output into video_tasks so TTS can read segments."""
    terminal = output_type == "captionsAndTranslation"
    status = "COMPLETED" if terminal else "PROCESSING"
    progress = 100.0 if terminal else 50.0
    completed_at = _utcnow() if terminal else None

    db.execute(
        text("""
            UPDATE video_tasks
               SET translated_transcript = :tr,
                   segments              = CAST(:segs AS jsonb),
                   status                = CAST(:status AS taskstatus),
                   progress              = :progress,
                   completed_at          = :completed_at,
                   updated_at            = :now
             WHERE id = :tid
        """),
        {
            "tr": translated_transcript,
            "segs": json.dumps(segments),
            "status": status,
            "progress": progress,
            "completed_at": completed_at,
            "now": _utcnow(),
            "tid": task_id,
        },
    )
    db.commit()


def _update_job_completed(db, job_id: str, output_data: dict):
    db.execute(
        text("""
            UPDATE jobs
               SET status='COMPLETED', output_data=CAST(:output AS jsonb),
                   progress=100.0, completed_at=:now, updated_at=:now
             WHERE id=:jid
        """),
        {"output": json.dumps(output_data), "now": _utcnow(), "jid": job_id},
    )
    db.commit()


def _update_job_failed(db, job_id: str, error: str):
    db.execute(
        text("""
            UPDATE jobs
               SET status='FAILED', error_message=:error,
                   completed_at=:now, updated_at=:now
             WHERE id=:jid
        """),
        {"error": error, "now": _utcnow(), "jid": job_id},
    )
    db.commit()


# ── Segment translation (batched inference + optional length adjust) ───────────

def _apply_length_adjust(idx: int, original: str, translated: str) -> str:
    """Groq-based length adjustment (I/O-bound); runs sequentially after batch infer."""
    if not settings.NMT_LENGTH_ADJUST_ENABLED or not translated or not original:
        return translated
    try:
        return adjust_ar(
            translated,
            original,
            scale=settings.NMT_LENGTH_ADJUST_SCALE,
            max_iters=settings.NMT_LENGTH_ADJUST_MAX_ITERS,
            groq_api_key=settings.GROQ_API_KEY,
            groq_model=settings.GROQ_MODEL,
        )
    except Exception as exc:
        logger.warning("[NMT] length adjust failed seg=%d: %s", idx, exc)
        return translated


def _translate_one_segment(
    idx: int,
    seg: dict,
    source_lang: Optional[str],
    target_lang: str,
    num_beams: int,
    english_ratio_threshold: float,
    is_cancelled: Callable[[], bool],
) -> Optional[dict]:
    """Translate a single segment. Returns None if job was cancelled."""
    if is_cancelled():
        return None

    text = seg.get("text", "").strip()
    try:
        translated = _translator.translate_segment(
            text,
            src_lang=source_lang,
            tgt_lang=target_lang,
            num_beams=num_beams,
            english_ratio_threshold=english_ratio_threshold,
        )
    except Exception as exc:
        logger.warning("[NMT] segment %d translation failed, using original: %s", idx, exc)
        translated = text

    # Length adjustment (Groq) — graceful fallback on failure
    translated = _apply_length_adjust(idx, text, translated)

    return {
        "start": seg.get("start"),
        "end": seg.get("end"),
        "original_text": text,
        "translated_text": translated,
    }


def _translate_all_segments(
    job_id: str,
    stt_segments: list,
    source_lang: Optional[str],
    target_lang: str,
    num_beams: int,
    english_ratio_threshold: float,
    cancelled_flag: list,  # [bool] — mutable so threads can see updates
) -> Optional[list]:
    """Translate all segments with batched inference (F11).

    Returns None if the job was cancelled mid-flight.
    """
    def is_cancelled() -> bool:
        return cancelled_flag[0]

    if is_cancelled():
        return None

    total = len(stt_segments)
    if total == 0:
        return []

    texts = [seg.get("text", "").strip() for seg in stt_segments]

    try:
        translated_texts = _translator.translate_segments_batch(
            texts,
            src_lang=source_lang,
            tgt_lang=target_lang,
            num_beams=num_beams,
            english_ratio_threshold=english_ratio_threshold,
            batch_size=settings.NMT_BATCH_SIZE,
            is_cancelled=is_cancelled,
        )
    except Exception as exc:
        logger.exception("[NMT] job=%s batch translation failed: %s", job_id, exc)
        translated_texts = None

    if translated_texts is None:
        logger.info("[NMT] job=%s cancelled mid-translation", job_id)
        return None

    results: list = []
    for idx, seg in enumerate(stt_segments):
        if is_cancelled():
            logger.info("[NMT] job=%s cancelled during length-adjust/post-process", job_id)
            return None

        translated = _apply_length_adjust(idx, texts[idx], translated_texts[idx])
        results.append({
            "start": seg.get("start"),
            "end": seg.get("end"),
            "original_text": texts[idx],
            "translated_text": translated,
        })
        completed = idx + 1
        if completed % 5 == 0 or completed == total:
            logger.info("[NMT] job=%s progress=%d/%d segments", job_id, completed, total)

    return results


# ── Job processing ────────────────────────────────────────────────────────────

def process_nmt_job(job_id: str, cancelled_flag: list) -> dict:
    """Load STT segments, translate in-process, write results. Returns lean summary."""
    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            job = _load_job(db, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found in DB")

            # §10.3 idempotency
            if job["status"] == "COMPLETED":
                logger.info("[NMT] job=%s already COMPLETED — skipping re-run", job_id)
                return job["output_data"]

            input_data = job["input_data"]
            video_id = job["video_id"] or input_data.get("video_id")
            task_id = input_data.get("task_id")
            if not task_id and video_id:
                task_id = _find_video_task_id(db, video_id)
                if task_id:
                    logger.debug(
                        "[NMT] job=%s resolved task_id=%s via video_id fallback",
                        job_id, task_id,
                    )

            if not task_id:
                raise ValueError(f"Job {job_id}: cannot resolve video_task (no task_id, no video_id)")

            vt = _load_video_task(db, task_id)
            if not vt:
                raise ValueError(f"VideoTask {task_id} not found")
            if not vt["stt_segments"]:
                raise ValueError(f"VideoTask {task_id} has no stt_segments — STT stage incomplete")

            source_lang = vt["source_lang"] or input_data.get("source_lang")
            target_lang = vt["target_lang"] or input_data.get("target_lang", "arb_Arab")
            num_beams = vt["num_beams"]
            english_ratio_threshold = vt["english_ratio_threshold"]
            output_type = vt["output_type"]
            stt_segments = list(vt["stt_segments"])
            full_transcript = vt["transcript"]

            _update_job_processing(db, job_id)
    finally:
        pass

    logger.info(
        "[NMT] job=%s task=%s segments=%d %s→%s output_type=%s",
        job_id, task_id, len(stt_segments), source_lang or "auto", target_lang, output_type,
    )

    # D3: internal fan-out — translate all segments in-process
    translated_segments = _translate_all_segments(
        job_id, stt_segments, source_lang, target_lang,
        num_beams, english_ratio_threshold, cancelled_flag,
    )

    if translated_segments is None:
        # Cancelled mid-translation — don't write any output
        raise RuntimeError(f"Job {job_id} cancelled during translation")

    translated_transcript = " ".join(
        s["translated_text"] for s in translated_segments
    ).strip()

    # Claim Check: lean summary for the result message
    summary = {
        "segment_count": len(translated_segments),
        "target_lang": target_lang,
        "output_type": output_type,
    }

    engine2, SessionLocal2 = _make_db()
    try:
        with SessionLocal2() as db:
            _update_video_task_nmt(
                db, task_id,
                translated_transcript=translated_transcript,
                segments=translated_segments,
                output_type=output_type,
            )
            _update_job_completed(db, job_id, summary)
    finally:
        pass

    logger.info(
        "[NMT] job=%s done | segments=%d | terminal=%s",
        job_id, len(translated_segments), output_type == "captionsAndTranslation",
    )
    return summary


# ── RabbitMQ consumer ─────────────────────────────────────────────────────────

def _publish_result(
    channel,
    job_id: str,
    status: str,
    output_data: Optional[dict] = None,
    error: Optional[str] = None,
):
    payload: dict = {
        "job_id": job_id,
        "job_type": JOB_TYPE,
        "status": status,
        "output_data": output_data or {},
    }
    if error:
        payload["error"] = error

    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=RESULT_ROUTING_KEY,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        ),
    )
    logger.info("[NMT] Published %s for job %s", status, job_id)


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error("[NMT] Bad JSON: %s", exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("[NMT] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[NMT] Received job %s", job_id)

    # D8: cooperative cancellation check before doing any work
    try:
        with _SessionLocal() as db:
            cancelled = _is_cancelled(db, job_id)
    except Exception as exc:
        logger.error("[NMT] DB unreachable checking cancel for job %s: %s", job_id, exc)
        if classify_failure(exc) == "transient":
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        else:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    if cancelled:
        logger.info("[NMT] Job %s is CANCELLED — skipping", job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    # Mutable flag so _translate_all_segments can detect mid-job cancellation
    cancelled_flag = [False]
    stop_event = threading.Event()
    watcher = threading.Thread(
        target=_watch_cancel,
        args=(job_id, cancelled_flag, 3.0, stop_event),
        name=f"nmt-cancel-{job_id}",
        daemon=True,
    )
    watcher.start()

    try:
        summary = process_nmt_job(job_id, cancelled_flag)
        _publish_result(channel, job_id, "COMPLETED", output_data=summary)
    except RuntimeError as exc:
        # Raised when cancelled mid-translation — ack without publishing FAILED
        if "cancelled" in str(exc).lower():
            logger.info("[NMT] Job %s cancelled mid-translation — acking silently", job_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        logger.exception("[NMT] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        _publish_result(channel, job_id, "FAILED", error=str(exc))
    except Exception as exc:
        logger.exception("[NMT] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        _publish_result(channel, job_id, "FAILED", error=str(exc))
    finally:
        stop_event.set()

    channel.basic_ack(delivery_tag=method.delivery_tag)


def _handle_failure(job_id: str, exc: Exception):
    try:
        with _SessionLocal() as db:
            _update_job_failed(db, job_id, str(exc))
    except Exception as db_exc:
        logger.error("[NMT] Could not mark job %s failed: %s", job_id, db_exc)


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    consume_loop(
        settings.RABBITMQ_URL,
        NMT_QUEUE,
        BINDING_KEY,
        EXCHANGE,
        on_message,
        service_name="NMT",
    )
