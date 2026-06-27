"""TTS Celery tasks (remaining Celery pipeline after STT/NMT migration).

STT and NMT are now handled by their respective microservices via RabbitMQ.
This file contains only the TTS tasks still running as Celery workers.

Pipeline (TTS portion):
  tts_synthesize_segment (×N, dispatched by nmt-service result handler)
  → tts_combine_results  (triggered by Redis counter when all segments done)
"""
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus, JobType

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _apply_processing_mode(
    *,
    segments: list[dict],
    words: Optional[list[dict]],
    transcript: str,
    duration: Optional[float],
    processing_mode: str,
) -> list[dict]:
    """Normalize STT segments according to the selected processing mode."""
    requested_mode = str(processing_mode or "").strip().lower()
    legacy_aliases = {
        "single_chunk": "single",
        "segmented": "stt_focused",
        "true": "single",
        "false": "stt_focused",
    }
    mode = legacy_aliases.get(requested_mode, requested_mode)
    if mode != requested_mode:
        logger.warning(
            "Legacy processing_mode=%r normalized to %r",
            processing_mode,
            mode,
        )

    if mode not in {"stt_focused", "single", "tts_focused"}:
        logger.warning(
            "Unknown processing_mode=%r. Falling back to 'single'.",
            processing_mode,
        )
        mode = "single"

    if mode == "tts_focused":
        rebuilt = _rebuild_segments_from_words(words or [])
        if rebuilt:
            return rebuilt
        return segments

    if mode != "single":
        return segments

    if not segments or not transcript.strip():
        return segments

    end = duration
    if end is None:
        end = segments[-1].get("end")

    try:
        end_value = round(float(end if end is not None else 0.0), 2)
    except (TypeError, ValueError):
        end_value = 0.0

    return [{"start": 0.0, "end": max(0.0, end_value), "text": transcript.strip()}]


def _rebuild_segments_from_words(
    words: list[dict],
    *,
    min_words: int = 10,
    max_words: int = 30,
) -> list[dict]:
    """Rebuild segments from word timestamps using punctuation-aware boundaries."""
    if not words:
        return []

    rebuilt_segments: list[dict] = []
    current_words: list[dict] = []

    for word_item in words:
        current_words.append(word_item)
        word_count = len(current_words)
        last_word = str(current_words[-1].get("word") or "")

        # Segment closes at '.' after min_words, or at max_words as a hard limit.
        if word_count >= min_words and re.search(r"[.]", last_word):
            rebuilt_segments.append(
                {
                    "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                    "start": float(current_words[0].get("start") or 0.0),
                    "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
                }
            )
            current_words = []
        elif word_count >= max_words:
            rebuilt_segments.append(
                {
                    "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                    "start": float(current_words[0].get("start") or 0.0),
                    "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
                }
            )
            current_words = []

    if current_words:
        rebuilt_segments.append(
            {
                "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                "start": float(current_words[0].get("start") or 0.0),
                "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
            }
        )

    return rebuilt_segments


# ===========================================================================
# Per-segment TTS worker  (STT is handled by the stt-service microservice)
# ===========================================================================

