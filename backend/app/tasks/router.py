"""VideoTask API router.

Endpoints:
  GET /api/tasks/video/{video_id}   — list all tasks for a video (newest first)
  GET /api/tasks/{task_id}          — get one task with full output
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import User
from app.tasks.models import VideoTask, TaskStatus

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SegmentOut(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    tts_key: Optional[str] = None
    audio_url: Optional[str] = None

    class Config:
        from_attributes = True


class VideoTaskSummary(BaseModel):
    id: str
    video_id: str
    output_type: str
    source_lang: Optional[str]
    target_lang: str
    status: TaskStatus
    progress: float
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class VideoTaskDetail(VideoTaskSummary):
    transcript: Optional[str]
    translated_transcript: Optional[str]
    segments: Optional[list]
    stt_metadata: Optional[dict]
    num_beams: int
    english_ratio_threshold: float
    error_message: Optional[str]
    started_at: Optional[datetime]
    root_job_id: Optional[str]
    combined_audio_key: Optional[str] = None
    # Presigned URLs injected at request time
    original_audio_url: Optional[str] = None
    combined_audio_url: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/video/{video_id}", response_model=List[VideoTaskSummary])
async def list_tasks_for_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[VideoTaskSummary]:
    """Return all tasks for a video, newest first."""
    result = await db.execute(
        select(VideoTask)
        .where(VideoTask.video_id == video_id, VideoTask.user_id == current_user.user_id)
        .order_by(VideoTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return tasks


@router.get("/{task_id}", response_model=VideoTaskDetail)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoTaskDetail:
    """Return a single task with full output data including presigned audio URLs."""
    task = await db.get(VideoTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    original_audio_url: Optional[str] = None
    combined_audio_url: Optional[str] = None

    try:
        from app.media.storage import get_storage_service
        from app.media.models import Video
        storage = get_storage_service()

        # Original audio: use the video's audio_path (or file_path as fallback)
        video = await db.get(Video, task.video_id)
        if video:
            audio_key = video.audio_path or video.file_path
            if audio_key:
                original_audio_url = await storage.get_url(audio_key)

        # Combined TTS audio
        if task.combined_audio_key:
            combined_audio_url = await storage.get_url(task.combined_audio_key)
    except Exception:
        pass  # audio URLs are best-effort; don't fail the request

    detail = VideoTaskDetail.model_validate(task)
    detail.original_audio_url = original_audio_url
    detail.combined_audio_url = combined_audio_url
    return detail
