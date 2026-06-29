"""RabbitMQ consumer for the dubbing merge stage (DUBBING_MERGE).

Design references:
  §6   — queue stage.merge, routing keys job.start.merge / job.results.merge
  §4   — Claim Check: lean AMQP summary; full artifacts in S3 + DB
  D1   — worker writes DB directly
  §10.3 — idempotency on redelivery
  D8   — cooperative cancellation pre-check
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.config import settings
from app.mux import mux_video_with_audio
from dablja_worker import (
    check_cancelled,
    classify_failure,
    consume_loop,
    finish_job_message,
    is_completed,
    make_engine,
    mark_completed,
    mark_failed,
    mark_processing,
)

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
MERGE_QUEUE = "stage.merge"
BINDING_KEY = "job.start.merge"
RESULT_ROUTING_KEY = "job.results.merge"
JOB_TYPE = "DUBBING_MERGE"

_ENGINE, _SessionLocal = make_engine(settings.sync_db_url)


def _make_db():
    return _ENGINE, _SessionLocal


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
            "SELECT id, video_id, combined_audio_key, output_type"
            " FROM video_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "video_id": row[1],
        "combined_audio_key": row[2],
        "output_type": row[3] or "fullDubbing",
    }


def _load_video(db, video_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT id, file_path, audio_path, media_type"
            " FROM videos WHERE id = :vid"
        ),
        {"vid": video_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "file_path": row[1],
        "audio_path": row[2],
        "media_type": row[3] or "video",
    }


def _update_video_task_completed(db, task_id: str, combined_audio_key: Optional[str] = None):
    db.execute(
        text("""
            UPDATE video_tasks
               SET status = 'COMPLETED',
                   progress = 100.0,
                   combined_audio_key = COALESCE(:combined_key, combined_audio_key),
                   completed_at = :now,
                   updated_at = :now
             WHERE id = :tid
        """),
        {
            "combined_key": combined_audio_key,
            "now": _utcnow(),
            "tid": task_id,
        },
    )
    db.commit()


def _update_video_dubbed(db, video_id: str, dubbed_video_key: Optional[str]):
    if not dubbed_video_key:
        return
    db.execute(
        text(
            "UPDATE videos SET dubbed_video_path = :key, updated_at = :now"
            " WHERE id = :vid"
        ),
        {"key": dubbed_video_key, "now": _utcnow(), "vid": video_id},
    )
    db.commit()


def process_merge_job(job_id: str) -> dict:
    """Mux TTS combined audio with original video (mux-only — no segment re-concat)."""
    import asyncio

    with _SessionLocal() as db:
        job = _load_job(db, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found in DB")

        if is_completed(db, job_id):
            logger.info("[merge] job=%s already COMPLETED — skipping", job_id)
            return job["output_data"]

        input_data = job["input_data"]
        video_id = job["video_id"] or input_data.get("video_id")
        task_id = input_data.get("task_id")
        if not task_id and video_id:
            task_id = _find_video_task_id(db, video_id)
        if not task_id:
            raise ValueError(f"Job {job_id}: cannot resolve video_task")
        if not video_id:
            raise ValueError(f"Job {job_id} has no video_id")

        vt = _load_video_task(db, task_id)
        if not vt:
            raise ValueError(f"VideoTask {task_id} not found")

        combined_key = vt.get("combined_audio_key")
        if not combined_key:
            raise ValueError(
                f"TTS stage incomplete — no combined_audio_key on task {task_id}"
            )

        video = _load_video(db, video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")

        mark_processing(db, job_id)

    media_type = str(video.get("media_type") or "video").lower()
    original_key = (
        video.get("file_path")
        if media_type == "video"
        else (video.get("audio_path") or video.get("file_path"))
    )

    logger.info(
        "[merge] job=%s video=%s task=%s combined_key=%s media_type=%s",
        job_id,
        video_id,
        task_id,
        combined_key,
        media_type,
    )

    if media_type == "video" and original_key:
        dubbed_key = f"dubbed/{video_id}/dubbed_{job_id}.mp4"
        merge_result = asyncio.run(
            mux_video_with_audio(
                video_key=original_key,
                audio_key=combined_key,
                output_key=dubbed_key,
                temp_dir=settings.MERGE_TEMP_DIR,
            )
        )
    else:
        logger.info(
            "[merge] job=%s skipping video mux (media_type=%s) — audio-only path",
            job_id,
            media_type,
        )
        merge_result = {
            "combined_audio_key": combined_key,
            "dubbed_video_key": None,
        }

    summary = {
        "combined_audio_key": merge_result.get("combined_audio_key") or combined_key,
        "dubbed_video_key": merge_result.get("dubbed_video_key"),
    }

    with _SessionLocal() as db:
        _update_video_task_completed(db, task_id, summary["combined_audio_key"])
        _update_video_dubbed(db, video_id, summary.get("dubbed_video_key"))
        mark_completed(db, job_id, summary, progress=100.0)

    logger.info("[merge] job=%s done | dubbed=%s", job_id, summary.get("dubbed_video_key"))
    return summary


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error("[merge] Bad JSON: %s", exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("[merge] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[merge] Received job %s", job_id)

    try:
        with _SessionLocal() as db:
            cancelled = check_cancelled(db, job_id)
    except Exception as exc:
        logger.error("[merge] DB unreachable checking cancel for job %s: %s", job_id, exc)
        if classify_failure(exc) == "transient":
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        else:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    if cancelled:
        logger.info("[merge] Job %s is CANCELLED — skipping", job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    def _mark_failure(job_id: str, exc: Exception) -> None:
        try:
            with _SessionLocal() as db:
                mark_failed(db, job_id, str(exc))
        except Exception as db_exc:
            logger.error("[merge] Could not mark job %s failed: %s", job_id, db_exc)

    finish_job_message(
        channel=channel,
        delivery_tag=method.delivery_tag,
        rabbitmq_url=settings.RABBITMQ_URL,
        result_routing_key=RESULT_ROUTING_KEY,
        job_id=job_id,
        job_type=JOB_TYPE,
        session_factory=_SessionLocal,
        process_fn=lambda: process_merge_job(job_id),
        mark_failure_fn=_mark_failure,
        service_name="MERGE",
    )


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    consume_loop(
        settings.RABBITMQ_URL,
        MERGE_QUEUE,
        BINDING_KEY,
        EXCHANGE,
        on_message,
        service_name="MERGE",
    )
