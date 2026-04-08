"""AI pipeline Celery tasks.

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.
"""
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.tasks.buffer import SegmentBuffer
from app.jobs.models import JobStatus

logger = logging.getLogger(__name__)


# ===========================================================================
# Speech-to-Text
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.stt_transcribe_only",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_stt",
)
def stt_transcribe_only(
    self,
    job_id: str,
    video_id: str,
    language: Optional[str] = None,
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Transcribe ONLY the audio track of *video_id* (no NMT, no TTS).

    Downloads the file from MinIO, runs Whisper, returns transcript + segments.
    Used by /api/transcription/transcribe-async endpoint.

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript_key": str,           # MinIO key of source audio
            "transcript":     str,           # full text
            "segments":       list[dict],    # [{start, end, text}, ...]
            "metadata":       dict,
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING + record Celery task id ───────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 2. Look up the Video row to get the MinIO key ────────────────────────
    def _get_file_key() -> str:
        from app.media.models import Video  # noqa: F401 - needed for SQLAlchemy mapper resolution
        engine, SessionLocal = self._make_db()
        try:
            with SessionLocal() as db:
                video = db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found.")
                # Prefer the extracted audio track; fall back to the raw file
                return video.audio_path or video.file_path
        finally:
            engine.dispose()

    file_key: str = _get_file_key()
    logger.info("[STT-only] job=%s video=%s file_key=%s", job_id, video_id, file_key)

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
            logger.info("[STT-only] downloaded %s → %s", file_key, local_path)
        else:
            # Local storage — point directly at the file, no copy needed
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe using the shared WhisperModelManager instance ──────
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

            logger.info(f"[STT-only] Starting transcription | duration={info.duration:.1f}s | job={job_id}")

            for seg in segments_generator:
                segment_dict = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

                current_time = segment_dict["end"]
                # Progress from 25% (start) to 90% (near completion)
                progress = 25.0 + (65.0 * current_time / max(info.duration, 0.1))
                self.update_progress(job_id, min(progress, 90.0))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            result = {
                "transcript": full_transcript,
                "segments": structured_segments,
                "metadata": {
                    "language": info.language,
                    "duration": round(info.duration, 2),
                    "model_size": whisper.model_size,
                    "device": whisper.device,
                    "compute_type": whisper.compute_type,
                    "processing_time": round(processing_time, 2),
                    "segment_count": len(structured_segments),
                },
            }

        except Exception as exc:
            logger.error("[STT-only] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 95.0)

        # ── 5. Persist output_data — on_success hook will set COMPLETED ──────────
        output = {
            "job_id":         job_id,
            "video_id":       video_id,
            "transcript_key": file_key,
            "transcript":     result["transcript"],
            "segments":       structured_segments,
            "metadata":       result["metadata"],
        }

        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

        logger.info(
            "[STT-only] job=%s done | duration=%.1fs | segments=%d",
            job_id,
            result["metadata"].get("duration", 0),
            result["metadata"].get("segment_count", 0),
        )

        return output


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

    Downloads the file from MinIO, runs Whisper via the shared
    ``transcribe_task`` model instance (loaded once per worker), then
    stores the result in the Job row.

    As segments are transcribed, they are immediately dispatched to the
    NMT queue for parallel translation (chunked processing).

    Returns:
        {
            "job_id":         str,
            "video_id":       str,
            "transcript_key": None,          # raw file unchanged in storage
            "transcript":     str,           # full text
            "segments":       list[dict],    # [{start, end, text}, ...]
            "metadata":       dict,
            "nmt_tasks_submitted": int,      # number of NMT tasks dispatched
        }
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager
    from app.jobs.tasks.nmt import nmt_translate_segment

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING + record Celery task id ───────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 2. Look up the Video row to get the MinIO key ────────────────────────
    def _get_file_key() -> str:
        from app.media.models import Video  # noqa: F401 - needed for SQLAlchemy mapper resolution
        engine, SessionLocal = self._make_db()
        try:
            with SessionLocal() as db:
                video = db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found.")
                # Prefer the extracted audio track; fall back to the raw file
                return video.audio_path or video.file_path
        finally:
            engine.dispose()

    file_key: str = _get_file_key()
    logger.info("[STT pipeline] job=%s video=%s file_key=%s", job_id, video_id, file_key)

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
            logger.info("[STT pipeline] downloaded %s → %s", file_key, local_path)
        else:
            # Local storage — point directly at the file, no copy needed
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe using the shared WhisperModelManager instance ──────
        # Whisper yields segments progressively, so we dispatch each segment
        # to NMT queue as soon as it's available (chunked processing)
        structured_segments = []
        nmt_tasks_submitted = 0
        nmt_results = []
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

            logger.info(f"[STT] Starting transcription | duration={info.duration:.1f}s | job={job_id}")

            for seg_idx, seg in enumerate(segments_generator):
                segment_dict = {
                    "segment_id": seg_idx,  # FIX: must be stored so dubbing_merge can reconstruct TTS keys
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                    "translated_text": " ".join(seg.text.split()), # default to original
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

                if segment_dict["text"].strip():
                    res = nmt_translate_segment.apply_async(
                        kwargs={
                            "segment_id": seg_idx,
                            "job_id": job_id,
                            "text": segment_dict["text"],
                            "start": segment_dict["start"],
                            "end": segment_dict["end"],
                            "source_lang": language,
                            "target_lang": target_lang,
                        },
                        queue="ai_nmt"
                    )
                    nmt_results.append(res)
                    nmt_tasks_submitted += 1
                    logger.debug(f"[STT] Dispatched segment {seg_idx} to NMT | job={job_id}")

                current_time = segment_dict["end"]
                # Progress from 25% (start of transcription) to 90% (near completion of streaming)
                progress = 25.0 + (65.0 * current_time / max(info.duration, 0.1))
                self.update_progress(job_id, min(progress, 90.0))

            processing_time = time.time() - start_time
            full_transcript = " ".join(transcript_parts)

            result = {
                "transcript": full_transcript,
                "segments": structured_segments,
                "metadata": {
                    "language": info.language,
                    "duration": round(info.duration, 2),
                    "model_size": whisper.model_size,
                    "device": whisper.device,
                    "compute_type": whisper.compute_type,
                    "processing_time": round(processing_time, 2),
                    "segment_count": len(structured_segments),
                },
            }

            # ── 5. Wait for background NMT tasks and merge results ───────────
            # Use SegmentBuffer (priority queue) to order out-of-order NMT results
            segment_buffer = SegmentBuffer()
            completed_count = 0
            failed_count = 0

            if nmt_tasks_submitted > 0:
                logger.info(f"[STT] Waiting for {nmt_tasks_submitted} NMT translations... | job={job_id}")

                # Use as_completed to process results as they arrive (out of order)
                from celery.result import AsyncResult
                async_results = [AsyncResult(r.id) for r in nmt_results]
                processed_result_ids = set()  # Track which results we've already processed

                start_wait = time.time()
                timeout = 600

                while completed_count + failed_count < nmt_tasks_submitted:
                    elapsed = time.time() - start_wait
                    if elapsed > timeout:
                        logger.warning(f"[STT] NMT wait timeout after {elapsed:.1f}s | job={job_id}")
                        break

                    # Check each result (polling approach - in production could use callback)
                    for res in async_results:
                        if res.ready() and res.id not in processed_result_ids:
                            processed_result_ids.add(res.id)  # Mark as processed
                            try:
                                task_result = res.result  # Use .result instead of .get()
                                logger.debug(f"[STT] Got NMT result: {task_result} | job={job_id}")
                                if task_result and "segment_id" in task_result:
                                    idx = task_result["segment_id"]
                                    start_time = task_result.get("start", 0)
                                    txt = task_result.get("translated_text")

                                    if 0 <= idx < len(structured_segments) and txt:
                                        # Update segment with translation immediately
                                        structured_segments[idx]["translated_text"] = txt
                                        logger.info(f"[STT] Received translation for segment {idx}: '{txt[:50]}...' | job={job_id}")
                                        
                                        # PROGRESSIVE TTS: Dispatch TTS immediately for this segment
                                        from app.jobs.celery_app import synthesize_tts
                                        if txt.strip():  # Only if there's actual text
                                            # FIX: use job_id (not video_id) + zero-padded index to match
                                            # the standard key pattern used everywhere else
                                            tts_key = f"tts/{job_id}/segment_{idx:04d}.wav"
                                            tts_result = synthesize_tts.apply_async(
                                                kwargs={
                                                    "text": txt,
                                                    "job_id": f"{job_id}_segment_{idx}",
                                                    "upload_to_minio": True,
                                                    "minio_key": tts_key,
                                                },
                                                queue="ai_tts",
                                            )
                                            # Store both task_id AND the resolved key so dubbing_merge
                                            # can use it directly without reconstructing
                                            structured_segments[idx]["tts_task_id"] = tts_result.id
                                            structured_segments[idx]["tts_audio_key"] = tts_key
                                            logger.info(f"[STT] Progressive TTS dispatched for segment {idx} | key={tts_key} | job={job_id}")
                                        
                                        # Push to priority queue for ordering verification
                                        segment_buffer.push(
                                            segment_id=idx,
                                            start=start_time,
                                            data={"segment_id": idx, "translated_text": txt}
                                        )
                                        completed_count += 1
                                        logger.debug(
                                            f"[STT] NMT+TTS result processed segment_id={idx} start={start_time:.2f} | job={job_id}"
                                        )
                            except Exception as e:
                                failed_count += 1
                                logger.warning(f"[STT] NMT task failed: {e} | job={job_id}")

                    # Small sleep to avoid busy-waiting
                    time.sleep(0.1)

            # Pop all results in sequence order (no longer needed for TTS dispatch since progressive)
            for i in range(len(structured_segments)):
                item = segment_buffer.pop_next(i)
                # Translation already applied in progressive loop above
                
            # Validate NMT count
            successful_translations = completed_count
            if successful_translations != nmt_tasks_submitted:
                logger.warning(
                    f"[STT] NMT+TTS dispatch incomplete: {successful_translations}/{nmt_tasks_submitted} segments processed | job={job_id}"
                )

            logger.info(f"[STT] Progressive NMT+TTS complete: {completed_count} segments processed, {failed_count} failed | job={job_id}")

            # Combine individual translated segments into a full translated transcript
            if target_lang and target_lang != info.language:
                result["translated_transcript"] = " ".join([
                    s.get("translated_text", "") for s in structured_segments
                ]).strip()
            else:
                result["translated_transcript"] = result["transcript"]

            # ── 6. Final result with progressive TTS metadata ──────────────────────
            tts_segments_dispatched = sum(1 for s in structured_segments if s.get("tts_task_id"))
            result.update({
                "job_id": job_id,
                "video_id": video_id,
                "transcript_key": file_key,
                "segments": structured_segments,
                "nmt_tasks_submitted": nmt_tasks_submitted,
                "tts_segments_dispatched": tts_segments_dispatched,
            })

        except Exception as exc:
            logger.error("[STT pipeline] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 95.0)

        # ── 7. Persist output_data — on_success hook will set COMPLETED ──────────
        output = {
            "job_id":         job_id,
            "video_id":       video_id,
            "transcript_key": file_key,
            "transcript":     result["transcript"],
            "translated_transcript": result["translated_transcript"],
            "segments":       structured_segments,
            "metadata":       result["metadata"],
            "nmt_tasks_submitted": nmt_tasks_submitted,
            "tts_segments_dispatched": tts_segments_dispatched,
        }

        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
        # Note: BaseJobTask.on_success will set it to COMPLETED immediately after return

        logger.info(
            "[STT pipeline] PROGRESSIVE job=%s done | duration=%.1fs | segments=%d | nmt_tasks=%d | tts_dispatched=%d",
            job_id,
            result["metadata"].get("duration", 0),
            result["metadata"].get("segment_count", 0),
            nmt_tasks_submitted,
            tts_segments_dispatched,
        )

        return output


# ===========================================================================
# Progressive STT Task (New Implementation)
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.stt_transcribe_progressive",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_stt",
)
def stt_transcribe_progressive(
    self,
    job_id: str,
    video_id: str,
    language: Optional[str] = None,
    target_lang: str = "arb_Arab",
) -> dict:
    """
    Progressive STT task with real-time video building.
    
    This task:
    1. Transcribes audio using Whisper
    2. Initializes progressive timeline
    3. Dispatches individual segments to progressive pipeline
    4. Returns immediately (doesn't wait for completion)
    """
    from app.media.storage import S3StorageService, get_storage_service
    from app.stt.models import WhisperModelManager
    from app.progressive.service import ProgressiveVideoBuilder

    whisper = WhisperModelManager()
    storage = get_storage_service()

    # ── 1. Mark PROCESSING + record Celery task id ───────────────────────────
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )

    # ── 2. Look up the Video row to get the MinIO key ────────────────────────
    def _get_video_info() -> tuple[str, str]:
        from app.media.models import Video  # noqa: F401 - needed for SQLAlchemy mapper resolution
        engine, SessionLocal = self._make_db()
        try:
            with SessionLocal() as db:
                video = db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found.")
                # Return both file key and original video path
                file_key = video.audio_path or video.file_path
                video_key = video.file_path  # Original video file for progressive merging
                return file_key, video_key
        finally:
            engine.dispose()

    file_key, video_key = _get_video_info()
    logger.info("[STT-PROGRESSIVE] job=%s video=%s file_key=%s", job_id, video_id, file_key)

    self.update_progress(job_id, 10.0)

    # ── 3. Download from MinIO ───────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix = Path(file_key).suffix or ".mp3"
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
            logger.info("[STT-PROGRESSIVE] downloaded %s → %s", file_key, local_path)
        else:
            local_path = Path(storage.get_absolute_path(file_key))

        self.update_progress(job_id, 25.0)

        # ── 4. Transcribe and collect segments ──────────────────────────
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

            logger.info(f"[STT-PROGRESSIVE] Starting transcription | duration={info.duration:.1f}s | job={job_id}")

            # Collect all segments first
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

            logger.info(f"[STT-PROGRESSIVE] Transcription complete | segments={len(structured_segments)} | job={job_id}")

            # ── 5. Initialize Progressive Timeline ──────────────────────────
            async def _initialize_progressive():
                # FIX: never use the global AsyncSessionLocal (FastAPI pool) from
                # a Celery worker — asyncpg binds connections to the event loop
                # they were created on.  Create a fresh engine with NullPool so
                # each worker invocation gets its own isolated connection.
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker
                from sqlalchemy.pool import NullPool

                _engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
                _AsyncSession = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
                try:
                    async with _AsyncSession() as db:
                        builder = ProgressiveVideoBuilder(db)
                        
                        # Get full video path from storage
                        if isinstance(storage, S3StorageService):
                            # Download original video temporarily to get full path
                            video_suffix = Path(video_key).suffix or ".mp4"
                            video_local_path = Path(tmp_dir) / f"video{video_suffix}"
                            
                            async with storage.session.client(
                                "s3",
                                endpoint_url=storage.endpoint_url,
                                aws_access_key_id=storage.access_key,
                                aws_secret_access_key=storage.secret_key,
                            ) as s3:
                                await s3.download_file(
                                    storage.bucket_name, video_key, str(video_local_path)
                                )
                            original_video_path = str(video_local_path)
                        else:
                            original_video_path = storage.get_absolute_path(video_key)
                        
                        # Initialize progressive timeline
                        timeline = await builder.initialize_timeline(
                            job_id=job_id,
                            video_id=video_id,
                            segments=structured_segments,
                            original_video_path=original_video_path
                        )
                        
                        logger.info(f"[STT-PROGRESSIVE] Timeline initialized | segments={len(structured_segments)} | job={job_id}")
                        return timeline
                finally:
                    await _engine.dispose()

            # Run async initialization
            try:
                timeline = self._run_sync(_initialize_progressive())
                if not timeline:
                    raise ValueError("Timeline initialization returned None")
                    
                logger.info(f"[STT-PROGRESSIVE] Timeline validated | job={job_id} | base_video={timeline.current_video_path}")
            except Exception as e:
                logger.error(f"[STT-PROGRESSIVE] Timeline initialization failed | job={job_id} | error={e}", exc_info=True)
                # Don't dispatch segments if timeline failed - job should be marked as failed
                result = {
                    "job_id": job_id,
                    "video_id": video_id,
                    "transcript_key": file_key,
                    "transcript": full_transcript,
                    "segments": structured_segments,
                    "metadata": {
                        "language": info.language,
                        "duration": round(info.duration, 2),
                        "model_size": whisper.model_size,
                        "device": whisper.device,
                        "compute_type": whisper.compute_type,
                        "processing_time": round(processing_time, 2),
                        "segment_count": len(structured_segments),
                    },
                    "progressive_timeline_initialized": False,
                    "segments_dispatched": 0,
                    "mode": "progressive",
                    "error": f"Timeline initialization failed: {str(e)}"
                }
                
                # Mark job as failed
                self.update_progress(job_id, 100.0, "FAILED", f"Timeline initialization failed: {str(e)}")
                return result

            # ── 6. Dispatch Progressive Segment Processing ──────────────────────────
            segments_dispatched = 0
            
            # Only dispatch segments if timeline was successfully initialized
            for i, segment in enumerate(structured_segments):
                if segment["text"].strip():  # Only process non-empty segments
                    # Dispatch to progressive NMT step (first in chain)
                    progressive_nmt_step.apply_async(
                        kwargs={
                            "job_id": job_id,
                            "segment_id": i,
                            "segment_data": segment,
                            "source_lang": language,
                            "target_lang": target_lang
                        },
                        queue="ai_nmt"  # Start with NMT processing
                    )
                    segments_dispatched += 1
                    logger.debug(f"[STT-PROGRESSIVE] Dispatched segment {i} to progressive pipeline | job={job_id}")

            # ── 7. Return immediately ──────────────────────────
            result = {
                "job_id": job_id,
                "video_id": video_id,
                "transcript_key": file_key,
                "transcript": full_transcript,
                "segments": structured_segments,
                "metadata": {
                    "language": info.language,
                    "duration": round(info.duration, 2),
                    "model_size": whisper.model_size,
                    "device": whisper.device,
                    "compute_type": whisper.compute_type,
                    "processing_time": round(processing_time, 2),
                    "segment_count": len(structured_segments),
                },
                "progressive_timeline_initialized": True,
                "segments_dispatched": segments_dispatched,
                "mode": "progressive"
            }

        except Exception as exc:
            logger.error("[STT-PROGRESSIVE] transcription error job=%s: %s", job_id, exc)
            raise self.retry(exc=exc)

        self.update_progress(job_id, 95.0)

        # ── 8. Store result and mark as processing (segments will complete individually) ──────────
        self._patch_job(job_id, JobStatus.PROCESSING, output_data=result)

        logger.info(
            "[STT-PROGRESSIVE] Complete | job=%s | duration=%.1fs | segments=%d | dispatched=%d",
            job_id,
            result["metadata"].get("duration", 0),
            result["metadata"].get("segment_count", 0),
            segments_dispatched,
        )

        return result


# ===========================================================================
# Progressive Segment Pipeline
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.progressive_nmt_step",
    max_retries=3,
    default_retry_delay=10,
    queue="ai_nmt",
)
def progressive_nmt_step(
    self, 
    job_id: str, 
    segment_id: int, 
    segment_data: dict, 
    source_lang: str, 
    target_lang: str
) -> dict:
    """
    Step 1: Process segment through NMT translation.
    
    Chains to TTS step on success. No blocking .get() calls.
    """
    logger.info(f"[PROGRESSIVE-NMT] Starting segment {segment_id} | job={job_id}")
    
    try:
        # Use NMT model directly instead of calling another Celery task
        from app.nmt.model import NLLBTranslatorWrapper
        
        translator = NLLBTranslatorWrapper()
        translated_text = translator._translate_item(
            text=segment_data["text"],
            src_lang=source_lang, 
            tgt_lang=target_lang
        )
        
        nmt_result = {
            "status": "completed",
            "segment_id": segment_id,
            "job_id": job_id,
            "original_text": segment_data["text"],
            "translated_text": translated_text,
            "start": segment_data["start"],
            "end": segment_data["end"],
            "source_lang": source_lang,
            "target_lang": target_lang
        }
        
        logger.info(f"[PROGRESSIVE-NMT] Complete segment {segment_id} | job={job_id} | text='{translated_text[:50]}...'")

        # Chain to TTS step (no blocking .get())
        celery_app.send_task(
            'app.jobs.tasks.pipeline.progressive_tts_step',
            kwargs={
                "job_id": job_id,
                "segment_id": segment_id,
                "segment_data": segment_data,
                "nmt_result": nmt_result,
            },
            queue="ai_tts"
        )
        
        return nmt_result
        
    except Exception as exc:
        logger.error(f"[PROGRESSIVE-NMT] Failed segment {segment_id} | job={job_id} | error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.progressive_tts_step",
    max_retries=3,
    default_retry_delay=10,
    queue="ai_tts",
)
def progressive_tts_step(
    self,
    job_id: str,
    segment_id: int,
    segment_data: dict,
    nmt_result: dict
) -> dict:
    """
    Step 2: Process segment through TTS synthesis.
    
    Chains to merge step on success. No blocking .get() calls.
    """
    logger.info(f"[PROGRESSIVE-TTS] Starting segment {segment_id} | job={job_id}")
    
    try:
        # Use TTS model directly instead of calling another Celery task
        from app.tts.models import SilmaTTSModelManager
        
        # FIX: key pattern must match what dubbing_merge expects:
        # tts/{job_id}/segment_{idx:04d}.wav
        audio_key = f"tts/{job_id}/segment_{segment_id:04d}.wav"
        
        # Use TTS model directly
        tts_manager = SilmaTTSModelManager()
        
        # Synthesize and upload to MinIO
        audio_result = tts_manager.synthesize_and_upload(
            text=nmt_result["translated_text"],
            minio_key=audio_key
        )
        
        tts_result = {
            "status": "completed",
            "segment_id": segment_id,
            "job_id": job_id,
            "text": nmt_result["translated_text"],
            "audio_key": audio_key,
            "duration": audio_result.get("duration", 0.0),
            "sample_rate": audio_result.get("sample_rate", 22050)
        }
        
        logger.info(f"[PROGRESSIVE-TTS] Complete segment {segment_id} | job={job_id} | audio_key={audio_key}")

        # Chain to merge step (no blocking .get())
        celery_app.send_task(
            'app.jobs.tasks.pipeline.progressive_merge_step',
            kwargs={
                "job_id": job_id,
                "segment_id": segment_id,
                "segment_data": segment_data,
                "nmt_result": nmt_result,
                "tts_result": tts_result,
            },
            queue="pipeline"
        )
        
        return tts_result
        
    except Exception as exc:
        logger.error(f"[PROGRESSIVE-TTS] Failed segment {segment_id} | job={job_id} | error={exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.progressive_merge_step", 
    max_retries=3,  # Restored to normal - timeline persistence fixes state loss
    default_retry_delay=10,  # Standard backoff for transient errors
    queue="pipeline",
)
def progressive_merge_step(
    self,
    job_id: str,
    segment_id: int,
    segment_data: dict,
    nmt_result: dict,
    tts_result: dict
) -> dict:
    """
    Step 3: Progressive video merge - insert TTS audio into growing video.
    """
    logger.info(f"[PROGRESSIVE-MERGE] Starting segment {segment_id} | job={job_id}")
    
    try:
        # Progressive Video Merge
        async def _merge_segment():
            # FIX: use a fresh async engine with NullPool — never the global
            # AsyncSessionLocal (FastAPI pool) from inside a Celery worker event loop
            from app.progressive.service import ProgressiveVideoBuilder
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy.pool import NullPool
            from app.config import settings

            _engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
            _AsyncSession = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with _AsyncSession() as db:
                    builder = ProgressiveVideoBuilder(db)
                    return await builder.segment_ready_for_merge(
                        job_id=job_id,
                        segment_id=segment_id,
                        tts_audio_key=tts_result["audio_key"],
                        nmt_result=nmt_result
                    )
            finally:
                await _engine.dispose()
        
        # Run progressive merge
        merge_success = self._run_sync(_merge_segment())
        
        if not merge_success:
            raise ValueError(f"Progressive merge failed for segment {segment_id}")
        
        logger.info(f"[PROGRESSIVE-MERGE] Complete segment {segment_id} | job={job_id}")
        
        return {
            "job_id": job_id,
            "segment_id": segment_id, 
            "status": "completed",
            "nmt_result": nmt_result,
            "tts_result": tts_result,
            "merge_completed": True,
            "timestamp": time.time()
        }
        
    except Exception as exc:
        logger.error(f"[PROGRESSIVE-MERGE] Failed | job={job_id} | segment={segment_id} | error={exc}")
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Neural Machine Translation
# ---------------------------------------------------------------------------



# ===========================================================================
# Text-to-Speech
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
    """Compatibility: if called in a chain, extract job_id from dict."""
    if isinstance(job_id, dict):
        video_id = job_id.get("video_id")
        job_id = job_id.get("job_id")
    """
    Stub: synthesise speech from the translated text.

    Returns:
        {"job_id": job_id, "video_id": video_id, "audio_key": "<storage_key>"}
    """
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )
    # TODO: call TTS service
    logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)

    output = {"job_id": job_id, "video_id": video_id, "audio_key": None}
    self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)

    return output


