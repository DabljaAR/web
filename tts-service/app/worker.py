"""RabbitMQ consumer for TTS microservice.
Consumes ``job.start.tts`` and publishes results to ``job.results.tts``.
"""
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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


def _load_video_task_segments(video_id: str) -> list:
    from sqlalchemy import text as sa_text
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            row = db.execute(
                sa_text(
                    "SELECT segments FROM video_tasks"
                    " WHERE video_id = :vid ORDER BY created_at DESC LIMIT 1"
                ),
                {"vid": video_id},
            ).mappings().first()
            if not row:
                return []
            segments = row["segments"]
            if isinstance(segments, str):
                segments = json.loads(segments)
            return segments or []
    finally:
        engine.dispose()


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
    if job.get("status") == "CANCELLED":
        return True
    parent_id = job.get("parent_job_id")
    if parent_id:
        parent = _load_job(parent_id)
        if parent and parent.get("status") == "CANCELLED":
            return True
    return False


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
        _publish_result(channel, result, status="COMPLETED", job_id=job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("[TTS] Completed job %s", job_id)
    except Exception as exc:
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _publish_result(
            channel,
            {"job_id": job_id, "error": str(exc)},
            status="FAILED",
            job_id=job_id,
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def _process_tts_job(job_id: str) -> dict:
    job = _load_job(job_id)
    if job is None:
        raise ValueError(f"TTS job {job_id} not found")

    video_id = job.get("video_id")
    if not video_id:
        raise ValueError(f"Job {job_id} has no video_id")

    segments = _load_video_task_segments(video_id)
    if not segments:
        logger.warning("[TTS] No segments to synthesize | job=%s", job_id)
        return {"status": "completed", "segments": []}

    if _is_cancelled(job_id):
        logger.warning("[TTS] Job %s cancelled before processing", job_id)
        return {"status": "cancelled", "segments": []}

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
            tts_key = f"tts/{job_id}/segment_{idx}.wav"
            audio_list = OmniVoiceManager.synthesize(text=translated_text)
            if not audio_list:
                raise RuntimeError("OmniVoice returned no audio")

            audio = audio_list[0]
            buf = io.BytesIO()
            sf.write(buf, audio, settings.SAMPLE_RATE, format="WAV")
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
        "status": "completed",
        "video_id": video_id,
        "segments": result_segments,
        "metadata": {
            "total_segments": len(result_segments),
            "failed": sum(1 for s in result_segments if s.get("tts_error")),
        },
    }

    _update_job_output(job_id, output, status="COMPLETED")

    logger.info(
        "[TTS] Done | job=%s | segments=%d | failed=%d",
        job_id,
        len(result_segments),
        output["metadata"]["failed"],
    )

    return output


def _publish_result(channel, output: dict, *, status: str, job_id: str):
    payload = {
        "job_id": job_id,
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
    logger.info("Published result to %s | job_id=%s | status=%s", _RESULT_KEY, job_id, status)


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
