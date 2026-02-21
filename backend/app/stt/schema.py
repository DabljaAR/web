"""
Pydantic models for STT API schema validation and documentation.
Location: sst/schema.py
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum
from app.shared.enums import languageEnum



# ==================== REQUEST MODELS ====================

class TranscriptionRequest(BaseModel):
    """Request model for transcription (file upload handled separately)."""
    
    language: Optional[languageEnum] = Field(
        default=None,
        description="Language of the audio. If None, auto-detected."
    )
    
    class Config:
        schema_extra = {
            "example": {
                "language": "en"
            }
        }


class TranscriptionAsyncRequest(BaseModel):
    """Request model for async transcription."""
    
    language: Optional[languageEnum] = Field(
        default=None,
        description="Language of the audio"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "language": "en"
            }
        }


# ==================== RESPONSE MODELS ====================

class TranscriptionSegment(BaseModel):
    """Individual transcription segment with timestamps."""
    
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text for this segment")
    
    class Config:
        schema_extra = {
            "example": {
                "start": 0.0,
                "end": 2.5,
                "text": "Welcome to this presentation."
            }
        }


class TranscriptionMetadata(BaseModel):
    """Metadata about the transcription."""
    
    language: str = Field(..., description="Detected/used language code")
    duration: float = Field(..., description="Audio duration in seconds")
    model_size: str = Field(..., description="Model size used (tiny/small/medium/large)")
    device: str = Field(..., description="Device used (cuda/cpu)")
    processing_time: float = Field(..., description="Transcription processing time in seconds")
    segment_count: int = Field(..., description="Number of segments")
    
    class Config:
        schema_extra = {
            "example": {
                "language": "en",
                "duration": 125.5,
                "model_size": "medium",
                "device": "cuda",
                "processing_time": 15.3,
                "segment_count": 8
            }
        }


class TranscriptionResponse(BaseModel):
    """Successful transcription response."""
    
    transcript: str = Field(..., description="Full transcribed text")
    segments: List[TranscriptionSegment] = Field(..., description="Timestamped segments")
    metadata: TranscriptionMetadata = Field(..., description="Transcription metadata")
    
    class Config:
        schema_extra = {
            "example": {
                "transcript": "Welcome to this presentation. Today we will discuss...",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 2.5,
                        "text": "Welcome to this presentation."
                    },
                    {
                        "start": 2.5,
                        "end": 5.0,
                        "text": "Today we will discuss..."
                    }
                ],
                "metadata": {
                    "language": "en",
                    "duration": 125.5,
                    "model_size": "medium",
                    "device": "cuda",
                    "processing_time": 15.3,
                    "segment_count": 2
                }
            }
        }


# ==================== ASYNC JOB MODELS ====================

class AsyncJobResponse(BaseModel):
    """Response for async job submission."""
    
    task_id: str = Field(..., description="Unique task ID for polling")
    status: str = Field(default="queued", description="Job status (queued/processing/success/failed)")
    message: str = Field(..., description="Status message")
    
    class Config:
        schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "queued",
                "message": "Job submitted. Check status at /status/550e8400-e29b-41d4-a716-446655440000"
            }
        }


class JobStatusResponse(BaseModel):
    """Response for checking async job status."""
    
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Job status (pending/processing/success/failed)")
    result: Optional[TranscriptionResponse] = Field(
        default=None,
        description="Transcription result (only if status is success)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message (only if status is failed)"
    )
    progress: Optional[dict] = Field(
        default=None,
        description="Progress info (only if status is processing)"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "success",
                "result": {
                    "transcript": "Welcome to this presentation...",
                    "segments": [],
                    "metadata": {}
                }
            }
        }


# ==================== METRICS MODEL ====================

class MetricsResponse(BaseModel):
    """API performance metrics."""
    
    total_requests: int = Field(..., description="Total transcription requests")
    successful_transcriptions: int = Field(..., description="Successfully completed")
    failed_transcriptions: int = Field(..., description="Failed transcriptions")
    avg_processing_time: float = Field(..., description="Average processing time in seconds")
    device: str = Field(..., description="Device (cuda/cpu)")
    model_size: str = Field(..., description="Model size")
    is_transcribing: bool = Field(..., description="Currently processing a file")
    
    success_rate: Optional[float] = Field(
        default=None,
        description="Success rate percentage"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "total_requests": 42,
                "successful_transcriptions": 40,
                "failed_transcriptions": 2,
                "avg_processing_time": 18.5,
                "device": "cuda",
                "model_size": "medium",
                "is_transcribing": False,
                "success_rate": 95.2
            }
        }


# ==================== ERROR MODELS ====================

class ErrorResponse(BaseModel):
    """Standard error response."""
    
    status: str = Field(default="error", description="Status indicator")
    error: str = Field(..., description="Error type or message")
    detail: Optional[str] = Field(default=None, description="Additional error details")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "error",
                "error": "File not found",
                "detail": "Audio file not found at /path/to/audio.mp4"
            }
        }


class ValidationErrorResponse(BaseModel):
    """Validation error response."""
    
    status: str = Field(default="error", description="Status indicator")
    error: str = Field(default="Validation error", description="Error type")
    details: List[dict] = Field(..., description="List of validation errors")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "error",
                "error": "Validation error",
                "details": [
                    {
                        "field": "language",
                        "message": "Invalid language code"
                    }
                ]
            }
        }


# ==================== HEALTH CHECK MODEL ====================

class HealthCheckResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(default="healthy", description="API status")
    model_loaded: bool = Field(..., description="Whether model is loaded")
    device: str = Field(..., description="Device in use (cuda/cpu)")
    version: str = Field(default="1.0.0", description="API version")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "model_loaded": True,
                "device": "cuda",
                "version": "1.0.0"
            }
        }