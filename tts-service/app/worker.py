"""RabbitMQ consumer for TTS microservice.
Consumes ``job.start.tts`` and publishes results to ``job.results.tts``.
"""
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

import pika
import soundfile as sf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.model import OmniVoiceManager
from app.storage import upload_audio

logger = logging.getLogger(__name__)

_EXCHANGE = "dablja.jobs.exchange"
_DLX = "dablja.jobs.dlx"
_QUEUE = "stage.tts"
_BINDING_KEY = "job.start.tts"
_RESULT_KEY = "job.results.tts"
_PREFETCH = 1


# ─── DB helpers (sync psycopg2 + NullPool) ────────────────────────────────

def _make_engine():
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, poolclass=NullPool)
    return engine, sessionmaker(bind=engine)


def _load_job(job_id: str) -> Optional[Dict[str, Any]]:
    from sqlalchemy import text as sa_text
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            row = db.execute(
                sa_text("SELECT * FROM jobs WHERE id = :id"),
                {"id": job_id},
            ).mappings().first()
            if row is None:
                return None
            return dict(row)
    finally:
        engine.dispose()


def _create_child_job(parent_job_id: str, job_type: str) -> str:
    from sqlalchemy import text as sa_text
    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            parent = db.execute(
                sa_text("SELECT * FROM jobs WHERE id = :id"),
                {"id": parent_job_id},
            ).mappings().first()
            if not parent:
                raise ValueError(f"Parent job {parent_job_id} not found")

            db.execute(
                sa_text("""
                    INSERT INTO jobs (id, parent_job_id, job_type, status, user_id, video_id,
                                      input_data, progress, created_at, updated_at)
                    VALUES (:id, :parent_job_id, :job_type, :status, :user_id, :video_id,
                            :input_data, 0.0, :now, :now)
                """),
                {
                    "id": new_id,
                    "parent_job_id": parent_job_id,
                    "job_type": job_type,
                    "status": "QUEUED",
                    "user_id": parent["user_id"],
                    "video_id": parent["video_id"],
                    "input_data": json.dumps(parent.get("input_data") or {}),
                    "now": now,
                },
            )
            db.commit()
    finally:
        engine.dispose()
    logger.info("Created child job %s (type=%s, parent=%s)", new_id, job_type, parent_job_id)
    return new_id


def _update_job_output(
    job_id: str,
    output_data: dict,
    *,
    status: Optional[str] = None,
    error: Optional[str] = None,
):
    from sqlalchemy import text as sa_text
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            updates = {"output_data": json.dumps(output_data), "updated_at": now}
            if status:
                updates["status"] = status
            if error:
                updates["error_message"] = error

            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            params = {"id": job_id, **updates}
            db.execute(
                sa_text(f"UPDATE jobs SET {set_clause} WHERE id = :id"),
                params,
            )
            db.commit()
    finally:
        engine.dispose()


def _is_cancelled(job_id: str) -> bool:
    job = _load_job(job_id)
    if job is None:
        return True
    return job.get("status") == "CANCELLED"


# ─── RabbitMQ consumer ────────────────────────────────────────────────────