@celery_app.task(
    bind=True,
    name="app.jobs.tasks.pipeline.tts_synthesize_segment",
    max_retries=2,
    default_retry_delay=30,
    queue="ai_tts",
)
def tts_synthesize_segment(
    self,
    segment_id: int,
    job_id: str,
    text: str,
    start: float,
    end: float,
    minio_segment_key: str,
    ref_clip_minio_key: Optional[str],
    # Counter-based combine params (set when dispatched from the nmt-service)
    tts_job_id: Optional[str] = None,
    total_segments: Optional[int] = None,
    task_id: Optional[str] = None,
    tts_metadata: Optional[dict] = None,
    output_type: str = "fullDubbing",
    video_id: Optional[str] = None,
    enqueued_at: Optional[float] = None,
) -> dict:
    """
    Synthesize one translated segment using the configured voice.

    Uses a Redis counter to detect when all segments are done and triggers
    tts_combine_results automatically — no Celery chord needed.

    NOTE: Requires the Celery result backend to be Redis (celery_app.backend.client).
    """
    import asyncio
    import json
    import shutil
    import tempfile
    from app.jobs.celery_app import synthesize_tts

    task_started_at = time.time()
    if enqueued_at:
        logger.info(
            "[TTS][TIMING] segment_queue_wait_ms=%.1f | tts_job=%s | segment_id=%s",
            (task_started_at - enqueued_at) * 1000.0,
            tts_job_id or job_id,
            segment_id,
        )

    result: dict = {
        "segment_id": segment_id, "start": start, "end": end,
        "tts_key": None, "audio_url": None,
        "translated_text": text or "",
    }

    logger.info(
        "[TTS] segment start | tts_job=%s segment_id=%s total=%s text_chars=%d task_id=%s",
        tts_job_id or job_id,
        segment_id,
        total_segments,
        len(text or ""),
        task_id,
    )

    if tts_job_id:
        BaseJobTask._patch_job(tts_job_id, JobStatus.PROCESSING, progress=60.0)
    if task_id:
        from app.tasks.models import TaskStatus
        BaseJobTask._patch_task(task_id, TaskStatus.PROCESSING, progress=60.0)

    if text.strip():
        ref_local = None
        _tmp_dir = tempfile.mkdtemp()
        try:
            ref_download_ms = 0.0
            if ref_clip_minio_key:
                from app.media.storage import get_storage_service
                _ref_path = os.path.join(_tmp_dir, "ref_clip.wav")
                _loop = asyncio.new_event_loop()
                ref_download_started_at = time.time()
                try:
                    ok = _loop.run_until_complete(
                        get_storage_service().download(ref_clip_minio_key, _ref_path)
                    )
                finally:
                    _loop.close()
                ref_download_ms = (time.time() - ref_download_started_at) * 1000.0
                if ok and os.path.exists(_ref_path):
                    ref_local = _ref_path

            if ref_clip_minio_key:
                logger.info(
                    "[TTS][TIMING] ref_download_ms=%.1f | tts_job=%s | segment_id=%s",
                    ref_download_ms,
                    tts_job_id or job_id,
                    segment_id,
                )

            if not ref_local:
                from app.config import settings
                ref_local = settings.get_silma_reference_audio() or None

            synth_started_at = time.time()
            tts_result = synthesize_tts.run(
                text=text.strip(),
                ref_audio_path=ref_local,
                job_id=f"{job_id}_seg_{segment_id}",
                upload_to_minio=True,
                minio_key=minio_segment_key,
            )
            logger.info(
                "[TTS][TIMING] synth_and_upload_ms=%.1f | tts_job=%s | segment_id=%s",
                (time.time() - synth_started_at) * 1000.0,
                tts_job_id or job_id,
                segment_id,
            )
            result["tts_key"] = tts_result.get("minio_key")
            result["audio_url"] = tts_result.get("audio_url")
            logger.debug("[TTS] segment %d done | job=%s", segment_id, job_id)

            if tts_job_id:
                BaseJobTask._patch_job(tts_job_id, JobStatus.PROCESSING, progress=85.0)
            if task_id:
                from app.tasks.models import TaskStatus
                BaseJobTask._patch_task(task_id, TaskStatus.PROCESSING, progress=85.0)

        except Exception as exc:
            logger.exception("[TTS] segment %d failed | job=%s: %s", segment_id, job_id, exc)
            result["tts_error"] = str(exc)
            if isinstance(exc, AttributeError) and "do_tashkeel" in str(exc):
                result["tts_error_code"] = "tts_tashkeel_init_mismatch"
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

    logger.info(
        "[TTS][TIMING] total_segment_task_ms=%.1f | tts_job=%s | segment_id=%s",
        (time.time() - task_started_at) * 1000.0,
        tts_job_id or job_id,
        segment_id,
    )

    # ── Redis counter: detect when all segments are done ─────────────────────
    # celery_app.backend.client is a Redis client — requires Redis result backend.
    if tts_job_id and total_segments:
        try:
            r = celery_app.backend.client
            counter_key = f"tts:done:{tts_job_id}"
            result_key = f"tts:result:{tts_job_id}:{segment_id}"

            r.set(result_key, json.dumps(result), ex=7200)
            done = r.incr(counter_key)
            r.expire(counter_key, 7200)

            logger.debug(
                "[TTS] counter %s → %d/%d done | job=%s",
                counter_key, done, total_segments, tts_job_id,
            )

            if done >= total_segments:
                # Last segment — collect all results and trigger combine
                all_results = []
                for i in range(total_segments):
                    raw = r.get(f"tts:result:{tts_job_id}:{i}")
                    all_results.append(
                        json.loads(raw) if raw else
                        {"segment_id": i, "start": None, "end": None,
                         "tts_key": None, "audio_url": None,
                         "tts_error": "result missing"}
                    )
                r.delete(counter_key)
                for i in range(total_segments):
                    r.delete(f"tts:result:{tts_job_id}:{i}")

                tts_combine_results.apply_async(
                    args=[all_results],
                    kwargs={
                        "job_id": tts_job_id,
                        "task_id": task_id,
                        "video_id": video_id or job_id,
                        "ref_clip_minio_key": ref_clip_minio_key,
                        "metadata": tts_metadata or {},
                        "output_type": output_type,
                    },
                    queue="ai_tts",
                )
                logger.info(
                    "[TTS] all %d segments done → tts_combine dispatched | tts_job=%s",
                    total_segments, tts_job_id,
                )
        except Exception as exc:
            logger.error("[TTS] Redis counter error | tts_job=%s: %s", tts_job_id, exc)

    return result


