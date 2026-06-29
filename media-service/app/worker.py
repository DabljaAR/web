"""RabbitMQ consumer that processes the dubbing merge stage (DUBBING_MERGE).

Design references:
  §6   — queue name stage.merge, routing keys job.start.merge / job.results.merge
  §4   — Claim Check: result carries lean summary only
  D1   — worker writes DB directly (jobs + video_tasks)
  §10.3 — idempotency on redelivery
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pika
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
MERGE_QUEUE = "stage.merge"
BINDING_KEY = "job.start.merge"
RESULT_ROUTING_KEY = "job.results.merge"
JOB_TYPE = "DUBBING_MERGE"


def _make_db():
    engine = create_engine(settings.sync_db_url)
    return engine, sessionmaker(bind=engine)


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
            "SELECT id, video_id, segments, combined_audio_key,"
            " output_type, source_lang, target_lang"
            " FROM video_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "video_id": row[1],
        "segments": row[2] or [],
        "combined_audio_key": row[3],
        "output_type": row[4] or "fullDubbing",
        "source_lang": row[5],
        "target_lang": row[6],
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


def _update_job_processing(db, job_id: str):
    db.execute(
        text(
            "UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now"
            " WHERE id=:jid"
        ),
        {"now": _utcnow(), "jid": job_id},
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


def _update_video_task_merge(db, task_id: str, combined_audio_key: Optional[str] = None):
    db.execute(
        text("""
            UPDATE video_tasks
               SET status='COMPLETED',
                   combined_audio_key = COALESCE(:combined_key, combined_audio_key),
                   progress = 100.0,
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


# ── Job processing ────────────────────────────────────────────────────────────

def process_merge_job(job_id: str) -> dict:
    """Load translated segments, merge audio, optionally mux with video.

    Returns a lean summary dict (Claim Check).
    """
    import asyncio
    from app.merge import merge_segments

    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            job = _load_job(db, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found in DB")

            if job["status"] == "COMPLETED":
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

            segments = list(vt["segments"])
            if not segments:
                raise ValueError(f"VideoTask {task_id} has no translated segments")

            video = _load_video(db, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found")

            _update_job_processing(db, job_id)
    finally:
        engine.dispose()

    logger.info(
        "[merge] job=%s video=%s task=%s segments=%d media_type=%s",
        job_id, video_id, task_id, len(segments), video.get("media_type", "video"),
    )

    # Resolve original media key
    media_type = str(video.get("media_type") or "video").lower()
    original_key = video.get("file_path") if media_type == "video" else (video.get("audio_path") or video.get("file_path"))

    # Build segment info for merge
    segment_infos: list[dict] = []
    for idx, seg in enumerate(segments):
        tts_key = seg.get("tts_key") or seg.get("tts_audio_key")
        if not tts_key:
            continue
        start_val = float(seg.get("start") or 0)
        end_val = float(seg.get("end") or start_val)
        segment_infos.append({
            "segment_id": idx,
            "start": start_val,
            "end": end_val if end_val > start_val else start_val + 0.001,
            "duration": max(end_val - start_val, 0.001),
            "tts_audio_key": tts_key,
            "translated_text": str(seg.get("translated_text") or ""),
        })

    if not segment_infos:
        raise RuntimeError(f"No segments with TTS audio keys for job {job_id}")

    combined_audio_key = f"tts/{job_id}/combined_{job_id}.wav"

    merge_result = asyncio.run(
        merge_segments(
            segments=segment_infos,
            video_id=str(video_id),
            job_id=job_id,
            original_media_key=original_key if media_type == "video" else None,
            output_key_prefix=f"dubbed/{video_id}",
            combined_audio_key=combined_audio_key,
            temp_dir=settings.MERGE_TEMP_DIR,
        )
    )

    summary = {
        "segment_count": len(segment_infos),
        "combined_audio_key": merge_result.get("combined_audio_key"),
        "dubbed_video_key": merge_result.get("dubbed_video_key"),
    }

    engine2, SessionLocal2 = _make_db()
    try:
        with SessionLocal2() as db:
            _update_video_task_merge(
                db, task_id,
                combined_audio_key=merge_result.get("combined_audio_key"),
            )
            _update_video_dubbed(
                db, video_id,
                merge_result.get("dubbed_video_key"),
            )
            _update_job_completed(db, job_id, summary)
    finally:
        engine2.dispose()

    logger.info("[merge] job=%s done | segments=%d", job_id, len(segment_infos))
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
    logger.info("[merge] Published %s for job %s to %s", status, job_id, RESULT_ROUTING_KEY)


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
        summary = process_merge_job(job_id)
        _publish_result(channel, job_id, "COMPLETED", output_data=summary)
    except Exception as exc:
        logger.exception("[merge] Job %s failed: %s", job_id, exc)
        try:
            engine, SessionLocal = _make_db()
            with SessionLocal() as db:
                _update_job_failed(db, job_id, str(exc))
            engine.dispose()
        except Exception as db_exc:
            logger.error("[merge] Could not mark job %s failed: %s", job_id, db_exc)
        _publish_result(channel, job_id, "FAILED", error=str(exc))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    logger.info("[merge] Connecting to RabbitMQ: %s", settings.RABBITMQ_URL)

    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare("dablja.jobs.dlx", exchange_type="direct", durable=True)

    channel.queue_declare(
        MERGE_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "dablja.jobs.dlx"},
    )
    channel.queue_bind(MERGE_QUEUE, EXCHANGE, BINDING_KEY)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(MERGE_QUEUE, on_message)

    logger.info(
        "[merge] Waiting for jobs on routing key '%s' (queue='%s')",
        BINDING_KEY, MERGE_QUEUE,
    )
    channel.start_consuming()
