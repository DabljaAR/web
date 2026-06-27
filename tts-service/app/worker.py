"""RabbitMQ consumer that processes TTS synthesis jobs (DUBBING_MERGE pipeline stage).

Design references:
  §8.3  D4 — internal per-segment loop + audio combine (no Redis counter)
  §8.4  D8 — cancellation check between segments
  §10.3     — idempotency on redelivery
  §6    — queue stage.tts, routing keys job.start.tts / job.results.tts
  §4    — Claim Check: result carries lean summary only
  D1    — worker writes DB directly (jobs + video_tasks)
"""
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
import pika
from botocore.config import Config as BotoConfig
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.model import _tts

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
TTS_QUEUE = "stage.tts"
BINDING_KEY = "job.start.tts"
RESULT_ROUTING_KEY = "job.results.tts"
JOB_TYPE = "TTS_SYNTHESIZE"


# ── S3 client ─────────────────────────────────────────────────────────────────

_s3_client: Optional[object] = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint(),
            aws_access_key_id=settings.s3_access_key(),
            aws_secret_access_key=settings.s3_secret_key(),
            config=BotoConfig(signature_version="s3v4"),
        )
    return _s3_client


def _upload_wav(audio_bytes: bytes, key: str) -> str:
    """Upload WAV bytes to MinIO/S3. Returns the object key (same as input)."""
    import io
    buf = io.BytesIO(audio_bytes)
    _get_s3().upload_fileobj(buf, settings.S3_MEDIA_BUCKET, key, ExtraArgs={"ContentType": "audio/wav"})
    logger.debug("[TTS] uploaded %dB → s3://%s/%s", len(audio_bytes), settings.S3_MEDIA_BUCKET, key)
    return key


# ── DB helpers ────────────────────────────────────────────────────────────────


def _make_db():
    engine = create_engine(settings.DATABASE_URL)
    return engine, sessionmaker(bind=engine)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_job(db, job_id: str) -> Optional[dict]:
    row = db.execute(
        text("SELECT id, video_id, input_data, status, output_data, parent_job_id FROM jobs WHERE id = :jid"),
        {"jid": job_id},
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "video_id": row[1], "input_data": row[2] or {}, "status": row[3], "output_data": row[4] or {}, "parent_job_id": row[5]}


def _find_video_task_id(db, video_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM video_tasks WHERE video_id = :vid ORDER BY created_at DESC LIMIT 1"),
        {"vid": video_id},
    ).fetchone()
    return row[0] if row else None