# ===========================================================================
# Dubbing merge
# ===========================================================================

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.dubbing_merge",
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
)
def dubbing_merge(self, stt_output: dict, job_id: str) -> dict:
    """
    Merge TTS audio segments with original video.
    
    Args:
        stt_output: Result from stt_transcribe task containing segment timing and TTS audio keys
        job_id: Dubbing merge job ID
    
    Takes output from stt_transcribe task which contains segment timing
    and TTS audio keys. Calls DubbingMergeService to:
    - Download TTS segments from MinIO
    - Apply time-stretching for timing mismatches
    - Add silence gaps between segments
    - Concatenate audio
    - Merge with original video
    - Upload final dubbed video
    
    Args:
        job_id: Job ID for tracking
        stt_output: Output dict from stt_transcribe containing:
            - video_id: Video ID
            - segments: List of segments with tts_audio_key
    
    Returns:
        {
            "job_id": job_id,
            "video_id": video_id,
            "output_key": "videos/{video_id}/dubbed/{timestamp}.mp4",
            "output_url": "https://...",
            "metadata": {...}
        }
    """
    # Extract video_id, segments, and the originating STT job_id from upstream output
    if isinstance(stt_output, dict):
        video_id = stt_output.get("video_id")
        segments_data = stt_output.get("segments", [])
        # Use the job_id that STT used to name TTS files.  In the standard chain both
        # are the same value, but pulling it from the payload makes this explicit and
        # safe even if the chain is ever restructured.
        stt_job_id = stt_output.get("job_id", job_id)
    else:
        raise ValueError("Invalid stt_output format")
    
    if not video_id:
        raise ValueError("video_id not found in stt_output")
    
    self._patch_job(
        job_id,
        JobStatus.PROCESSING,
        celery_task_id=self.request.id,
        started_at=datetime.utcnow(),
    )
    
    logger.info(
        f"[DubbingMerge] Starting dubbing_merge | job={job_id} | "
        f"video={video_id} | segments={len(segments_data)}"
    )

    # ── RACE-CONDITION GUARD: wait for all TTS tasks to finish ──────────────
    # stt_transcribe dispatches TTS tasks concurrently and returns before they
    # complete.  Without this poll we would try to download files that do not
    # yet exist in MinIO, causing every segment download to fail silently.
    tts_task_ids = [
        seg["tts_task_id"]
        for seg in segments_data
        if seg.get("tts_task_id")
    ]

    if tts_task_ids:
        from celery.result import AsyncResult

        logger.info(
            f"[DubbingMerge] Waiting for {len(tts_task_ids)} TTS tasks to finish | job={job_id}"
        )
        pending = set(tts_task_ids)
        deadline = time.time() + 600  # 10-minute hard cap
        poll_interval = 2.0           # seconds between sweeps

        while pending and time.time() < deadline:
            for tid in list(pending):
                r = AsyncResult(tid)
                if r.ready():
                    if r.failed():
                        logger.warning(
                            f"[DubbingMerge] TTS task {tid} failed: {r.result} | job={job_id}"
                        )
                    pending.discard(tid)
            if pending:
                time.sleep(poll_interval)

        if pending:
            # Some TTS tasks timed out — log which segments are affected and
            # let the segment-level skip logic below handle missing keys.
            logger.error(
                f"[DubbingMerge] {len(pending)} TTS task(s) did not finish within "
                f"600 s, proceeding with available segments | job={job_id} | "
                f"timed_out={pending}"
            )
        else:
            logger.info(f"[DubbingMerge] All TTS tasks complete | job={job_id}")
    # ── end TTS wait ─────────────────────────────────────────────────────────

    # ── Fetch video file key via sync psycopg2 (never AsyncSessionLocal here) ─
    # DubbingMergeService._merge_with_video needs the original video path from
    # MinIO.  Fetching it here — before the async event loop is created — keeps
    # all DB access in the sync/psycopg2 layer and avoids the asyncpg
    # "another operation is in progress" error.
    def _get_video_file_key() -> str:
        from app.media.models import Video  # noqa: F401
        engine, SessionLocal = self._make_db()
        try:
            with SessionLocal() as db:
                video = db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found")
                return video.file_path
        finally:
            engine.dispose()

    video_file_key = _get_video_file_key()
    logger.info(f"[DubbingMerge] Resolved video_file_key={video_file_key} | job={job_id}")

    try:
        # Convert segment dicts to SegmentTimingInfo objects
        from app.dubbing.schemas import SegmentTimingInfo
        from app.dubbing.service import DubbingMergeService
        
        segments = []
        for seg_data in segments_data:
            segment_id = seg_data.get("segment_id")
            if segment_id is None:
                # Should never happen after Bug 1 fix, but guard anyway
                logger.warning(
                    f"[DubbingMerge] Segment missing segment_id field, skipping: {seg_data}"
                )
                continue

            # Prefer the explicit key stored by stt_transcribe; fall back to
            # reconstructing it from the known naming convention.
            tts_audio_key = seg_data.get("tts_audio_key")
            if not tts_audio_key and seg_data.get("tts_task_id"):
                # FIX: use stt_job_id + zero-padded index — must match the key
                # written by synthesize_tts in stt_transcribe
                tts_audio_key = f"tts/{stt_job_id}/segment_{segment_id:04d}.wav"
            
            if not tts_audio_key:
                logger.warning(
                    f"[DubbingMerge] Segment {segment_id} has no TTS audio key, skipping"
                )
                continue
            
            seg_info = SegmentTimingInfo(
                segment_id=segment_id,
                start=seg_data.get("start", 0.0),
                end=seg_data.get("end", 0.0),
                duration=seg_data.get("end", 0.0) - seg_data.get("start", 0.0),
                original_text=seg_data.get("text", ""),
                translated_text=seg_data.get("translated_text", ""),
                tts_audio_key=tts_audio_key
            )
            segments.append(seg_info)
        
        if not segments:
            raise ValueError("No valid segments with TTS audio found")
        
        logger.info(f"[DubbingMerge] Processing {len(segments)} segments with TTS audio")
        
        # Progress callback
        def progress_callback(percent: float):
            self.update_progress(job_id, percent)
        
        # Run dubbing merge service (sync context - use asyncio.run)
        import asyncio
        service = DubbingMergeService()
        
        async def async_progress_callback(progress: float):
            """Async wrapper for progress updates in Celery task."""
            self.update_progress(job_id, progress)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                service.merge_segments(
                    video_id=video_id,
                    segments=segments,
                    job_id=job_id,
                    progress_callback=async_progress_callback,
                    video_file_key=video_file_key,  # pre-fetched via sync psycopg2
                )
            )
        finally:
            loop.close()
        
        # Update job with output
        output = {
            "job_id": result.job_id,
            "video_id": result.video_id,
            "output_key": result.output_key,
            "output_url": result.output_url,
            "metadata": result.metadata
        }
        
        self._patch_job(job_id, JobStatus.PROCESSING, output_data=output)
        
        logger.info(
            f"[DubbingMerge] Completed | job={job_id} | "
            f"output={result.output_key} | "
            f"time={result.metadata.get('processing_time', 0):.1f}s"
        )
        
        return output
    
    except Exception as exc:
        logger.error(f"[DubbingMerge] Failed | job={job_id} | error={exc}", exc_info=True)
        raise self.retry(exc=exc)


