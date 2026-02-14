from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.media.models import VideoStatus, MediaType

class VideoBase(BaseModel):
    title: str

class VideoCreate(VideoBase):
    pass

class VideoUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[VideoStatus] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class VideoUploadResponse(BaseModel):
    id: str
    message: str = "The media is being processed"
    status: VideoStatus
    
    model_config = ConfigDict(from_attributes=True)

class VideoResponse(VideoBase):
    id: str
    user_id: int
    original_filename: str
    file_path: str
    thumbnail_path: Optional[str] = None
    audio_path: Optional[str] = None
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
    
    url: Optional[str] = None # Added for convenience to return full URL
    thumbnail_url: Optional[str] = None
    audio_url: Optional[str] = None

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
    active: List[VideoResponse]
    recent: List[VideoResponse]