def _process_message(channel, method, properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON message — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[TTS] Processing job %s", job_id)

    try:
        result = _process_tts_job(job_id)
        _publish_result(channel, result, status="COMPLETED")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("[TTS] Completed job %s", job_id)
    except Exception as exc:
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _publish_result(
            channel,
            {"job_id": job_id, "error": str(exc)},
            status="FAILED",
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def _process_tts_job(job_id: str) -> dict:
    nmt_job = _load_job(job_id)
    if nmt_job is None:
        raise ValueError(f"NMT job {job_id} not found")

    nmt_output = nmt_job.get("output_data", {})
    if isinstance(nmt_output, str):
        nmt_output = json.loads(nmt_output)
    segments = nmt_output.get("segments", [])
    if not segments:
        logger.warning("[TTS] No segments to synthesize | job=%s", job_id)
        return {"status": "completed", "segments": []}

    input_data = nmt_job.get("input_data", {})
    if isinstance(input_data, str):
        input_data = json.loads(input_data)

    if _is_cancelled(job_id):
        logger.warning("[TTS] Job %s cancelled before processing", job_id)
        return {"status": "cancelled", "segments": []}

    # Create TTS child job
    tts_job_id = _create_child_job(job_id, "TTS_SYNTHESIZE")
    _update_job_output(tts_job_id, {"status": "processing"})

    video_id = nmt_job.get("video_id")

    result_segments = []
    for idx, seg in enumerate(segments):
        if _is_cancelled(job_id):
            logger.warning("[TTS] Job %s cancelled during segment %d", job_id, idx)
            break

        translated_text = ""
        if isinstance(seg, dict):
            translated_text = seg.get("translated_text", "").strip()
        elif isinstance(seg, str):
            translated_text = seg.strip()

        if not translated_text:
            logger.debug("[TTS] Empty text for segment %d — skipping", idx)
            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start") if isinstance(seg, dict) else None,
                "end": seg.get("end") if isinstance(seg, dict) else None,
                "original_text": seg.get("original_text", "") if isinstance(seg, dict) else "",
                "translated_text": translated_text,
                "tts_key": None,
                "audio_url": None,
            })
            continue

        try:
            tts_key = f"tts/{tts_job_id}/segment_{idx}.wav"
            audio_list = OmniVoiceManager.synthesize(text=translated_text)
            if not audio_list:
                raise RuntimeError("OmniVoice returned no audio")

            audio = audio_list[0]
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            wav_bytes = buf.getvalue()
            audio_url = upload_audio(wav_bytes, tts_key)

            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start") if isinstance(seg, dict) else None,
                "end": seg.get("end") if isinstance(seg, dict) else None,
                "original_text": seg.get("original_text", "") if isinstance(seg, dict) else "",
                "translated_text": translated_text,
                "tts_key": tts_key,
                "audio_url": audio_url,
            })
        except Exception as exc:
            logger.exception("[TTS] Segment %d synthesis failed", idx)
            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start") if isinstance(seg, dict) else None,
                "end": seg.get("end") if isinstance(seg, dict) else None,
                "original_text": seg.get("original_text", "") if isinstance(seg, dict) else "",
                "translated_text": translated_text,
                "tts_key": None,
                "audio_url": None,
                "tts_error": str(exc),
            })

    output = {
        "_result_job_id": tts_job_id,
        "status": "completed",
        "video_id": video_id,
        "segments": result_segments,
        "metadata": {
            "total_segments": len(result_segments),
            "failed": sum(1 for s in result_segments if s.get("tts_error")),
        },
    }

    _update_job_output(tts_job_id, output, status="COMPLETED")

    logger.info(
        "[TTS] Done | job=%s | segments=%d | failed=%d",
        tts_job_id,
        len(result_segments),
        output["metadata"]["failed"],
    )

    return output


def _publish_result(channel, output: dict, *, status: str):
    payload = {
        "job_id": output.get("_result_job_id") or output.get("job_id", ""),
        "job_type": "TTS_SYNTHESIZE",
        "status": status,
        "output_data": output,
        "error": output.get("error") if status == "FAILED" else None,
    }
    channel.basic_publish(
        exchange=_EXCHANGE,
        routing_key=_RESULT_KEY,
        body=json.dumps(payload, default=str),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    logger.info("Published result to %s | job_id=%s | status=%s", _RESULT_KEY, payload["job_id"], status)


def start_consumer():
    params = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(exchange=_EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=_DLX, exchange_type="direct", durable=True)

    channel.queue_declare(
        queue=_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": _DLX},
    )
    channel.queue_bind(queue=_QUEUE, exchange=_EXCHANGE, routing_key=_BINDING_KEY)

    channel.queue_declare(queue="orchestrator.dlq", durable=True)
    channel.queue_bind(queue="orchestrator.dlq", exchange=_DLX, routing_key=_QUEUE)

    channel.basic_qos(prefetch_count=_PREFETCH)
    channel.basic_consume(queue=_QUEUE, on_message_callback=_process_message, auto_ack=False)

    logger.info("[TTS] RabbitMQ consumer started | queue=%s binding=%s", _QUEUE, _BINDING_KEY)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("[TTS] Consumer interrupted — shutting down")
        channel.stop_consuming()
    finally:
        connection.close()
