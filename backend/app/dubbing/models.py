"""Optional Pydantic models for dubbing merge (mainly for internal use)."""
from typing import Optional
from pydantic import BaseModel, Field


class SegmentTiming(BaseModel):
    """Internal timing information for a segment during processing."""
    segment_id: int
    start: float
    end: float
    duration: float
    tts_duration: Optional[float] = None
    stretch_factor: float = 1.0
    gap_after: float = 0.0


class DubbingOutput(BaseModel):
    """Result metadata from dubbing merge operation."""
    output_key: str = Field(..., description="MinIO key for dubbed video")
    output_url: Optional[str] = Field(None, description="Presigned URL")
    total_segments: int = Field(..., description="Number of segments processed")
    segments_stretched: int = Field(..., description="Number of segments that required stretching")
    avg_stretch_factor: float = Field(..., description="Average stretch factor applied")
    warnings: list[str] = Field(default_factory=list, description="List of warnings")
    processing_time: float = Field(..., description="Total processing time in seconds")
