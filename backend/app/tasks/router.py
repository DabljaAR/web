"""VideoTask REST API — read-only status and result endpoints."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import User
from app.tasks.models import VideoTask, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SegmentOut(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    tts_key: Optional[str] = None
    audio_url: Optional[str] = None


class VideoTaskSummary(BaseModel):
    id: str
    video_id: str
    status: TaskStatus
    progress: float
    output_type: str
    processing_mode: str
    source_lang: Optional[str]
    target_lang: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class VideoTaskDetail(VideoTaskSummary):
    transcript: Optional[str]
    translated_transcript: Optional[str]
    segments: Optional[List[SegmentOut]]
    stt_metadata: Optional[dict]
    num_beams: int
    english_ratio_threshold: float
    combined_audio_key: Optional[str]
    original_audio_url: Optional[str] = None
    original_video_url: Optional[str] = None
    combined_audio_url: Optional[str] = None
    dubbed_video_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/video/{video_id}", response_model=List[VideoTaskSummary])
async def list_tasks_for_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all VideoTask rows for a given video, newest first."""
    result = await db.execute(
        select(VideoTask)
        .where(VideoTask.video_id == video_id, VideoTask.user_id == current_user.user_id)
        .order_by(VideoTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return tasks


def _split_proportionally(text: str, char_weights: list[int]) -> list[str]:
    """Split text into len(char_weights) parts weighted by char_weights."""
    if not text or not char_weights:
        return [""] * len(char_weights)
    words = text.split()
    total_w = sum(char_weights) or 1
    parts, offset = [], 0
    for i, w in enumerate(char_weights):
        if i == len(char_weights) - 1:
            parts.append(" ".join(words[offset:]))
        else:
            n = max(1, round(len(words) * w / total_w))
            parts.append(" ".join(words[offset:offset + n]))
            offset += n
    return parts


def _build_segments(task) -> list[SegmentOut]:
    """Serve segments with text fields, backfilling from stt_segments / translated_transcript."""
    raw_segs = task.segments or []
    if not raw_segs:
        return []

    # --- original_text: from stored field OR stt_segments lookup by start time ---
    stt_map: dict[float, str] = {
        round(float(s.get("start", 0)), 2): s.get("text", "")
        for s in (task.stt_segments or [])
    }

    orig_texts = [
        s.get("original_text") or stt_map.get(round(float(s.get("start", 0)), 2), "")
        for s in raw_segs
    ]

    # --- translated_text: from stored field OR split translated_transcript ---
    tran_stored = [s.get("translated_text") or "" for s in raw_segs]
    if any(tran_stored):
        tran_texts = tran_stored
    elif task.translated_transcript:
        weights = [len(t) for t in orig_texts]
        tran_texts = _split_proportionally(task.translated_transcript, weights)
    else:
        tran_texts = [""] * len(raw_segs)

    result = []
    for s, orig, tran in zip(raw_segs, orig_texts, tran_texts):
        result.append(SegmentOut(
            start=s.get("start"),
            end=s.get("end"),
            original_text=orig or None,
            translated_text=tran or None,
            tts_key=s.get("tts_key"),
            audio_url=s.get("audio_url"),
        ))

    logger.debug(
        "_build_segments task=%s segs=%d stt_fallback=%d tran_split=%s",
        task.id, len(result),
        sum(1 for o in orig_texts if o),
        not any(tran_stored),
    )
    return result


@router.get("/{task_id}", response_model=VideoTaskDetail)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full detail for a single VideoTask, including presigned audio URLs."""
    task = await db.get(VideoTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    original_audio_url: Optional[str] = None
    original_video_url: Optional[str] = None
    combined_audio_url: Optional[str] = None
    dubbed_video_url: Optional[str] = None

    # Best-effort presigned URL generation — failures are logged but do not break the response
    try:
        from app.storage import get_storage_service
        from app.videos.models import Video
        storage = get_storage_service()

        video = await db.get(Video, task.video_id)
        if video:
            audio_key = video.audio_path or video.file_path
            if audio_key:
                try:
                    original_audio_url = await storage.get_url(audio_key)
                except Exception as e:
                    logger.warning(
                        "Failed to generate presigned URL for original audio key %s: %s",
                        audio_key, e,
                    )
            if video.file_path and video.media_type and video.media_type.value == "VIDEO":
                try:
                    original_video_url = await storage.get_url(video.file_path)
                except Exception as e:
                    logger.warning(
                        "Failed to generate presigned URL for original video key %s: %s",
                        video.file_path, e,
                    )
            if getattr(video, "dubbed_video_path", None):
                try:
                    dubbed_video_url = await storage.get_url(video.dubbed_video_path)
                except Exception as e:
                    logger.warning(
                        "Failed to generate presigned URL for dubbed video key %s: %s",
                        video.dubbed_video_path, e,
                    )

        if task.combined_audio_key:
            try:
                combined_audio_url = await storage.get_url(task.combined_audio_key)
            except Exception as e:
                logger.warning(
                    "Failed to generate presigned URL for combined audio key %s: %s",
                    task.combined_audio_key, e,
                )
    except Exception as e:
        logger.warning("Could not initialise storage service for task %s: %s", task_id, e)

    return VideoTaskDetail(
        id=task.id,
        video_id=task.video_id,
        status=task.status,
        progress=task.progress,
        output_type=task.output_type,
        processing_mode=task.processing_mode,
        source_lang=task.source_lang,
        target_lang=task.target_lang,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        error_message=task.error_message,
        transcript=task.transcript,
        translated_transcript=task.translated_transcript,
        segments=_build_segments(task),
        stt_metadata=task.stt_metadata,
        num_beams=task.num_beams,
        english_ratio_threshold=task.english_ratio_threshold,
        combined_audio_key=task.combined_audio_key,
        original_audio_url=original_audio_url,
        original_video_url=original_video_url,
        combined_audio_url=combined_audio_url,
        dubbed_video_url=dubbed_video_url,
    )
