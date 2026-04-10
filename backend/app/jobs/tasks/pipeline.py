"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.

Pipeline flow (each stage is independent — reads input from DB, writes output to DB):
  stt_transcribe  →  nmt_translate  →  tts_pipeline
"""
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus, JobType

logger = logging.getLogger(__name__)


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

    Downloads the file from MinIO, runs Whisper, stores the result in the
    Job row, then creates one NMT job and dispatches nmt_translate.

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript":     str,
            "segments":       list[dict],   # [{start, end, text}, ...]
            "metadata":       dict,
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING ───────────────────────────────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── Read output_type from this job's input_data ──────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            from app.jobs.models import Job as _Job
            stt_job_row = db.get(_Job, job_id)
            _input_data = dict(stt_job_row.input_data) if stt_job_row and stt_job_row.input_data else {}
    finally:
        engine.dispose()
    output_type = _input_data.get("output_type", "fullDubbing")
    task_id     = _input_data.get("task_id")

    # ── 2. Resolve the MinIO key ─────────────────────────────────────────────
    async def _get_file_key() -> str:
        from app.core.db import AsyncSessionLocal
        from app.media.models import Video
        async with AsyncSessionLocal() as db:
            video = await db.get(Video, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found.")
            return video.audio_path or video.file_path

    file_key: str = self._run_sync(_get_file_key())
    logger.info("[STT] job=%s video=%s file_key=%s", job_id, video_id, file_key)

    self.update_progress(job_id, 10.0)

    # ── 3. Download from MinIO ───────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix     = Path(file_key).suffix or ".mp3"
        local_path = Path(tmp_dir) / f"audio{suffix}"

        if isinstance(storage, S3StorageService):
            async def _download():
                async with storage.session.client(
                    "s3",
                    endpoint_url=storage.endpoint_url,
                    aws_access_key_id=storage.access_key,
                    aws_secret_access_key=storage.secret_key,
                ) as s3:
                    await s3.download_file(
                        storage.bucket_name, file_key, str(local_path)
                    )

            self._run_sync(_download())
            logger.info("[STT] downloaded %s → %s", file_key, local_path)
        else:
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

            logger.info("[STT] Starting transcription | duration=%.1fs | job=%s", info.duration, job_id)

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

            metadata = {
                "language": info.language,
                "duration": round(info.duration, 2),
                "model_size": whisper.model_size,
                "device": whisper.device,
                "compute_type": whisper.compute_type,
                "processing_time": round(processing_time, 2),
                "segment_count": len(structured_segments),
            }

        except Exception as exc:
            logger.error("[STT] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 90.0)

        output = {
            "job_id":     job_id,
            "video_id":   video_id,
            "transcript": full_transcript,
            "segments":   structured_segments,
            "metadata":   metadata,
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
                stt_metadata=metadata,
                progress=100.0 if captions_only else 10.0,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow() if captions_only else None,
            )

        # ── 6. Conditionally dispatch NMT based on output_type ───────────────
        NMT_REQUIRED = {"captionsAndTranslation", "translationAndTTS", "fullDubbing"}
        if structured_segments and output_type in NMT_REQUIRED:
            from app.jobs.tasks.nmt import nmt_translate

            nmt_job_id = self._create_next_job(
                job_id,
                JobType.NMT_TRANSLATE,
                input_data={
                    "task_id":    task_id,
                    "source_lang": language or "auto",
                    "target_lang": target_lang,
                    "output_type": output_type,
                },
            )
            nmt_translate.apply_async(args=[nmt_job_id], queue="ai_nmt")
            logger.info("[STT] NMT job %s dispatched | job=%s | segments=%d | output_type=%s",
                        nmt_job_id, job_id, len(structured_segments), output_type)
        else:
            if structured_segments:
                logger.info("[STT] output_type=%s — skipping NMT/TTS | job=%s", output_type, job_id)
            else:
                logger.info("[STT] No segments to translate; pipeline ends here | job=%s", job_id)

        logger.info(
            "[STT] done | job=%s | duration=%.1fs | segments=%d",
            job_id, metadata.get("duration", 0), metadata.get("segment_count", 0),
        )

        return output


# ===========================================================================
# Text-to-Speech pipeline stage
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.tts_pipeline",
    max_retries=2,
    default_retry_delay=30,
    queue="ai_tts",
)
def tts_pipeline(self, job_id: str) -> dict:
    """
    TTS orchestrator — mirrors the NMT chord pattern.

    1. Extract a 15-second voice clip from the video and upload it to MinIO
       so every segment task can access the same reference voice.
    2. Fan out one tts_synthesize_segment task per translated segment.
    3. tts_combine_results (chord callback) collects results and writes the DB.
    """
    import asyncio
    import subprocess
    import tempfile
    from celery import chord, group
    from app.jobs.models import Job

    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 1. Load NMT output ───────────────────────────────────────────────────
    engine, SessionLocal = BaseJobTask._make_db()
    try:
        with SessionLocal() as db:
            tts_job = db.get(Job, job_id)
            if not tts_job:
                raise ValueError(f"TTS job {job_id} not found")
            parent = db.get(Job, tts_job.parent_job_id) if tts_job.parent_job_id else None
            if not parent or not parent.output_data:
                raise ValueError(f"TTS job {job_id} has no parent NMT output")
            nmt_output  = dict(parent.output_data)
            video_id    = tts_job.video_id
            tts_input   = dict(tts_job.input_data or {})
    finally:
        engine.dispose()

    task_id  = tts_input.get("task_id")
    segments: list = nmt_output.get("segments", [])
    metadata: dict = nmt_output.get("metadata", {})

    logger.info("[TTS] job=%s video=%s segments=%d", job_id, video_id, len(segments))

    # ── 2. Extract reference voice clip from the video, upload to MinIO ──────
    ref_clip_minio_key = f"tts/{video_id}/ref_clip_{job_id}.wav"

    try:
        engine2, SessionLocal2 = BaseJobTask._make_db()
        try:
            with SessionLocal2() as db:
                from app.media.models import Video as _Video
                _video_row = db.get(_Video, video_id)
                _audio_key = (_video_row.audio_path or _video_row.file_path) if _video_row else None
        finally:
            engine2.dispose()

        if not _audio_key:
            raise ValueError("No audio key found for video")

        from app.media.storage import get_storage_service

        with tempfile.TemporaryDirectory() as _tmp:
            _raw  = os.path.join(_tmp, "source_audio")
            _clip = os.path.join(_tmp, "ref_clip.wav")

            _loop = asyncio.new_event_loop()
            try:
                _loop.run_until_complete(get_storage_service().download(_audio_key, _raw))
            finally:
                _loop.close()

            subprocess.run(
                ["ffmpeg", "-y", "-i", _raw,
                 "-t", "15", "-ar", "24000", "-ac", "1", _clip],
                check=True, capture_output=True,
            )

            with open(_clip, "rb") as _f:
                clip_bytes = _f.read()

        _loop2 = asyncio.new_event_loop()
        try:
            _loop2.run_until_complete(
                get_storage_service().upload_bytes(clip_bytes, ref_clip_minio_key, "audio/wav")
            )
        finally:
            _loop2.close()

        logger.info("[TTS] ref clip uploaded | key=%s | job=%s", ref_clip_minio_key, job_id)

    except Exception as _exc:
        logger.warning("[TTS] could not extract video voice, using fallback | %s", _exc)
        ref_clip_minio_key = None  # segment tasks will use bundled default

    # ── 3. Fan out one task per segment ──────────────────────────────────────
    segment_tasks = [
        tts_synthesize_segment.s(
            idx,
            str(job_id),
            seg.get("translated_text") or seg.get("text") or "",
            seg.get("start"),
            seg.get("end"),
            f"tts/{job_id}/segment_{idx}.wav",
            ref_clip_minio_key,
        )
        for idx, seg in enumerate(segments)
    ]

    chord(group(segment_tasks))(
        tts_combine_results.s(
            job_id=job_id,
            task_id=task_id,
            video_id=video_id,
            ref_clip_minio_key=ref_clip_minio_key,
            metadata=metadata,
            output_type=tts_input.get("output_type", "fullDubbing"),
        )
    )

    logger.info("[TTS] chord dispatched | job=%s | tasks=%d", job_id, len(segment_tasks))
    return {"_skip_completion": True, "job_id": job_id, "segment_count": len(segment_tasks)}


# ---------------------------------------------------------------------------
# Per-segment TTS worker
# ---------------------------------------------------------------------------

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
    Synthesize one translated segment using the video's own voice.

    When tts_job_id is provided (dispatched from nmt_translate_segment),
    uses a Redis counter to detect when all segments are done and triggers
    tts_combine_results automatically — no chord needed.
    """
    import asyncio
    import json
    import shutil
    import tempfile
    from app.jobs.celery_app import synthesize_tts

    # ── Synthesize ───────────────────────────────────────────────────────────
    result: dict = {
        "segment_id": segment_id, "start": start, "end": end,
        "tts_key": None, "audio_url": None,
    }

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
            result["tts_key"]   = tts_result.get("minio_key")
            result["audio_url"] = tts_result.get("audio_url")
            logger.debug("[TTS] segment %d done | job=%s", segment_id, job_id)

        except Exception as exc:
            logger.exception("[TTS] segment %d failed | job=%s: %s", segment_id, job_id, exc)
            result["tts_error"] = str(exc)
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

    # ── Redis counter: detect when all segments are done ─────────────────────
    if tts_job_id and total_segments:
        try:
            r = celery_app.backend.client
            counter_key = f"tts:pending:{tts_job_id}"
            result_key  = f"tts:result:{tts_job_id}:{segment_id}"

            r.set(result_key, json.dumps(result), ex=7200)
            remaining = r.decr(counter_key)

            logger.debug("[TTS] counter %s → %d remaining | job=%s",
                         counter_key, remaining, tts_job_id)

            if remaining <= 0:
                # Last segment — collect all results and trigger combine
                all_results = []
                for i in range(total_segments):
                    raw = r.get(f"tts:result:{tts_job_id}:{i}")
                    all_results.append(json.loads(raw) if raw else
                                       {"segment_id": i, "start": None, "end": None,
                                        "tts_key": None, "audio_url": None,
                                        "tts_error": "result missing"})
                # Clean up Redis keys
                r.delete(counter_key)
                for i in range(total_segments):
                    r.delete(f"tts:result:{tts_job_id}:{i}")

                tts_combine_results.apply_async(
                    args=[all_results],
                    kwargs={
                        "job_id":              tts_job_id,
                        "task_id":             task_id,
                        "video_id":            video_id or job_id,
                        "ref_clip_minio_key":  ref_clip_minio_key,
                        "metadata":            tts_metadata or {},
                        "output_type":         output_type,
                    },
                    queue="ai_tts",
                )
                logger.info("[TTS] all %d segments done → tts_combine dispatched | tts_job=%s",
                            total_segments, tts_job_id)
        except Exception as exc:
            logger.error("[TTS] Redis counter error | tts_job=%s: %s", tts_job_id, exc)

    return result


