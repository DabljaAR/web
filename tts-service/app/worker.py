"""RabbitMQ consumer for TTS microservice (OmniVoice).

Consumes ``job.start.tts`` and publishes results to ``job.results.tts``.
Uses the shared dablja_worker library for reconnect, heartbeats, and reliable publish.
"""
import io
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import soundfile as sf
from sqlalchemy import text

from app.config import settings
from app.model import OmniVoiceManager
from app.storage import upload_audio
from dablja_worker import (
    check_cancelled,
    classify_failure,
    consume_loop,
    finish_job_message,
    make_engine,
)
from dablja_worker.job_state import mark_completed, mark_failed, mark_processing

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
TTS_QUEUE = "stage.tts"
BINDING_KEY = "job.start.tts"
RESULT_ROUTING_KEY = "job.results.tts"
JOB_TYPE = "TTS_SYNTHESIZE"

_ENGINE, _SessionLocal = make_engine(settings.DATABASE_URL)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_job(db, job_id: str) -> Optional[Dict[str, Any]]:
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


def _load_video_task_segments(db, video_id: str) -> list:
    row = db.execute(
        text(
            "SELECT segments FROM video_tasks"
            " WHERE video_id = :vid ORDER BY created_at DESC LIMIT 1"
        ),
        {"vid": video_id},
    ).fetchone()
    if not row:
        return []
    segments = row[0]
    if isinstance(segments, str):
        segments = json.loads(segments)
    return segments or []


def _is_cancelled(db, job_id: str) -> bool:
    """D8: cooperative cancel check for job or parent pipeline."""
    if check_cancelled(db, job_id):
        return True
    row = db.execute(
        text("SELECT parent_job_id FROM jobs WHERE id = :jid"),
        {"jid": job_id},
    ).fetchone()
    if row and row[0]:
        return check_cancelled(db, row[0])
    return False


def _watch_cancel(
    job_id: str,
    cancelled_flag: list,
    interval_s: float,
    stop_event: threading.Event,
) -> None:
    """Poll DB periodically; set cancelled_flag when job or parent is CANCELLED."""
    while not stop_event.is_set():
        if stop_event.wait(interval_s):
            break
        try:
            with _SessionLocal() as db:
                if _is_cancelled(db, job_id):
                    cancelled_flag[0] = True
                    logger.info("[TTS] job=%s cancelled mid-synthesis — watcher flagged", job_id)
                    return
        except Exception as exc:
            logger.warning("[TTS] cancel watcher DB error for job %s: %s", job_id, exc)


def process_tts_job(job_id: str, cancelled_flag: list) -> dict:
    """Synthesize translated segments with OmniVoice and persist output."""
    with _SessionLocal() as db:
        job = _load_job(db, job_id)
        if not job:
            raise ValueError(f"TTS job {job_id} not found")

        if job["status"] == "COMPLETED":
            logger.info("[TTS] job=%s already COMPLETED — skipping re-run", job_id)
            return job["output_data"]

        video_id = job["video_id"] or job["input_data"].get("video_id")
        if not video_id:
            raise ValueError(f"Job {job_id} has no video_id")

        segments = _load_video_task_segments(db, video_id)
        if not segments:
            logger.warning("[TTS] No segments to synthesize | job=%s", job_id)
            output = {"status": "completed", "video_id": video_id, "segments": []}
            mark_completed(db, job_id, output)
            return output

        if _is_cancelled(db, job_id):
            logger.warning("[TTS] Job %s cancelled before processing", job_id)
            output = {"status": "cancelled", "video_id": video_id, "segments": []}
            mark_completed(db, job_id, output)
            return output

        mark_processing(db, job_id)

    result_segments = []
    for idx, seg in enumerate(segments):
        if cancelled_flag[0]:
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

    with _SessionLocal() as db:
        mark_completed(db, job_id, output)

    logger.info(
        "[TTS] Done | job=%s | segments=%d | failed=%d",
        job_id,
        len(result_segments),
        output["metadata"]["failed"],
    )
    return output


def _handle_failure(job_id: str, exc: Exception) -> None:
    try:
        with _SessionLocal() as db:
            mark_failed(db, job_id, str(exc))
    except Exception as db_exc:
        logger.error("[TTS] Could not mark job %s failed: %s", job_id, db_exc)


def on_message(channel, method, _properties, body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error("[TTS] Bad JSON in message: %s", exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = payload.get("job_id")
    if not job_id:
        logger.error("[TTS] Message missing job_id — discarding")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("[TTS] Received job %s", job_id)

    try:
        with _SessionLocal() as db:
            cancelled = _is_cancelled(db, job_id)
    except Exception as exc:
        logger.error("[TTS] DB unreachable checking cancel for job %s: %s", job_id, exc)
        if classify_failure(exc) == "transient":
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        else:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    if cancelled:
        logger.info("[TTS] Job %s is CANCELLED — skipping", job_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    cancelled_flag = [False]
    stop_event = threading.Event()
    watcher = threading.Thread(
        target=_watch_cancel,
        args=(job_id, cancelled_flag, 3.0, stop_event),
        name=f"tts-cancel-{job_id}",
        daemon=True,
    )
    watcher.start()

    try:
        finish_job_message(
            channel=channel,
            delivery_tag=method.delivery_tag,
            rabbitmq_url=settings.RABBITMQ_URL,
            result_routing_key=RESULT_ROUTING_KEY,
            job_id=job_id,
            job_type=JOB_TYPE,
            session_factory=_SessionLocal,
            process_fn=lambda: process_tts_job(job_id, cancelled_flag),
            mark_failure_fn=_handle_failure,
            service_name="TTS",
        )
    finally:
        stop_event.set()


def start_consumer():
    """Connect to RabbitMQ, declare topology, and start consuming (blocking)."""
    consume_loop(
        settings.RABBITMQ_URL,
        TTS_QUEUE,
        BINDING_KEY,
        EXCHANGE,
        on_message,
        service_name="TTS",
    )
