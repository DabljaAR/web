"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.

Pipeline flow:
  stt_transcribe  →  nmt_translate  →  tts_synthesize_segment (×N)  →  tts_combine_results
"""
import logging
import os
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
    transcript: str,
    duration: Optional[float],
    processing_mode: str,
) -> list[dict]:
    """Normalize STT segments according to the selected processing mode."""
    if processing_mode != "single_chunk":
        return segments

    if not segments or not transcript.strip():
        return segments

    end = duration
    if end is None:
        end = segments[-1].get("end")

    try:
        end_value = round(float(end), 2)
    except (TypeError, ValueError):
        end_value = 0.0

    return [{"start": 0.0, "end": max(0.0, end_value), "text": transcript.strip()}]


# ===========================================================================
# Speech-to-Text
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.stt_transcribe",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_stt",
)
def stt_transcribe(
    self,
    job_id: str,
    video_id: str,
    language: Optional[str] = None,
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Transcribe the audio track of *video_id*.

    Downloads the audio from storage, runs Whisper, stores the result in
    the Job row and VideoTask, then creates one NMT job and dispatches
    nmt_translate when the output_type requires translation.

    Returns:
        {
            "job_id":     str,
            "video_id":   str,
            "transcript": str,
            "segments":   list[dict],   # [{start, end, text}, ...]
            "metadata":   dict,
        }
    """
    from app.media.storage import get_storage_service
    from app.stt.models import WhisperModelManager

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING ───────────────────────────────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=_utcnow(),
    )

    # ── Read output_type and task_id from this job's input_data ─────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            from app.jobs.models import Job as _Job
            stt_job_row = db.get(_Job, job_id)
            _input_data = dict(stt_job_row.input_data) if stt_job_row and stt_job_row.input_data else {}
    finally:
        engine.dispose()
    output_type = _input_data.get("output_type", "fullDubbing")
    processing_mode = _input_data.get("processing_mode", "segmented")
    processing_mode_source = "job_input" if "processing_mode" in _input_data else "default"
    task_id = _input_data.get("task_id")

    # ── 2. Resolve the storage key ───────────────────────────────────────────
    def _get_file_key() -> str:
        from app.media.models import Video  # noqa: F401 — needed for SQLAlchemy mapper resolution
        _engine, _SessionLocal = self._make_db()
        try:
            with _SessionLocal() as db:
                video = db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found.")
                return video.audio_path or video.file_path
        finally:
            _engine.dispose()

    file_key: str = _get_file_key()
    logger.info(
        "[STT] job=%s video=%s file_key=%s output_type=%s processing_mode=%s source=%s",
        job_id,
        video_id,
        file_key,
        output_type,
        processing_mode,
        processing_mode_source,
    )

    self.update_progress(job_id, 10.0)

    # ── 3. Download from storage ─────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix = Path(file_key).suffix or ".mp3"
        local_path = Path(tmp_dir) / f"audio{suffix}"

        downloaded = self._run_sync(storage.download(file_key, str(local_path)))
        if downloaded:
            logger.info("[STT] downloaded %s → %s", file_key, local_path)
        else:
            # Fallback: local storage absolute path
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe ────────────────────────────────────────────────────
        structured_segments = []
        transcript_parts = []

        try:
            start_time = time.time()
            segments_generator, info = whisper.model.transcribe(
                str(local_path),
                language=language,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 50},
            )

            if info.duration > 3600:
                raise ValueError(f"Audio too long: {info.duration:.0f}s (max 3600s)")

            logger.info(
                "[STT] Starting transcription | duration=%.1fs | job=%s | mode=%s",
                info.duration,
                job_id,
                processing_mode,
            )

            for seg in segments_generator:
                segment_dict = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

                current_time = segment_dict["end"]
                progress = 25.0 + (65.0 * current_time / max(info.duration, 0.1))
                self.update_progress(job_id, min(progress, 90.0))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            structured_segments = _apply_processing_mode(
                segments=structured_segments,
                transcript=full_transcript,
                duration=info.duration,
                processing_mode=processing_mode,
            )

            metadata = {
                "language": info.language,
                "duration": round(info.duration, 2),
                "model_size": whisper.model_size,
                "device": whisper.device,
                "compute_type": whisper.compute_type,
                "processing_time": round(processing_time, 2),
                "segment_count": len(structured_segments),
                "processing_mode": processing_mode,
            }

        except Exception as exc:
            logger.error("[STT] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 90.0)

        output = {
            "job_id": job_id,
            "video_id": video_id,
            "transcript": full_transcript,
            "segments": structured_segments,
            "metadata": metadata,
        }

        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

        # ── 5. Write STT result to VideoTask ─────────────────────────────────
        if task_id:
            from app.tasks.models import TaskStatus
            captions_only = output_type == "captionsOnly"
            self._patch_task(
                task_id,
                TaskStatus.COMPLETED if captions_only else TaskStatus.PROCESSING,
                transcript=full_transcript,
                stt_segments=structured_segments,
                stt_metadata=metadata,
                progress=100.0 if captions_only else 10.0,
                started_at=_utcnow(),
                completed_at=_utcnow() if captions_only else None,
            )

        # ── 6. Conditionally dispatch NMT based on output_type ───────────────
        NMT_REQUIRED = {"captionsAndTranslation", "translationAndTTS", "fullDubbing"}
        if structured_segments and output_type in NMT_REQUIRED:
            from app.jobs.tasks.nmt import nmt_translate

            nmt_job_id = self._create_next_job(
                job_id,
                JobType.NMT_TRANSLATE,
                input_data={
                    "task_id": task_id,
                    "source_lang": language or "auto",
                    "target_lang": target_lang,
                    "output_type": output_type,
                },
            )
            nmt_translate.apply_async(args=[nmt_job_id], queue="ai_nmt")
            logger.info(
                "[STT] NMT job %s dispatched | job=%s | segments=%d | output_type=%s",
                nmt_job_id, job_id, len(structured_segments), output_type,
            )
        else:
            if structured_segments:
                logger.info("[STT] output_type=%s — skipping NMT/TTS | job=%s", output_type, job_id)
            else:
                logger.info("[STT] No segments to translate; pipeline ends here | job=%s", job_id)

        logger.info(
            "[STT] done | job=%s | duration=%.1fs | segments=%d | processing_mode=%s",
            job_id,
            metadata.get("duration", 0),
            metadata.get("segment_count", 0),
            processing_mode,
        )

        return output


# ===========================================================================
# Per-segment TTS worker
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
    # Counter-based combine params (set when dispatched from nmt_translate_segment)
    tts_job_id: Optional[str] = None,
    total_segments: Optional[int] = None,
    task_id: Optional[str] = None,
    tts_metadata: Optional[dict] = None,
    output_type: str = "fullDubbing",
    video_id: Optional[str] = None,
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
            if ref_clip_minio_key:
                from app.media.storage import get_storage_service
                _ref_path = os.path.join(_tmp_dir, "ref_clip.wav")
                _loop = asyncio.new_event_loop()
                try:
                    ok = _loop.run_until_complete(
                        get_storage_service().download(ref_clip_minio_key, _ref_path)
                    )
                finally:
                    _loop.close()
                if ok and os.path.exists(_ref_path):
                    ref_local = _ref_path

            if not ref_local:
                from app.config import settings
                ref_local = settings.get_silma_reference_audio() or None

            tts_result = synthesize_tts.run(
                text=text.strip(),
                ref_audio_path=ref_local,
                job_id=f"{job_id}_seg_{segment_id}",
                upload_to_minio=True,
                minio_key=minio_segment_key,
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
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

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

    result_segments = [
        {
            "start": r["start"],
            "end": r["end"],
            "tts_key": r.get("tts_key"),
            "audio_url": r.get("audio_url"),
            **({"tts_error": r["tts_error"]} if r.get("tts_error") else {}),
        }
        for r in sorted_results
    ]

    failed = sum(1 for r in sorted_results if r.get("tts_error"))

    combined_minio_key: Optional[str] = None
    combined_audio_url: Optional[str] = None
    dubbed_video_key: Optional[str] = None
    dubbed_video_url: Optional[str] = None

    segments_with_audio = [r for r in sorted_results if r.get("tts_key") and not r.get("tts_error")]

    if segments_with_audio:
        try:
            media_type_value = "audio"
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
        },
    }

    # ── Clean up shared ref clip ─────────────────────────────────────────────
    if ref_clip_minio_key:
        try:
            asyncio.run(get_storage_service().delete(ref_clip_minio_key))
        except Exception as _exc:
            logger.warning("[TTS] could not delete ref clip %s: %s", ref_clip_minio_key, _exc)

    # ── Write to Job row ─────────────────────────────────────────────────────
    if failed and not combined_minio_key:
        msg = f"TTS failed for {failed}/{len(result_segments)} segments"
        BaseJobTask._patch_job(
            job_id, JobStatus.FAILED,
            output_data=output, error_message=msg, completed_at=_utcnow(),
        )
    else:
        BaseJobTask._patch_job(
            job_id, JobStatus.COMPLETED,
            output_data=output, progress=100.0, completed_at=_utcnow(),
        )

    # ── Update VideoTask ─────────────────────────────────────────────────────
    if task_id:
        from app.tasks.models import TaskStatus
        logger.info("[TTS] patching VideoTask to COMPLETED | task_id=%s tts_job=%s", task_id, job_id)
        BaseJobTask._patch_task(
            task_id,
            TaskStatus.COMPLETED,
            segments=result_segments,
            combined_audio_key=combined_minio_key,
            combined_audio_url=combined_audio_url,
            progress=100.0,
            completed_at=_utcnow(),
        )

    logger.info(
        "[TTS] combined | job=%s | segments=%d | failed=%d | merged=%s",
        job_id, len(result_segments), failed, bool(combined_minio_key),
    )
    return output
