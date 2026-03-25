from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.jobs.models import JobStatus, JobType


class JobBase(BaseModel):
    video_id: Optional[str] = None
    user_id: int
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    input_data: Optional[dict[str, Any]] = None

    @field_validator("video_id", mode="before")
    @classmethod
    def coerce_video_id(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    progress: Optional[float] = None
    celery_task_id: Optional[str] = None
    output_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobProgressUpdate(BaseModel):
    """Payload accepted by PATCH /api/jobs/{id}/progress (called by workers)."""

    progress: float
    status: Optional[JobStatus] = None
    error_message: Optional[str] = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    user_id: int
    job_type: JobType
    status: JobStatus
    progress: float
    celery_task_id: Optional[str] = None
    parent_job_id: Optional[str] = None
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
