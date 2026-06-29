"""RabbitMQ consumer that processes STT jobs dispatched by the orchestrator."""
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from app.config import settings
from dablja_worker import check_cancelled, classify_failure, consume_loop, finish_job_message, make_engine
from app.model import WhisperModelManager
from app.storage import download_file

logger = logging.getLogger(__name__)

_whisper = WhisperModelManager()

EXCHANGE = "dablja.jobs.exchange"
STT_QUEUE = "stage.stt"           # §6: matches design doc queue name
BINDING_KEY = "job.start.stt"
RESULT_ROUTING_KEY = "job.results.stt"
JOB_TYPE = "STT_TRANSCRIBE"

_ENGINE, _SessionLocal = make_engine(settings.DATABASE_URL)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_db():
    return _ENGINE, _SessionLocal


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_job(db, job_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT id, video_id, input_data, status, output_data"
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
    }


def _load_video_audio_key(db, video_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT audio_path, file_path FROM videos WHERE id = :vid"),
        {"vid": video_id},
    ).fetchone()
    if not row:
        return None
    return row[0] or row[1]


def _find_video_task_id(db, video_id: str) -> Optional[str]:
    """Fallback lookup when task_id is absent from input_data."""
    row = db.execute(
        text(
            "SELECT id FROM video_tasks WHERE video_id = :vid"
            " ORDER BY created_at DESC LIMIT 1"
        ),
        {"vid": video_id},
    ).fetchone()
    return row[0] if row else None


def _is_cancelled(db, job_id: str) -> bool:
    """D8: check whether the job has been cancelled before doing any work."""
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


def _update_video_task(
    db, task_id: str, transcript: str, segments: list, metadata: dict
):
    """D1: write STT output into video_tasks so downstream NMT can read stt_segments."""
    source_lang = (metadata or {}).get("language")
    db.execute(
        text("""
            UPDATE video_tasks
               SET stt_segments = CAST(:segs AS jsonb),
                   transcript   = :tr,
                   stt_metadata = CAST(:meta AS jsonb),
                   source_lang  = COALESCE(:lang, source_lang),
                   updated_at   = :now
             WHERE id = :tid
        """),
        {
            "segs": json.dumps(segments),
            "tr": transcript,
            "meta": json.dumps(metadata),
            "lang": source_lang,
            "tid": task_id,
            "now": _utcnow(),
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
             WHERE id=:jid AND status != 'COMPLETED'
        """),
        {"error": error, "now": _utcnow(), "jid": job_id},
    )
    db.commit()


# ── Job processing ────────────────────────────────────────────────────────────

def process_stt_job(job_id: str) -> dict:
    """Download audio, transcribe with Whisper, persist result.

    Returns a lean summary dict (Claim Check — no raw transcripts on the wire).
    """
    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            job = _load_job(db, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found in DB")

            # §10.3 idempotency: redelivered messages must not reset a finished job.
            if job["status"] == "COMPLETED":
                logger.info("[STT] job=%s already COMPLETED — skipping re-run", job_id)
                return job["output_data"]

            input_data = job["input_data"]
            video_id = job["video_id"] or input_data.get("video_id")
            language = input_data.get("language")
            task_id = input_data.get("task_id")  # video_tasks.id
            if not task_id and video_id:
                task_id = _find_video_task_id(db, video_id)
                if task_id:
                    logger.debug(
                        "[STT] job=%s resolved task_id=%s via video_id fallback",
                        job_id, task_id,
                    )

            if not video_id:
                raise ValueError(f"Job {job_id} has no video_id")

            file_key = _load_video_audio_key(db, video_id)
            if not file_key:
                raise ValueError(f"No audio path for video {video_id}")

            _update_job_processing(db, job_id)
    finally:
        pass

    logger.info(
        "[STT] job=%s video=%s file_key=%s language=%s task_id=%s",
        job_id, video_id, file_key, language, task_id,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix = Path(file_key).suffix or ".mp3"
        local_path = str(Path(tmp_dir) / f"audio{suffix}")

        if not download_file(file_key, local_path):
            raise RuntimeError(f"Could not download {file_key} from MinIO")

        result = _whisper.transcribe(local_path, language=language)

    # Claim Check (§4, §15): result message carries only small summary references.
    # Full transcript and segments are written to video_tasks for downstream stages.
    summary = {
        "segment_count": len(result["segments"]),
        "language": result["metadata"].get("language"),
        "duration": result["metadata"].get("duration"),
    }

    engine2, SessionLocal2 = _make_db()
    try:
        with SessionLocal2() as db:
            if task_id:
                _update_video_task(
                    db, task_id,
                    transcript=result["transcript"],
                    segments=result["segments"],
                    metadata=result["metadata"],
                )
            else:
                logger.warning(
                    "[STT] job=%s could not resolve video_task"
                    " — stt_segments not written to video_tasks", job_id
                )
            _update_job_completed(db, job_id, summary)
    finally:
        pass

    return summary


# ── RabbitMQ consumer ─────────────────────────────────────────────────────────

def _handle_failure(job_id: str, exc: Exception) -> None:
    try:
        with _SessionLocal() as db:
            _update_job_failed(db, job_id, str(exc))
    except Exception as db_exc:
        logger.error("[STT] Could not mark job %s failed: %s", job_id, db_exc)


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error("[STT] Bad JSON in message: %s", exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("[STT] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[STT] Received job %s", job_id)

    # D8: cooperative cancellation — check before doing any work.
    try:
        with _SessionLocal() as db:
            cancelled = _is_cancelled(db, job_id)
    except Exception as exc:
        logger.error("[STT] DB unreachable checking cancel for job %s: %s", job_id, exc)
        if classify_failure(exc) == "transient":
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        else:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    if cancelled:
        logger.info("[STT] Job %s is CANCELLED — skipping", job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    finish_job_message(
        channel=channel,
        delivery_tag=method.delivery_tag,
        rabbitmq_url=settings.RABBITMQ_URL,
        result_routing_key=RESULT_ROUTING_KEY,
        job_id=job_id,
        job_type=JOB_TYPE,
        session_factory=_SessionLocal,
        process_fn=lambda: process_stt_job(job_id),
        mark_failure_fn=_handle_failure,
        service_name="STT",
    )


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    consume_loop(
        settings.RABBITMQ_URL,
        STT_QUEUE,
        BINDING_KEY,
        EXCHANGE,
        on_message,
        service_name="STT",
    )
