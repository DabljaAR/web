"""Merge worker — combines TTS audio segments with original video.

Consumes ``job.start.merge`` and publishes results to ``job.results.merge``.
"""
import logging
from typing import Optional

from app.dubbing.schemas import SegmentTimingInfo
from app.dubbing.service import DubbingMergeService
import app.worker._db as _db
from app.worker._db import (
    create_child_job,
    load_job,
    update_job_output,
)


def _make_engine():
    """Wrapper so tests can patch merge_worker._make_engine."""
    return _db._make_engine()
from app.worker.base_worker import BaseWorker
from app.worker.registry import register

logger = logging.getLogger(__name__)


def _get_video_media_type(video_id: str) -> str:
    """Resolve the media type (video/audio) for a given video_id."""
    from app.videos.models import MediaType, Video as MediaVideo

    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            row = db.get(MediaVideo, video_id)
            if row is None:
                return "audio"
            mt = row.media_type
            if hasattr(mt, "value"):
                return mt.value.lower()
            return str(mt).lower()
    finally:
        engine.dispose()


def _get_original_media_key(video_id: str, media_type: str) -> Optional[str]:
    """Get the storage key for the original media file."""
    from app.videos.models import Video as MediaVideo

    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            row = db.get(MediaVideo, video_id)
            if row is None:
                return None
            if media_type == "video":
                return row.file_path
            return row.audio_path or row.file_path
    finally:
        engine.dispose()


@register(
    routing_key="job.start.merge",
    result_key="job.results.merge",
    job_type="DUBBING_MERGE",
    description="Merge TTS audio segments into the original video",
)
async def handle_merge(job_id: str) -> dict:
    """Merge TTS audio segments into the original video.

    ``job_id`` is the TTS child job's ID. Load its output_data to get
    the TTS audio keys for each segment, then run the dubbing merge
    service to produce the final output.
    """
    import asyncio

    # 1. Load the TTS child job
    tts_job = load_job(job_id)
    if tts_job is None:
        raise ValueError(f"TTS job {job_id} not found")

    tts_output = tts_job.get("output_data", {})
    segments = tts_output.get("segments", [])
    video_id = tts_job.get("video_id")

    if not video_id:
        raise ValueError(f"No video_id for TTS job {job_id}")

    if not segments:
        logger.warning("[MERGE] No segments to merge | job=%s", job_id)
        return {"status": "completed", "output_key": None}

    # 2. Filter to segments that have audio
    valid_segments = [s for s in segments if s.get("tts_key") and not s.get("tts_error")]
    if not valid_segments:
        logger.error("[MERGE] No valid TTS segments to merge | job=%s", job_id)
        return {"status": "failed", "error": "No valid TTS segments", "output_key": None}

    # 3. Create MERGE child job
    merge_job_id = create_child_job(
        job_id,
        "DUBBING_MERGE",
        input_data={"video_id": video_id},
    )

    update_job_output(merge_job_id, {"status": "processing"})

    # 4. Determine media type and original media key
    media_type = _get_video_media_type(video_id)
    original_media_key = _get_original_media_key(video_id, media_type)

    # 5. Build SegmentTimingInfo list
    segment_infos = []
    for s in valid_segments:
        start_val = float(s.get("start") or 0.0)
        end_val = float(s.get("end") or start_val)
        if end_val <= start_val:
            end_val = start_val + 0.001
        segment_infos.append(
            SegmentTimingInfo(
                segment_id=int(s.get("segment_id", 0)),
                start=start_val,
                end=end_val,
                duration=max(end_val - start_val, 0.001),
                translated_text=str(s.get("translated_text", "")),
                tts_audio_key=s["tts_key"],
            )
        )

    # 6. Run dubbing merge
    merge_service = DubbingMergeService()
    combined_audio_key = f"tts/{merge_job_id}/combined.wav"

    merge_response = await merge_service.merge_segments(
        video_id=video_id,
        segments=segment_infos,
        job_id=merge_job_id,
        media_type=media_type,
        output_key_prefix=f"dubbed/{video_id}",
        original_media_key=original_media_key,
        combined_audio_key=combined_audio_key,
    )

    merged_meta = merge_response.metadata or {}
    output_key = merge_response.output_key
    output_url = merge_response.output_url

    # 7. Update the video record with dubbed path
    if output_key:
        from app.videos.models import Video as MediaVideo

        engine, SessionLocal = _make_engine()
        try:
            with SessionLocal() as db:
                row = db.get(MediaVideo, video_id)
                if row is not None:
                    row.dubbed_video_path = output_key
                    existing_meta = dict(row.dubbing_metadata) if row.dubbing_metadata else {}
                    row.dubbing_metadata = {
                        **existing_meta,
                        "merge_job_id": merge_job_id,
                        "combined_audio_key": merged_meta.get("combined_audio_key"),
                        "dubbed_video_key": output_key,
                        "dubbed_video_url": output_url,
                    }
                    db.commit()
        finally:
            engine.dispose()

    output = {
        "_result_job_id": merge_job_id,
        "status": "completed",
        "video_id": video_id,
        "output_key": output_key,
        "output_url": output_url,
        "metadata": {
            "media_type": media_type,
            "segments_merged": len(segment_infos),
            "combined_audio_key": merged_meta.get("combined_audio_key"),
        },
    }

    update_job_output(merge_job_id, output, status="COMPLETED")

    logger.info(
        "[MERGE] Done | job=%s | output=%s | segments=%d",
        merge_job_id, output_key, len(segment_infos),
    )

    return output


def create_worker(rabbitmq_url: str, concurrency: int = 2) -> BaseWorker:
    """Create and configure a Merge worker."""
    worker = BaseWorker(
        rabbitmq_url=rabbitmq_url,
        concurrency=concurrency,
        worker_name="merge",
    )
    worker.register_handler(
        routing_key="job.start.merge",
        fn=handle_merge,
        result_key="job.results.merge",
        job_type="DUBBING_MERGE",
    )
    return worker
