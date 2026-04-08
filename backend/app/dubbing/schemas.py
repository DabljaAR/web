"""Pydantic schemas for dubbing merge service."""
from typing import List, Optional
from pydantic import BaseModel, Field


class SegmentTimingInfo(BaseModel):
    """Timing information for a single segment."""
    segment_id: int = Field(..., description="Segment index")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Segment duration in seconds")
    original_text: str = Field(..., description="Original text")
    translated_text: str = Field(..., description="Translated text")
    tts_audio_key: Optional[str] = Field(None, description="MinIO key for TTS audio")
    tts_duration: Optional[float] = Field(None, description="TTS audio duration in seconds")
    stretch_factor: Optional[float] = Field(None, description="Applied time-stretch factor (1.0 = no stretch)")
    gap_after: Optional[float] = Field(None, description="Silence gap after this segment in seconds")


class DubbingMergeRequest(BaseModel):
    """Request parameters for dubbing merge."""
    video_id: str = Field(..., description="Video ID to process")
    segments: List[SegmentTimingInfo] = Field(..., description="List of segment timing info")
    output_key: Optional[str] = Field(None, description="Output video key in MinIO (auto-generated if None)")
    max_stretch_ratio: Optional[float] = Field(None, description="Maximum stretch ratio (defaults to config)")
    min_stretch_ratio: Optional[float] = Field(None, description="Minimum stretch ratio (defaults to config)")


class TimingWarning(BaseModel):
    """Warning about timing mismatch."""
    segment_id: int
    message: str
    stretch_factor: float
    duration_mismatch_percent: float


class DubbingMergeResponse(BaseModel):
    """Response from dubbing merge operation."""
    job_id: str = Field(..., description="Job ID")
    video_id: str = Field(..., description="Video ID")
    output_key: str = Field(..., description="MinIO key for dubbed video")
    output_url: Optional[str] = Field(None, description="Presigned URL for dubbed video")
    
    metadata: dict = Field(default_factory=dict, description="Processing metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "video_id": "video-abc",
                "output_key": "videos/video-abc/dubbed/1234567890.mp4",
                "output_url": "https://minio.../videos/video-abc/dubbed/1234567890.mp4",
                "metadata": {
                    "total_segments": 42,
                    "segments_stretched": 15,
                    "avg_stretch_factor": 1.08,
                    "warnings": ["Segment 5: 22% mismatch, trimmed excess"],
                    "processing_time": 23.4
                }
            }
        }


class FullPipelineResponse(BaseModel):
    """Response from full dubbing pipeline initiation."""
    job_id: str = Field(..., description="Job ID for tracking pipeline progress")
    video_id: str = Field(..., description="Video ID being processed")
    status: str = Field(..., description="Initial job status (typically 'queued')")
    message: str = Field(..., description="Human-readable status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-456def",
                "video_id": "video-789abc",
                "status": "queued",
                "message": "Full dubbing pipeline started successfully"
            }
        }


class PipelineJobStatusResponse(BaseModel):
    """Response for pipeline job status query."""
    job_id: str = Field(..., description="Job ID")
    video_id: Optional[str] = Field(None, description="Video ID (if available)")
    status: str = Field(..., description="Job status: queued, processing, completed, failed, retrying, cancelled")
    progress: Optional[dict] = Field(None, description="Progress information with percent completion")
    result: Optional[dict] = Field(None, description="Full pipeline output when completed (transcript, segments, metadata)")
    error: Optional[str] = Field(None, description="Error message if status is failed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-456def",
                "video_id": "video-789abc",
                "status": "processing",
                "progress": {"percent": 45.0, "stage": "nmt"},
                "result": None,
                "error": None
            }
        }


class DubbedVideoResponse(BaseModel):
    """Response for dubbed video retrieval."""
    video_id: str = Field(..., description="Video ID")
    dubbed_video_url: str = Field(..., description="Presigned URL for the dubbed video")
    created_at: str = Field(..., description="ISO 8601 timestamp when dubbing completed")
    metadata: dict = Field(default_factory=dict, description="Video and dubbing metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "video_id": "video-789abc",
                "dubbed_video_url": "https://minio.example.com/videos/video-789abc/dubbed/final.mp4?expires=...",
                "created_at": "2026-03-26T14:30:00Z",
                "metadata": {
                    "duration": 120.5,
                    "source_language": "en",
                    "target_language": "arb_Arab",
                    "total_segments": 42,
                    "processing_time": 45.2
                }
            }
        }
