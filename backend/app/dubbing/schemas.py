"""Schemas for dubbing merge workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SegmentTimingInfo(BaseModel):
    segment_id: int = Field(..., ge=0)
    start: float = Field(..., ge=0.0)
    end: float = Field(..., ge=0.0)
    duration: float = Field(..., ge=0.0)
    original_text: str = ""
    translated_text: str = ""
    tts_audio_key: Optional[str] = None
    tts_duration: Optional[float] = None
    stretch_factor: Optional[float] = None
    gap_after: Optional[float] = None


class DubbingMergeRequest(BaseModel):
    video_id: str
    segments: List[SegmentTimingInfo]
    output_key: Optional[str] = None
    max_stretch_ratio: float = 1.2
    min_stretch_ratio: float = 0.8


class TimingWarning(BaseModel):
    segment_id: int
    message: str
    mismatch_percent: float


class DubbingMergeResponse(BaseModel):
    job_id: str
    video_id: str
    output_key: Optional[str] = None
    output_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FullPipelineResponse(BaseModel):
    job_id: str
    video_id: str
    status: str
    message: str


class PipelineJobStatusResponse(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: str
    progress: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DubbedVideoResponse(BaseModel):
    video_id: str
    dubbed_video_url: str
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