# ===========================================================================
# Full dubbing pipeline (orchestrator)
# ===========================================================================

def dispatch_full_dubbing_pipeline(
    job_id: str,
    video_id: str,
    source_lang: str = "auto",
    target_lang: str = "arb_Arab",
) -> None:
    """
    Dispatch the full dubbing pipeline as a Celery ``chain``.

    Sequence: 
      1. stt_transcribe - Transcribe audio + dispatch NMT for each segment
      2. (NMT tasks run in parallel in ai_nmt queue - already dispatched by STT)
      3. (TTS tasks run progressively as NMT completes - already dispatched by STT)
      4. dubbing_merge - Wait for TTS completion, merge audio with video
    
    Note: STT task handles NMT and TTS dispatching internally (progressive pipeline).
    The dubbing_merge task receives the STT output with segment metadata and
    TTS audio keys, then performs the final video merge.
    """
    from celery import chain
    
    logger.info(f"[DISPATCH] Creating pipeline chain for job {job_id}")
    
    pipeline = chain(
        # STT transcribes and dispatches NMT+TTS progressively
        stt_transcribe.s(job_id, video_id, source_lang, target_lang),
        # Dubbing merge receives STT output and merges TTS audio with video
        dubbing_merge.s(job_id),
    )
    
    result = pipeline.apply_async()
    logger.info(f"[DISPATCH] Pipeline chain submitted with ID: {result.id}")
    
    return result