def _load_video_task(db, task_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT segments, output_type, source_lang, target_lang"
            " FROM video_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    ).fetchone()
    if not row:
        return None
    return {"segments": row[0] or [], "output_type": row[1] or "fullDubbing", "source_lang": row[2], "target_lang": row[3]}


def _is_cancelled(db, job_id: str) -> bool:
    row = db.execute(text("SELECT status FROM jobs WHERE id = :jid"), {"jid": job_id}).fetchone()
    return row is not None and row[0] == "CANCELLED"


def _update_job_processing(db, job_id: str):
    db.execute(
        text("UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now WHERE id=:jid"),
        {"now": _utcnow(), "jid": job_id},
    )
    db.commit()


def _update_video_task_segments(db, task_id: str, segments: list, output_type: str):
    terminal = output_type == "translationAndTTS"
    status = "COMPLETED" if terminal else "PROCESSING"
    progress = 75.0 if terminal else 55.0
    db.execute(
        text("""
            UPDATE video_tasks
               SET segments    = CAST(:segs AS jsonb),
                   status      = CAST(:status AS taskstatus),
                   progress    = :progress,
                   updated_at  = :now
             WHERE id = :tid
        """),
        {"segs": json.dumps(segments), "status": status, "progress": progress, "now": _utcnow(), "tid": task_id},
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


# ── Job processing ────────────────────────────────────────────────────────────


def process_tts_job(job_id: str, cancelled_flag: list) -> dict:
    """Load translated segments, synthesize TTS per segment, upload to MinIO, write results."""
    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            job = _load_job(db, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            if job["status"] == "COMPLETED":
                logger.info("[TTS] job=%s already COMPLETED — skipping re-run", job_id)
                return job["output_data"]

            input_data = job["input_data"]
            video_id = job["video_id"] or input_data.get("video_id")
            task_id = input_data.get("task_id")
            if not task_id and video_id:
                task_id = _find_video_task_id(db, video_id)
            if not task_id:
                raise ValueError(f"No task_id for job {job_id}")

            vt = _load_video_task(db, task_id)
            if not vt:
                raise ValueError(f"VideoTask {task_id} not found")
            if not vt["segments"]:
                raise ValueError(f"VideoTask {task_id} has no segments — NMT stage incomplete")

            output_type = vt["output_type"]
            translated_segments = list(vt["segments"])

            _update_job_processing(db, job_id)
    finally:
        engine.dispose()

    total = len(translated_segments)
    logger.info("[TTS] job=%s task=%s segments=%d output_type=%s", job_id, task_id, total, output_type)

    tts_segments = []
    failed_count = 0

    for idx, seg in enumerate(translated_segments):
        # D8: cooperative cancel between segments
        if cancelled_flag[0]:
            logger.info("[TTS] job=%s cancelled at segment %d/%d", job_id, idx, total)
            raise RuntimeError(f"Job {job_id} cancelled during TTS synthesis")

        seg = dict(seg)
        translated_text = seg.get("translated_text", "")
        if not translated_text.strip():
            tts_segments.append(seg)
            continue

        minio_key = f"tts/{video_id}/segment_{idx}.wav"
        logger.info("[TTS] segment %d/%d | job=%s | chars=%d", idx + 1, total, job_id, len(translated_text))

        try:
            audio_bytes = _tts.synthesize(text=translated_text)
            _upload_wav(audio_bytes, minio_key)

            seg["tts_key"] = minio_key
            seg["tts_audio_key"] = minio_key
            tts_segments.append(seg)
            logger.info("[TTS] segment %d/%d done | job=%s | bytes=%d", idx + 1, total, job_id, len(audio_bytes))

        except Exception as exc:
            logger.exception("[TTS] segment %d/%d failed | job=%s: %s", idx + 1, total, job_id, exc)
            seg["tts_error"] = str(exc)
            tts_segments.append(seg)
            failed_count += 1

    all_failed = failed_count == total
    summary = {
        "segment_count": total,
        "tts_segments": total - failed_count,
        "tts_failed": failed_count,
        "output_type": output_type,
    }

    engine2, SessionLocal2 = _make_db()
    try:
        with SessionLocal2() as db:
            _update_video_task_segments(db, task_id, tts_segments, output_type)

            if all_failed:
                _update_job_failed(db, job_id, f"TTS failed for all {total} segments")
            else:
                _update_job_completed(db, job_id, summary)
    finally:
        engine2.dispose()

    logger.info(
        "[TTS] job=%s done | segments=%d | failed=%d | terminal=%s",
        job_id, total, failed_count, output_type == "translationAndTTS",
    )
    return summary


# ── RabbitMQ consumer ─────────────────────────────────────────────────────────


def _publish_result(channel, job_id: str, status: str, output_data: Optional[dict] = None, error: Optional[str] = None):
    payload: dict = {"job_id": job_id, "job_type": JOB_TYPE, "status": status, "output_data": output_data or {}}
    if error:
        payload["error"] = error
    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=RESULT_ROUTING_KEY,
        body=json.dumps(payload),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    logger.info("[TTS] Published %s for job %s", status, job_id)


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("[TTS] Bad JSON — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("[TTS] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[TTS] Received job %s", job_id)

    try:
        engine, SessionLocal = _make_db()
        with SessionLocal() as db:
            cancelled = _is_cancelled(db, job_id)
        engine.dispose()
    except Exception as exc:
        logger.error("[TTS] DB unreachable checking cancel for job %s: %s", job_id, exc)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    if cancelled:
        logger.info("[TTS] Job %s is CANCELLED — skipping", job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    cancelled_flag = [False]

    try:
        summary = process_tts_job(job_id, cancelled_flag)
        _publish_result(channel, job_id, "COMPLETED", output_data=summary)
    except RuntimeError as exc:
        if "cancelled" in str(exc).lower():
            logger.info("[TTS] Job %s cancelled mid-synthesis — acking silently", job_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        _publish_result(channel, job_id, "FAILED", error=str(exc))
    except Exception as exc:
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        _publish_result(channel, job_id, "FAILED", error=str(exc))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def _handle_failure(job_id: str, exc: Exception):
    try:
        engine, SessionLocal = _make_db()
        with SessionLocal() as db:
            _update_job_failed(db, job_id, str(exc))
        engine.dispose()
    except Exception as db_exc:
        logger.error("[TTS] Could not mark job %s failed: %s", job_id, db_exc)


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    logger.info("[TTS] Connecting to RabbitMQ: %s", settings.RABBITMQ_URL)

    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = settings.RABBITMQ_HEARTBEAT
    params.blocked_connection_timeout = settings.RABBITMQ_BLOCKED_TIMEOUT

    max_retries = settings.RABBITMQ_MAX_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            connection = pika.BlockingConnection(params)
            break
        except pika.exceptions.AMQPConnectionError as e:
            if attempt == max_retries:
                logger.error("[TTS] Could not connect to RabbitMQ after %d attempts", max_retries)
                raise
            wait = min(2 ** attempt, 30)
            logger.warning("[TTS] RabbitMQ not ready (attempt %d/%d), retrying in %ds: %s", attempt, max_retries, wait, e)
            time.sleep(wait)

    channel = connection.channel()

    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare("dablja.jobs.dlx", exchange_type="direct", durable=True)

    channel.queue_declare(
        TTS_QUEUE, durable=True,
        arguments={"x-dead-letter-exchange": "dablja.jobs.dlx"},
    )
    channel.queue_bind(TTS_QUEUE, EXCHANGE, BINDING_KEY)

    channel.basic_qos(prefetch_count=settings.RABBITMQ_PREFETCH)
    channel.basic_consume(TTS_QUEUE, on_message)

    logger.info("[TTS] Waiting for jobs on routing key '%s' (queue='%s')", BINDING_KEY, TTS_QUEUE)
    channel.start_consuming()
