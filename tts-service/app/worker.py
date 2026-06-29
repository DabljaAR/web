"""RabbitMQ consumer that processes TTS synthesis jobs.

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
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pika
from sqlalchemy import text

from app.audio_combine import combine_segment_wavs
from app.config import settings
from app.model import _tts
from app.storage import upload_wav
from dablja_worker import (
    check_cancelled,
    classify_failure,
    consume_loop,
    is_completed,
    make_engine,
    mark_completed,
    mark_failed,
    mark_processing,
    publish_result,
)

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
TTS_QUEUE = "stage.tts"
BINDING_KEY = "job.start.tts"
RESULT_ROUTING_KEY = "job.results.tts"
JOB_TYPE = "TTS_SYNTHESIZE"

_ENGINE, _SessionLocal = make_engine(settings.DATABASE_URL)


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
    """Poll DB periodically; set cancelled_flag when job status is CANCELLED (D8)."""
    while not stop_event.is_set():
        if stop_event.wait(interval_s):
            break
        try:
            with _SessionLocal() as db:
                if check_cancelled(db, job_id):
                    cancelled_flag[0] = True
                    logger.info("[TTS] job=%s cancelled mid-synthesis — watcher flagged", job_id)
                    return
        except Exception as exc:
            logger.warning("[TTS] cancel watcher DB error for job %s: %s", job_id, exc)


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
            "SELECT segments, output_type, source_lang, target_lang"
            " FROM video_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    ).fetchone()
    if not row:
        return None
    return {
        "segments": row[0] or [],
        "output_type": row[1] or "fullDubbing",
        "source_lang": row[2],
        "target_lang": row[3],
    }


def _update_video_task_tts(
    db,
    task_id: str,
    segments: list,
    combined_audio_key: str,
    output_type: str,
) -> None:
    terminal = output_type == "translationAndTTS"
    status = "COMPLETED" if terminal else "PROCESSING"
    progress = 100.0 if terminal else 75.0
    db.execute(
        text("""
            UPDATE video_tasks
               SET segments           = CAST(:segs AS jsonb),
                   combined_audio_key = :combined_key,
                   status             = CAST(:status AS taskstatus),
                   progress           = :progress,
                   updated_at         = :now,
                   completed_at       = CASE WHEN :terminal THEN :now ELSE completed_at END
             WHERE id = :tid
        """),
        {
            "segs": json.dumps(segments),
            "combined_key": combined_audio_key,
            "status": status,
            "progress": progress,
            "terminal": terminal,
            "now": _utcnow(),
            "tid": task_id,
        },
    )
    db.commit()


def process_tts_job(job_id: str, cancelled_flag: list) -> dict:
    """Load translated segments, synthesize TTS, combine, upload, write results."""
    with _SessionLocal() as db:
        job = _load_job(db, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if is_completed(db, job_id):
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
        mark_processing(db, job_id)

    total = len(translated_segments)
    logger.info(
        "[TTS] job=%s task=%s segments=%d output_type=%s",
        job_id,
        task_id,
        total,
        output_type,
    )

    tts_segments: list = []
    local_wav_paths: list[Path] = []
    failed_count = 0
    session_root = Path(settings.DUBBING_TEMP_DIR)
    session_root.mkdir(parents=True, exist_ok=True)
    session_dir = Path(tempfile.mkdtemp(prefix=f"tts_{job_id}_", dir=str(session_root)))

    try:
        for idx, seg in enumerate(translated_segments):
            if cancelled_flag[0]:
                logger.info("[TTS] job=%s cancelled at segment %d/%d", job_id, idx, total)
                raise RuntimeError(f"Job {job_id} cancelled during TTS synthesis")

            seg = dict(seg)
            translated_text = seg.get("translated_text", "")
            if not translated_text.strip():
                tts_segments.append(seg)
                continue

            minio_key = f"tts/{video_id}/segment_{idx}.wav"
            logger.info(
                "[TTS] segment %d/%d | job=%s | chars=%d",
                idx + 1,
                total,
                job_id,
                len(translated_text),
            )

            try:
                audio_bytes = _tts.synthesize(text=translated_text)
                upload_wav(audio_bytes, minio_key)

                local_path = session_dir / f"segment_{idx}.wav"
                local_path.write_bytes(audio_bytes)

                seg["tts_key"] = minio_key
                seg["tts_audio_key"] = minio_key
                tts_segments.append(seg)
                local_wav_paths.append(local_path)
                logger.info(
                    "[TTS] segment %d/%d done | job=%s | bytes=%d",
                    idx + 1,
                    total,
                    job_id,
                    len(audio_bytes),
                )
            except Exception as exc:
                logger.exception(
                    "[TTS] segment %d/%d failed | job=%s: %s",
                    idx + 1,
                    total,
                    job_id,
                    exc,
                )
                seg["tts_error"] = str(exc)
                tts_segments.append(seg)
                failed_count += 1

        synthesised_count = len(local_wav_paths)
        all_failed = synthesised_count == 0 and total > 0

        combined_key = f"tts/{video_id}/combined_{job_id}.wav"
        if synthesised_count > 0:
            ok_segments = [s for s in tts_segments if s.get("tts_audio_key")]
            combined_bytes = combine_segment_wavs(ok_segments, local_wav_paths, session_dir)
            upload_wav(combined_bytes, combined_key)
            logger.info("[TTS] combined audio uploaded: %s (%d bytes)", combined_key, len(combined_bytes))
        else:
            combined_key = ""

        summary = {
            "segment_count": total,
            "tts_segments": synthesised_count,
            "tts_failed": failed_count,
            "output_type": output_type,
            "combined_audio_key": combined_key,
        }

        with _SessionLocal() as db:
            if all_failed:
                mark_failed(db, job_id, f"TTS failed for all {total} segments")
            else:
                _update_video_task_tts(db, task_id, tts_segments, combined_key, output_type)
                mark_completed(db, job_id, summary, progress=75.0)

        logger.info(
            "[TTS] job=%s done | segments=%d | failed=%d | terminal=%s",
            job_id,
            total,
            failed_count,
            output_type == "translationAndTTS",
        )
        return summary
    finally:
        import shutil

        shutil.rmtree(session_dir, ignore_errors=True)


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
        with _SessionLocal() as db:
            cancelled = check_cancelled(db, job_id)
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
        summary = process_tts_job(job_id, cancelled_flag)
        publish_result(
            channel,
            RESULT_ROUTING_KEY,
            job_id,
            JOB_TYPE,
            "COMPLETED",
            output_data=summary,
        )
    except RuntimeError as exc:
        if "cancelled" in str(exc).lower():
            logger.info("[TTS] Job %s cancelled mid-synthesis — acking silently", job_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        publish_result(
            channel,
            RESULT_ROUTING_KEY,
            job_id,
            JOB_TYPE,
            "FAILED",
            error=str(exc),
        )
    except Exception as exc:
        logger.exception("[TTS] Job %s failed: %s", job_id, exc)
        _handle_failure(job_id, exc)
        publish_result(
            channel,
            RESULT_ROUTING_KEY,
            job_id,
            JOB_TYPE,
            "FAILED",
            error=str(exc),
        )
    finally:
        stop_event.set()

    channel.basic_ack(delivery_tag=method.delivery_tag)


def _handle_failure(job_id: str, exc: Exception):
    try:
        with _SessionLocal() as db:
            mark_failed(db, job_id, str(exc))
    except Exception as db_exc:
        logger.error("[TTS] Could not mark job %s failed: %s", job_id, db_exc)


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