# ===========================================================================
# Combine all TTS segments into final audio
# ===========================================================================

@celery_app.task(
    name="app.jobs.tasks.pipeline.tts_combine_results",
    max_retries=2,
    default_retry_delay=60,
    queue="ai_tts",
    soft_time_limit=300,
    time_limit=360,
)
def tts_combine_results(
    segment_results: list,
    *,
    job_id: str,
    task_id: Optional[str],
    video_id,
    ref_clip_minio_key: Optional[str],
    metadata: dict,
    output_type: str,
) -> dict:
    """
    Sort segment results, run timing-aware merge, optionally mux with original
    video audio replacement, then write combined output to DB.
    """
    import asyncio

    from app.dubbing.schemas import SegmentTimingInfo
    from app.dubbing.service import DubbingMergeService
    from app.media.models import MediaType, Video as MediaVideo
    from app.media.storage import get_storage_service

    sorted_results = sorted(segment_results, key=lambda r: r["segment_id"])

    # Load text already written by NMT and STT so we never lose it
    _existing_segs: dict[float, dict] = {}
    _stt_map: dict[float, str] = {}
    if task_id:
        try:
            _eng, _SL = BaseJobTask._make_db()
            try:
                with _SL() as _db:
                    from app.tasks.models import VideoTask as _VT
                    _vt = _db.get(_VT, task_id)
                    for _s in (_vt.segments or []):
                        _existing_segs[round(float(_s.get("start", 0)), 2)] = _s
                    for _s in (_vt.stt_segments or []):
                        _stt_map[round(float(_s.get("start", 0)), 2)] = _s.get("text", "")
            finally:
                _eng.dispose()
        except Exception:
            pass

    result_segments = []
    for r in sorted_results:
        key = round(float(r["start"]), 2)
        existing = _existing_segs.get(key, {})
        orig = r.get("original_text") or existing.get("original_text") or _stt_map.get(key, "")
        tran = r.get("translated_text") or existing.get("translated_text") or ""
        entry = {
            "start": r["start"],
            "end": r["end"],
            "original_text": orig,
            "translated_text": tran,
            "tts_key": r.get("tts_key"),
            "audio_url": r.get("audio_url"),
            **({"tts_error": r["tts_error"]} if r.get("tts_error") else {}),
            **({"tts_error_code": r["tts_error_code"]} if r.get("tts_error_code") else {}),
        }
        if r.get("tts_error"):
            entry["tts_error"] = r["tts_error"]
        result_segments.append(entry)

    failed = sum(1 for r in sorted_results if r.get("tts_error"))

    combined_minio_key: Optional[str] = None
    combined_audio_url: Optional[str] = None
    dubbed_video_key: Optional[str] = None
    dubbed_video_url: Optional[str] = None
    media_type_value = "audio"
    merge_error_message: Optional[str] = None

    segments_with_audio = [r for r in sorted_results if r.get("tts_key") and not r.get("tts_error")]

    if segments_with_audio:
        try:
            original_media_key: Optional[str] = None

            engine_v, SessionLocal_v = BaseJobTask._make_db()
            try:
                with SessionLocal_v() as db:
                    video_row = db.get(MediaVideo, video_id)
                    if video_row is not None:
                        media_type_value = (
                            video_row.media_type.value.lower()
                            if isinstance(video_row.media_type, MediaType)
                            else str(video_row.media_type).lower()
                        )
                        if media_type_value == "video":
                            original_media_key = video_row.file_path
                        else:
                            original_media_key = video_row.audio_path or video_row.file_path
            finally:
                engine_v.dispose()

            segment_infos: list[SegmentTimingInfo] = []
            for idx, row in enumerate(sorted_results):
                if not row.get("tts_key") or row.get("tts_error"):
                    continue

                start_val = float(row.get("start") or 0.0)
                end_raw = float(row.get("end") or start_val)
                end_val = end_raw if end_raw > start_val else start_val + 0.001
                segment_infos.append(
                    SegmentTimingInfo(
                        segment_id=int(row.get("segment_id", idx)),
                        start=start_val,
                        end=end_val,
                        duration=max(end_val - start_val, 0.001),
                        translated_text=str(row.get("translated_text") or ""),
                        tts_audio_key=row.get("tts_key"),
                    )
                )

            if not segment_infos:
                logger.error("[TTS] no usable segment infos for merge | job=%s", job_id)
            else:
                merge_service = DubbingMergeService()
                preferred_audio_key = f"tts/{job_id}/combined_{job_id}.wav"

                merge_response = asyncio.run(
                    merge_service.merge_segments(
                        video_id=str(video_id),
                        segments=segment_infos,
                        job_id=job_id,
                        media_type=media_type_value,
                        output_key_prefix=f"dubbed/{video_id}",
                        original_media_key=original_media_key,
                        combined_audio_key=preferred_audio_key,
                    )
                )

                merged_meta = merge_response.metadata or {}
                combined_minio_key = merged_meta.get("combined_audio_key")
                combined_audio_url = merged_meta.get("combined_audio_url")

                if media_type_value == "video":
                    dubbed_video_key = merge_response.output_key
                    dubbed_video_url = merge_response.output_url

                engine_u, SessionLocal_u = BaseJobTask._make_db()
                try:
                    with SessionLocal_u() as db:
                        up_video = db.get(MediaVideo, video_id)
                        if up_video is not None:
                            if dubbed_video_key:
                                up_video.dubbed_video_path = dubbed_video_key
                            existing_meta = (
                                dict(up_video.dubbing_metadata)
                                if up_video.dubbing_metadata
                                else {}
                            )
                            up_video.dubbing_metadata = {
                                **existing_meta,
                                "tts_job_id": job_id,
                                "media_type": media_type_value,
                                "combined_audio_key": combined_minio_key,
                                "combined_audio_url": combined_audio_url,
                                "dubbed_video_key": dubbed_video_key,
                                "dubbed_video_url": dubbed_video_url,
                                "updated_at": _utcnow().isoformat(),
                            }
                            db.commit()
                finally:
                    engine_u.dispose()
        except Exception as _exc:
            merge_error_message = str(_exc)
            logger.error("[TTS] merge step failed | job=%s: %s", job_id, _exc, exc_info=True)

    output = {
        "job_id": job_id,
        "video_id": video_id,
        "segments": result_segments,
        "combined_audio_key": combined_minio_key,
        "combined_audio_url": combined_audio_url,
        "dubbed_video_key": dubbed_video_key,
        "dubbed_video_url": dubbed_video_url,
        "metadata": {
            **metadata,
            "media_type": media_type_value if segments_with_audio else None,
            "tts_segments": len(result_segments),
            "tts_failed": failed,
            **({"merge_error": merge_error_message} if merge_error_message else {}),
        },
    }

    # ── Clean up shared ref clip ─────────────────────────────────────────────
    if ref_clip_minio_key:
        try:
            asyncio.run(get_storage_service().delete(ref_clip_minio_key))
        except Exception as _exc:
            logger.warning("[TTS] could not delete ref clip %s: %s", ref_clip_minio_key, _exc)

    # ── Write to Job row ─────────────────────────────────────────────────────
    error_message: Optional[str] = None
    if segments_with_audio and not combined_minio_key:
        error_message = merge_error_message or "TTS merge failed: no combined output was generated."
    elif failed and not combined_minio_key:
        error_message = f"TTS failed for {failed}/{len(result_segments)} segments"

    if error_message:
        BaseJobTask._patch_job(
            job_id, JobStatus.FAILED,
            output_data=output, error_message=error_message, completed_at=_utcnow(),
        )
    else:
        BaseJobTask._patch_job(
            job_id, JobStatus.COMPLETED,
            output_data=output, progress=100.0, completed_at=_utcnow(),
        )

    # ── Update VideoTask ─────────────────────────────────────────────────────
    if task_id:
        from app.tasks.models import TaskStatus
        task_status = TaskStatus.FAILED if error_message else TaskStatus.COMPLETED
        logger.info("[TTS] patching VideoTask to %s | task_id=%s tts_job=%s", task_status.value, task_id, job_id)
        patch_kwargs = {
            "segments": result_segments,
            "combined_audio_key": combined_minio_key,
            "combined_audio_url": combined_audio_url,
            "progress": 100.0,
            "completed_at": _utcnow(),
        }
        if error_message:
            patch_kwargs["error_message"] = error_message
        BaseJobTask._patch_task(task_id, task_status, **patch_kwargs)

    # ── Publish TTS result to RabbitMQ for orchestrator ────────────────────────
    try:
        from app.shared.rabbitmq import publish_tts_result
        if error_message:
            publish_tts_result(job_id, "FAILED", output, error=error_message)
        else:
            publish_tts_result(job_id, "COMPLETED", output)
    except Exception as _pub_exc:
        logger.warning("[TTS] Could not publish TTS result to RabbitMQ: %s", _pub_exc)

    logger.info(
        "[TTS] combined | job=%s | segments=%d | failed=%d | merged=%s",
        job_id, len(result_segments), failed, bool(combined_minio_key),
    )
    return output