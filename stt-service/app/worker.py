"""RabbitMQ consumer that processes STT jobs dispatched by the orchestrator."""
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pika
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.model import WhisperModelManager
from app.storage import download_file

logger = logging.getLogger(__name__)

_whisper = WhisperModelManager()

EXCHANGE = "dablja.jobs.exchange"
STT_QUEUE = "stt.jobs"
BINDING_KEY = "job.start.stt"
RESULT_ROUTING_KEY = "job.results.stt"
JOB_TYPE = "STT_TRANSCRIBE"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_db():
    engine = create_engine(settings.DATABASE_URL)
    return engine, sessionmaker(bind=engine)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_job(db, job_id: str) -> Optional[dict]:
    row = db.execute(
        text("SELECT id, video_id, input_data FROM jobs WHERE id = :jid"),
        {"jid": job_id},
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "video_id": row[1], "input_data": row[2] or {}}


def _load_video_audio_key(db, video_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT audio_path, file_path FROM videos WHERE id = :vid"),
        {"vid": video_id},
    ).fetchone()
    if not row:
        return None
    return row[0] or row[1]


def _update_job_processing(db, job_id: str):
    db.execute(
        text(
            "UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now WHERE id=:jid"
        ),
        {"now": _utcnow(), "jid": job_id},
    )
    db.commit()


def _update_job_completed(db, job_id: str, output_data: dict):
    db.execute(
        text(
            """UPDATE jobs
               SET status='COMPLETED', output_data=CAST(:output AS jsonb),
                   progress=100.0, completed_at=:now, updated_at=:now
               WHERE id=:jid"""
        ),
        {"output": json.dumps(output_data), "now": _utcnow(), "jid": job_id},
    )
    db.commit()


def _update_job_failed(db, job_id: str, error: str):
    db.execute(
        text(
            """UPDATE jobs
               SET status='FAILED', error_message=:error,
                   completed_at=:now, updated_at=:now
               WHERE id=:jid"""
        ),
        {"error": error, "now": _utcnow(), "jid": job_id},
    )
    db.commit()


# ── Job processing ────────────────────────────────────────────────────────────

def process_stt_job(job_id: str) -> dict:
    """Download audio, transcribe with Whisper, persist result. Returns the result dict."""
    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            job = _load_job(db, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found in DB")

            input_data = job["input_data"]
            video_id = job["video_id"] or input_data.get("video_id")
            language = input_data.get("language")

            if not video_id:
                raise ValueError(f"Job {job_id} has no video_id")

            file_key = _load_video_audio_key(db, video_id)
            if not file_key:
                raise ValueError(f"No audio path for video {video_id}")

            _update_job_processing(db, job_id)
    finally:
        engine.dispose()

    logger.info("[STT] job=%s video=%s file_key=%s language=%s", job_id, video_id, file_key, language)

    # Download audio to temp dir
    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix = Path(file_key).suffix or ".mp3"
        local_path = str(Path(tmp_dir) / f"audio{suffix}")

        if not download_file(file_key, local_path):
            raise RuntimeError(f"Could not download {file_key} from MinIO")

        result = _whisper.transcribe(local_path, language=language)

    output = {
        "job_id": job_id,
        "video_id": video_id,
        "transcript": result["transcript"],
        "segments": result["segments"],
        "metadata": result["metadata"],
    }

    engine2, SessionLocal2 = _make_db()
    try:
        with SessionLocal2() as db:
            _update_job_completed(db, job_id, output)
    finally:
        engine2.dispose()

    return output


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
            delivery_mode=2,  # persistent
        ),
    )
    logger.info("[STT] Published %s for job %s to %s", status, job_id, RESULT_ROUTING_KEY)


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

    try:
        output = process_stt_job(job_id)
        _publish_result(channel, job_id, "COMPLETED", output_data=output)
    except Exception as exc:
        logger.exception("[STT] Job %s failed: %s", job_id, exc)
        # Mark failed in DB
        try:
            engine, SessionLocal = _make_db()
            with SessionLocal() as db:
                _update_job_failed(db, job_id, str(exc))
            engine.dispose()
        except Exception as db_exc:
            logger.error("[STT] Could not update job %s as failed: %s", job_id, db_exc)

        _publish_result(channel, job_id, "FAILED", error=str(exc))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    logger.info("[STT] Connecting to RabbitMQ: %s", settings.RABBITMQ_URL)

    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Idempotent topology declarations (must match the orchestrator)
    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare("dablja.jobs.dlx", exchange_type="direct", durable=True)

    channel.queue_declare(
        STT_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "dablja.jobs.dlx"},
    )
    channel.queue_bind(STT_QUEUE, EXCHANGE, BINDING_KEY)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(STT_QUEUE, on_message)

    logger.info("[STT] Waiting for jobs on routing key '%s' (queue='%s')", BINDING_KEY, STT_QUEUE)
    channel.start_consuming()
