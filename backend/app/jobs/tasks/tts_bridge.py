"""Temporary bridge: consume job.start.tts from RabbitMQ → dispatch Celery TTS tasks.

This is scaffolding until TTS is migrated to its own microservice (Phase 6).
The bridge handles:
  1. Reading the TTS child job and its video_task (translated segments)
  2. Dispatching one tts_synthesize_segment Celery task per segment
  3. The Redis counter in tts_synthesize_segment triggers tts_combine_results automatically

Start this via:
    from app.jobs.tasks.tts_bridge import start_tts_bridge
    threading.Thread(target=start_tts_bridge, daemon=True).start()

Removed when TTS becomes a RabbitMQ microservice.
"""
import json
import logging
import time
from datetime import datetime, timezone

import pika
from sqlalchemy import text

from app.config import settings
from app.jobs.celery_app import celery_app
from app.shared.dablja_worker import consume_loop, make_engine

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
TTS_QUEUE = "stage.tts"
BINDING_KEY = "job.start.tts"
RESULT_KEY = "job.results.tts"
JOB_TYPE = "TTS_SYNTHESIZE"

_SYNC_DB_URL = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
_ENGINE, _SessionLocal = make_engine(_SYNC_DB_URL)


def _make_db():
    return _ENGINE, _SessionLocal


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _publish_result(channel, job_id: str, status: str, error: str | None = None):
    payload: dict = {
        "job_id": job_id,
        "job_type": JOB_TYPE,
        "status": status,
        "output_data": {},
    }
    if error:
        payload["error"] = error

    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=RESULT_KEY,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        ),
    )
    logger.info("[TTS-BRIDGE] Published %s for job %s", status, job_id)


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("[TTS-BRIDGE] Bad JSON — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    tts_job_id = payload.get("job_id")
    if not tts_job_id:
        logger.error("[TTS-BRIDGE] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[TTS-BRIDGE] Received job %s", tts_job_id)

    try:
        with _SessionLocal() as db:
            jrow = db.execute(
                text(
                    "SELECT video_id, input_data, status"
                    " FROM jobs WHERE id = :jid"
                ),
                {"jid": tts_job_id},
            ).fetchone()
            if not jrow:
                raise ValueError(f"TTS child job {tts_job_id} not found")

            if jrow[2] == "COMPLETED":
                logger.info("[TTS-BRIDGE] job=%s already COMPLETED — skipping", tts_job_id)
                channel.basic_ack(delivery_tag=method.delivery_tag)
                return

            video_id = jrow[0]
            input_data = jrow[1] or {}
            task_id = input_data.get("task_id")

            if not task_id:
                raise ValueError(f"No task_id in input_data for job {tts_job_id}")

            vt = db.execute(
                text(
                    "SELECT segments, output_type FROM video_tasks WHERE id = :tid"
                ),
                {"tid": task_id},
            ).fetchone()
            if not vt or not vt[0]:
                raise ValueError(f"No translated segments in video_task {task_id}")

            translated_segments = list(vt[0])
            output_type = vt[1] or "fullDubbing"

            # Mark TTS child as PROCESSING
            db.execute(
                text(
                    "UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now"
                    " WHERE id = :jid"
                ),
                {"now": _utcnow(), "jid": tts_job_id},
            )
            db.commit()

        total = len(translated_segments)
        enqueued_at = time.time()

        logger.info(
            "[TTS-BRIDGE] Dispatching %d TTS segments for job %s (task=%s, output_type=%s)",
            total, tts_job_id, task_id, output_type,
        )

        for idx, seg in enumerate(translated_segments):
            translated_text = seg.get("translated_text", "")
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start + 0.001))
            minio_key = f"tts/{video_id}/segment_{idx}.wav"

            celery_app.send_task(
                "app.jobs.tasks.pipeline.tts_synthesize_segment",
                args=[idx, tts_job_id, translated_text, start, end, minio_key, None],
                kwargs={
                    "tts_job_id": tts_job_id,
                    "total_segments": total,
                    "task_id": task_id,
                    "video_id": video_id,
                    "output_type": output_type,
                    "enqueued_at": enqueued_at,
                },
                queue="ai_tts",
            )

        logger.info(
            "[TTS-BRIDGE] All %d segments dispatched for job %s", total, tts_job_id
        )

    except Exception as exc:
        logger.exception("[TTS-BRIDGE] Job %s failed: %s", tts_job_id, exc)
        try:
            with _SessionLocal() as db:
                db.execute(
                    text(
                        "UPDATE jobs SET status='FAILED', error_message=:err,"
                        " completed_at=:now, updated_at=:now WHERE id = :jid"
                    ),
                    {"err": str(exc), "now": _utcnow(), "jid": tts_job_id},
                )
                db.commit()
        except Exception as db_exc:
            logger.error("[TTS-BRIDGE] Could not mark job %s failed: %s", tts_job_id, db_exc)

        _publish_result(channel, tts_job_id, "FAILED", error=str(exc))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def start_tts_bridge():
    """Connect to RabbitMQ, declare topology, start consuming (blocking)."""
    consume_loop(
        settings.RABBITMQ_URL,
        TTS_QUEUE,
        BINDING_KEY,
        EXCHANGE,
        on_message,
        service_name="TTS-BRIDGE",
    )
