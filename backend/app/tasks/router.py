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
    """Return a single task with full output data."""
    task = await db.get(VideoTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return task
