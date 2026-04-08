import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SQLEnum
from app.core.db import Base


class JobType(str, enum.Enum):
    VIDEO_PROCESS = "VIDEO_PROCESS"
    VIDEO_HLS = "VIDEO_HLS"
    STT_TRANSCRIBE = "STT_TRANSCRIBE"
    NMT_TRANSLATE = "NMT_TRANSLATE"
    TTS_SYNTHESIZE = "TTS_SYNTHESIZE"
    DUBBING_MERGE = "DUBBING_MERGE"
    FULL_DUBBING_PIPELINE = "FULL_DUBBING_PIPELINE"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[JobType] = mapped_column(
        SQLEnum(JobType, name="jobtype"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="jobstatus"),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_job_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Progressive tracking columns
    segments_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    segments_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merge_timeline: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Job id={self.id} type={self.job_type} status={self.status}>"
