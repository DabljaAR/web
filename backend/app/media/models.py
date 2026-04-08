import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Boolean, Enum as SQLEnum, Float, BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base

class VideoStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class MediaType(str, enum.Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    TEXT = "TEXT"

class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    
    media_type: Mapped[MediaType] = mapped_column(SQLEnum(MediaType), default=MediaType.VIDEO, nullable=False)
    
    file_path: Mapped[str] = mapped_column(String(512), nullable=False) # Path or key
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    dubbed_video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Dubbed video output
    
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # e.g. "mp4", "mov"
    codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # e.g. "h264"
    frame_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[VideoStatus] = mapped_column(SQLEnum(VideoStatus), default=VideoStatus.PENDING, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dubbing_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Dubbing merge metadata

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped["User"] = relationship("User", back_populates="videos")


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url = None
        self.thumbnail_url = None
        self.audio_url = None

    def __repr__(self):
        return f"<Video {self.title} status={self.status}>"
