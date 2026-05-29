"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.

Pipeline flow:
  stt_transcribe  →  nmt_translate  →  tts_synthesize_segment (×N)  →  tts_combine_results
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
    from app.media_service.client import MediaServiceClient
    from app.stt.models import WhisperModelManager

    task_started_at = time.time()
    whisper = WhisperModelManager()
    media_client = MediaServiceClient()

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
    processing_mode = _input_data.get("processing_mode", "single")
    processing_mode_source = "job_input" if "processing_mode" in _input_data else "default"
    task_id = _input_data.get("task_id")

    # ── 2. Resolve the storage key ───────────────────────────────────────────
    async def _get_file_key() -> str:
        video = await media_client.get_video(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found.")
        return video.get("audio_path") or video.get("file_path")

    file_key: str = self._run_sync(_get_file_key())
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

        download_started_at = time.time()
        downloaded = self._run_sync(media_client.download_file(file_key, local_path))
        download_ms = (time.time() - download_started_at) * 1000.0
        if downloaded:
            logger.info("[STT] downloaded %s → %s", file_key, local_path)
        else:
            raise ValueError(f"Failed to download media key {file_key} via media-service")

        logger.info(
            "[STT][TIMING] input_download_ms=%.1f | job=%s | source=%s",
            download_ms,
            job_id,
            "remote" if downloaded else "missing",
        )

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe ────────────────────────────────────────────────────
        structured_segments = []
        word_level_timestamps: list[dict] = []
        transcript_parts = []

        try:
            start_time = time.time()
            segments_generator, info = whisper.model.transcribe(
                str(local_path),
                language=language,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 50},
                word_timestamps=True,
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

                seg_words = getattr(seg, "words", None) or []
                for w in seg_words:
                    word = str(getattr(w, "word", "") or "").strip()
                    start_w = getattr(w, "start", None)
                    end_w = getattr(w, "end", None)
                    if not word or start_w is None or end_w is None:
                        continue
                    word_level_timestamps.append(
                        {
                            "word": word,
                            "start": round(float(start_w), 2),
                            "end": round(float(end_w), 2),
                        }
                    )

                current_time = segment_dict["end"]
                progress = 25.0 + (65.0 * current_time / max(info.duration, 0.1))
                self.update_progress(job_id, min(progress, 90.0))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            structured_segments = _apply_processing_mode(
                segments=structured_segments,
                words=word_level_timestamps,
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

            logger.info(
                "[STT][TIMING] transcribe_ms=%.1f | job=%s | segments=%d",
                processing_time * 1000.0,
                job_id,
                len(structured_segments),
            )

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
            nmt_translate.apply_async(
                args=[nmt_job_id],
                kwargs={"enqueued_at": time.time()},
                queue="ai_nmt",
            )
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
        logger.info(
            "[STT][TIMING] total_task_ms=%.1f | job=%s",
            (time.time() - task_started_at) * 1000.0,
            job_id,
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
                from app.media_service.client import MediaServiceClient

                _ref_path = os.path.join(_tmp_dir, "ref_clip.wav")
                _loop = asyncio.new_event_loop()
                ref_download_started_at = time.time()
                try:
                    ok = _loop.run_until_complete(
                        MediaServiceClient().download_file(ref_clip_minio_key, Path(_ref_path))
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

            import httpx as _httpx
            import os as _os
            _media_svc_url = _os.getenv("MEDIA_SERVICE_URL", "http://media-service:8001")
            with _httpx.Client(timeout=10.0) as _c:
                _vr = _c.get(f"{_media_svc_url}/videos/{video_id}")
            if _vr.status_code == 200:
                _vdata = _vr.json()
                media_type_value = str(_vdata.get("media_type", "VIDEO")).lower()
                if media_type_value == "video":
                    original_media_key = _vdata.get("file_path")
                else:
                    original_media_key = _vdata.get("audio_path") or _vdata.get("file_path")

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

                import httpx as _httpx
                import os as _os
                _media_svc_url = _os.getenv(
                    "MEDIA_SERVICE_URL", "http://media-service:8001"
                )
                _patch_payload = {}
                if dubbed_video_key:
                    _patch_payload["dubbed_video_path"] = dubbed_video_key
                _patch_payload["dubbing_metadata"] = {
                    "tts_job_id": job_id,
                    "media_type": media_type_value,
                    "combined_audio_key": combined_minio_key,
                    "combined_audio_url": combined_audio_url,
                    "dubbed_video_key": dubbed_video_key,
                    "dubbed_video_url": dubbed_video_url,
                    "updated_at": _utcnow().isoformat(),
                }
                try:
                    with _httpx.Client(timeout=10.0) as _client:
                        _resp = _client.patch(
                            f"{_media_svc_url}/videos/{video_id}/paths",
                            json=_patch_payload,
                        )
                        _resp.raise_for_status()
                        logger.info(
                            "[TTS] media-service PATCH /videos/%s/paths → %s",
                            video_id, _resp.status_code,
                        )
                except Exception as _http_exc:
                    logger.error(
                        "[TTS] Failed to PATCH media-service for video %s: %s",
                        video_id, _http_exc,
                    )
                    raise
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
            import httpx as _httpx
            import os as _os
            _media_svc_url = _os.getenv("MEDIA_SERVICE_URL", "http://media-service:8001")
            with _httpx.Client(timeout=10.0) as _c:
                _c.delete(f"{_media_svc_url}/storage/{ref_clip_minio_key}")
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

    logger.info(
        "[TTS] combined | job=%s | segments=%d | failed=%d | merged=%s",
        job_id, len(result_segments), failed, bool(combined_minio_key),
    )
    return output