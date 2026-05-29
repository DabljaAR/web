from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class VideoStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MediaType(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    TEXT = "TEXT"


class VideoUploadResponse(BaseModel):
    id: str
    message: str = "The media is being processed"
    status: VideoStatus

    model_config = ConfigDict(from_attributes=True)


class VideoResponse(BaseModel):
    id: str
    user_id: int
    title: str
    original_filename: str
    file_path: str
    thumbnail_path: Optional[str] = None
    audio_path: Optional[str] = None
    dubbed_video_path: Optional[str] = None
    dubbing_metadata: Optional[dict] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    format: Optional[str] = None
    codec: Optional[str] = None
    frame_rate: Optional[float] = None
    media_type: MediaType
    status: VideoStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    audio_url: Optional[str] = None
    dubbed_video_url: Optional[str] = None
    transcript_url: Optional[str] = None
    translation_url: Optional[str] = None
    has_active_job: Optional[bool] = None
    active_job_status: Optional[str] = None
    active_job_progress: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedVideoResponse(BaseModel):
    items: List[VideoResponse]
    total: int
    page: int
    size: int
    pages: int
    total_completed: int
    total_failed: int


class DashboardResponse(BaseModel):
    active: List[dict]
    recent: List[dict]