# ---------------------------------------------------------------------------
# Chord callback — combines all segment results
# ---------------------------------------------------------------------------

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
    Chord callback: sort segment results, merge all segment WAVs into a single
    time-aligned audio file, upload it, then write combined output to DB.
    """
    import asyncio
    import shutil
    import subprocess

    from app.media.storage import get_storage_service

    sorted_results = sorted(segment_results, key=lambda r: r["segment_id"])

    result_segments = [
        {
            "start":     r["start"],
            "end":       r["end"],
            "tts_key":   r.get("tts_key"),
            "audio_url": r.get("audio_url"),
            **({"tts_error": r["tts_error"]} if r.get("tts_error") else {}),
        }
        for r in sorted_results
    ]

    failed = sum(1 for r in sorted_results if r.get("tts_error"))

    # ── Merge all segment WAVs into one time-aligned audio file ─────────────
    combined_minio_key: Optional[str] = None
    combined_audio_url: Optional[str] = None

    segments_with_audio = [r for r in sorted_results if r.get("tts_key") and not r.get("tts_error")]

    if segments_with_audio:
        _tmp = tempfile.mkdtemp()
        try:
            storage = get_storage_service()

            # ── Step 1: Download each TTS segment WAV ───────────────────────
            local_paths: list[tuple[float, float, str]] = []
            for r in segments_with_audio:
                local_f = os.path.join(_tmp, f"seg_{r['segment_id']}.wav")
                _loop = asyncio.new_event_loop()
                try:
                    _loop.run_until_complete(storage.download(r["tts_key"], local_f))
                finally:
                    _loop.close()
                if os.path.exists(local_f) and os.path.getsize(local_f) > 0:
                    local_paths.append((r["start"] or 0.0, r["end"] or 0.0, local_f))
                else:
                    logger.warning("[TTS] segment download empty | key=%s", r["tts_key"])

            if not local_paths:
                logger.error("[TTS] no segment files downloaded | job=%s", job_id)
            else:
                # ── Step 2: Concat all TTS segments into one track ───────────
                #
                # Write a concat list and use ffmpeg's concat demuxer — the
                # simplest and most reliable way to join N WAV files in order.
                concat_list = os.path.join(_tmp, "concat_list.txt")
                with open(concat_list, "w") as _cl:
                    for _, _, path in local_paths:
                        _cl.write(f"file '{path}'\n")

                tts_track = os.path.join(_tmp, "tts_track.wav")
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", concat_list,
                     "-ar", "24000", "-ac", "1", tts_track],
                    capture_output=True,
                )
                if proc.returncode != 0:
                    logger.error("[TTS] ffmpeg concat failed | job=%s\n%s",
                                 job_id, proc.stderr.decode())
                else:
                    logger.info("[TTS] concat done | job=%s | segments=%d",
                                job_id, len(local_paths))

                    # ── Step 3: Extract SFX track and mix with TTS ──────────
                    #
                    # Use Demucs to separate vocals from background (SFX/music).
                    # Only the no-vocals stem is mixed in so the original speaker
                    # voice does not bleed into the dubbed output.
                    # Falls back to TTS-only if Demucs is unavailable or fails.
                    combined_local = os.path.join(_tmp, "combined.wav")
                    sfx_track: Optional[str] = None

                    try:
                        engine_v, SL_v = BaseJobTask._make_db()
                        try:
                            with SL_v() as db:
                                from app.media.models import Video as _V
                                _vrow = db.get(_V, video_id)
                                _orig_key = (_vrow.audio_path or _vrow.file_path) if _vrow else None
                        finally:
                            engine_v.dispose()

                        if _orig_key:
                            orig_audio_local = os.path.join(_tmp, "orig_audio.wav")
                            _loop_bg = asyncio.new_event_loop()
                            try:
                                _loop_bg.run_until_complete(
                                    storage.download(_orig_key, orig_audio_local)
                                )
                            finally:
                                _loop_bg.close()

                            if os.path.exists(orig_audio_local) and os.path.getsize(orig_audio_local) > 0:
                                # ── Convert to WAV so Demucs can read it ────────
                                orig_wav = os.path.join(_tmp, "orig_audio_conv.wav")
                                subprocess.run(
                                    ["ffmpeg", "-y", "-i", orig_audio_local,
                                     "-ar", "44100", "-ac", "2", orig_wav],
                                    capture_output=True, check=True,
                                )

                                # ── Run Demucs vocal separation ──────────────────
                                demucs_out = os.path.join(_tmp, "demucs_out")
                                proc_demucs = subprocess.run(
                                    [
                                        "demucs",
                                        "--two-stems", "vocals",   # produces vocals + no_vocals
                                        "--out", demucs_out,
                                        "--name", "htdemucs",
                                        orig_wav,
                                    ],
                                    capture_output=True,
                                )

                                if proc_demucs.returncode == 0:
                                    # Demucs writes: <out>/<model>/<stem_name>/no_vocals.wav
                                    import glob as _glob
                                    no_vocals_candidates = _glob.glob(
                                        os.path.join(demucs_out, "**", "no_vocals.wav"),
                                        recursive=True,
                                    )
                                    if no_vocals_candidates:
                                        sfx_track = no_vocals_candidates[0]
                                        logger.info("[TTS] Demucs SFX track ready | job=%s | path=%s",
                                                    job_id, sfx_track)
                                    else:
                                        logger.warning("[TTS] Demucs ran but no_vocals.wav not found | job=%s", job_id)
                                else:
                                    logger.warning("[TTS] Demucs failed | job=%s\n%s",
                                                   job_id, proc_demucs.stderr.decode())
                    except FileNotFoundError:
                        logger.warning("[TTS] demucs not installed — mixing without SFX | job=%s", job_id)
                    except Exception as _bg_exc:
                        logger.warning("[TTS] SFX extraction failed: %s | job=%s", _bg_exc, job_id)

                    if sfx_track:
                        # Mix: TTS at full volume + SFX-only track at 80%
                        mix_fc = (
                            "[0:a]volume=1.0[tts];"
                            "[1:a]aresample=24000,volume=0.80[sfx];"
                            "[tts][sfx]amix=inputs=2:duration=first:normalize=0[out]"
                        )
                        proc2 = subprocess.run(
                            ["ffmpeg", "-y",
                             "-i", tts_track,
                             "-i", sfx_track,
                             "-filter_complex", mix_fc,
                             "-map", "[out]",
                             "-ar", "24000", "-ac", "1",
                             combined_local],
                            capture_output=True,
                        )
                        if proc2.returncode != 0:
                            logger.warning("[TTS] SFX mix failed, using TTS-only | job=%s\n%s",
                                           job_id, proc2.stderr.decode())
                            combined_local = tts_track
                        else:
                            logger.info("[TTS] SFX mixed | job=%s", job_id)
                    else:
                        combined_local = tts_track  # no SFX available

                    # ── Step 4: Upload ───────────────────────────────────────
                    combined_minio_key = f"tts/{job_id}/combined_{job_id}.wav"
                    with open(combined_local, "rb") as _f:
                        combined_bytes = _f.read()

                    _loop3 = asyncio.new_event_loop()
                    try:
                        _loop3.run_until_complete(
                            storage.upload_bytes(combined_bytes, combined_minio_key, "audio/wav")
                        )
                        combined_audio_url = _loop3.run_until_complete(
                            storage.get_url(combined_minio_key)
                        )
                    finally:
                        _loop3.close()

                    logger.info("[TTS] combined audio uploaded | key=%s | job=%s",
                                combined_minio_key, job_id)

        except Exception as _exc:
            logger.error("[TTS] merge step failed | job=%s: %s", job_id, _exc, exc_info=True)
        finally:
            shutil.rmtree(_tmp, ignore_errors=True)

    output = {
        "job_id":              job_id,
        "video_id":            video_id,
        "segments":            result_segments,
        "combined_audio_key":  combined_minio_key,
        "combined_audio_url":  combined_audio_url,
        "metadata": {
            **metadata,
            "tts_segments": len(result_segments),
            "tts_failed":   failed,
        },
    }

    # ── Clean up shared ref clip ─────────────────────────────────────────────
    if ref_clip_minio_key:
        try:
            _loop4 = asyncio.new_event_loop()
            try:
                _loop4.run_until_complete(get_storage_service().delete(ref_clip_minio_key))
            finally:
                _loop4.close()
        except Exception as _exc:
            logger.warning("[TTS] could not delete ref clip %s: %s", ref_clip_minio_key, _exc)

    # ── Write to Job row ─────────────────────────────────────────────────────
    if failed and not combined_minio_key:
        msg = f"TTS failed for {failed}/{len(result_segments)} segments"
        BaseJobTask._patch_job(
            job_id, JobStatus.FAILED,
            output_data=output, error_message=msg, completed_at=datetime.utcnow(),
        )
    else:
        BaseJobTask._patch_job(
            job_id, JobStatus.COMPLETED,
            output_data=output, progress=100.0, completed_at=datetime.utcnow(),
        )

    # ── Update VideoTask ─────────────────────────────────────────────────────
    if task_id:
        from app.tasks.models import TaskStatus
        BaseJobTask._patch_task(
            task_id,
            TaskStatus.COMPLETED,
            segments=result_segments,
            combined_audio_key=combined_minio_key,
            combined_audio_url=combined_audio_url,
            progress=100.0,
            completed_at=datetime.utcnow(),
        )

    logger.info(
        "[TTS] combined | job=%s | segments=%d | failed=%d | merged=%s",
        job_id, len(result_segments), failed, bool(combined_minio_key),
    )
    return output


# ===========================================================================
# Stubs kept for compatibility
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.tts_synthesize",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_tts",
)
def tts_synthesize(
    self,
    job_id: str,
    video_id: str,
    translation_key: Optional[str] = None,
    target_lang: str = "en",
) -> dict:
    """Legacy stub — use tts_pipeline for the pipeline flow."""
    if isinstance(job_id, dict):
        video_id = job_id.get("video_id")
        job_id = job_id.get("job_id")
    self._patch_job(job_id, JobStatus.PROCESSING, celery_task_id=self.request.id, started_at=datetime.utcnow())
    logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)
    output = {"job_id": job_id, "video_id": video_id, "audio_key": None}
    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
    return output


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.dubbing_merge",
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
)
def dubbing_merge(self, job_id: str, video_id: str, audio_key: str) -> dict:
    """Stub: merge synthesised audio with the original video."""
    self._patch_job(job_id, JobStatus.PROCESSING, celery_task_id=self.request.id, started_at=datetime.utcnow())
    logger.info("[STUB] dubbing_merge job=%s video=%s", job_id, video_id)
    return {"job_id": job_id, "video_id": video_id, "output_key": None}
