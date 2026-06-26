"""Pydantic models for STT API responses."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List


class TranscriptionSegment(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text for this segment")


class TranscriptionMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: str = Field(..., description="Detected/used language code")
    duration: float = Field(..., description="Audio duration in seconds")
    model_size: str = Field(..., description="Model size used (tiny/small/medium/large)")
    device: str = Field(..., description="Device used (cuda/cpu)")
    compute_type: Optional[str] = Field(default=None, description="Compute type (float16/int8/…)")
    processing_time: float = Field(..., description="Transcription processing time in seconds")
    segment_count: int = Field(..., description="Number of segments")


class TranscriptionResponse(BaseModel):
    transcript: str = Field(..., description="Full transcribed text")
    segments: List[TranscriptionSegment] = Field(..., description="Timestamped segments")
    metadata: TranscriptionMetadata = Field(..., description="Transcription metadata")


class AsyncJobResponse(BaseModel):
    task_id: str = Field(..., description="Job ID for polling via /api/jobs/{task_id}")
    status: str = Field(default="queued", description="Job status")
    message: str = Field(..., description="Status message")
