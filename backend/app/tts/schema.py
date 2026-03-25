"""
Pydantic models for TTS API schema validation and documentation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ArabicDialect(str, Enum):
    MSA = "MSA"
    EGY = "EGY"


# ==================== REQUEST MODELS ====================

class TTSRequest(BaseModel):
    """Request model for TTS synthesis."""
    
    text: str = Field(..., description="Arabic text to synthesize")
    dialect: ArabicDialect = Field(
        default=ArabicDialect.MSA,
        description="Arabic dialect (MSA or EGY)"
    )
    ref_audio_path: Optional[str] = Field(
        default=None,
        description="Path to reference audio for voice cloning"
    )
    ref_text: Optional[str] = Field(
        default=None,
        description="Transcript of the reference audio"
    )
    speed: Optional[float] = Field(
        default=None,
        description="Speech rate (1.0 = normal)"
    )
    cfg_strength: Optional[float] = Field(
        default=None,
        description="Classifier-free guidance strength"
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job ID for tracking"
    )
    upload_to_minio: bool = Field(
        default=False,
        description="Whether to upload the result to MinIO and return a downloadable URL"
    )
    minio_key: Optional[str] = Field(
        default=None,
        description="Custom MinIO key (e.g. 'tts/my-audio.wav'). If not provided, auto-generates."
    )
    
    class Config:
        schema_extra = {
            "example": {
                "text": "مرحباً بكم في منصة دبلجة عربية",
                "dialect": "MSA",
                "speed": 0.8,
                "upload_to_minio": True
            }
        }


class TTSJobRequest(BaseModel):
    """Request model for TTS job with video_id."""
    
    video_id: int = Field(..., description="Video ID to synthesize audio for")
    dialect: ArabicDialect = Field(
        default=ArabicDialect.MSA,
        description="Arabic dialect"
    )
    target_lang: str = Field(
        default="arb_Arab",
        description="Target language code"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "video_id": 123,
                "dialect": "MSA",
                "target_lang": "arb_Arab"
            }
        }


# ==================== RESPONSE MODELS ====================

class TTSResponse(BaseModel):
    """Response for TTS synthesis."""
    
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(default="queued", description="Task status")
    
    class Config:
        schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "queued"
            }
        }


class TTSJobResponse(BaseModel):
    """Response for TTS job status."""
    
    job_id: str = Field(..., description="Job ID")
    status: str = Field(..., description="Job status")
    video_id: Optional[int] = Field(default=None, description="Video ID")
    dialect: Optional[str] = Field(default=None, description="Dialect used")
    output_key: Optional[str] = Field(default=None, description="MinIO key for output audio")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: Optional[str] = Field(default=None, description="Job creation time")
    completed_at: Optional[str] = Field(default=None, description="Job completion time")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "video_id": 123,
                "dialect": "MSA",
                "output_key": "tts/123/audio.wav"
            }
        }


class TTSStatusResponse(BaseModel):
    """Response for checking TTS task status."""
    
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status (pending/processing/success/failed)")
    result: Optional[dict] = Field(
        default=None,
        description="TTS result (only if status is success)"
    )
    info: Optional[str] = Field(
        default=None,
        description="Additional info"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "success",
                "result": {
                    "status": "success",
                    "dialect": "MSA",
                    "bytes_size": 12345
                }
            }
        }


# ==================== ERROR MODELS ====================

class TTSErrorResponse(BaseModel):
    """Standard TTS error response."""
    
    status: str = Field(default="error", description="Status indicator")
    error: str = Field(..., description="Error type or message")
    detail: Optional[str] = Field(default=None, description="Additional error details")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "error",
                "error": "Synthesis failed",
                "detail": "Model not loaded"
            }
        }


# ==================== HEALTH CHECK MODEL ====================

class TTSHealthResponse(BaseModel):
    """TTS health check response."""
    
    status: str = Field(default="healthy", description="API status")
    model_loaded: bool = Field(..., description="Whether model is loaded")
    device: str = Field(..., description="Device in use (cuda/cpu)")
    dialect: str = Field(default="MSA", description="Available dialect")
    version: str = Field(default="1.0.0", description="API version")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "model_loaded": True,
                "device": "cpu",
                "dialect": "MSA",
                "version": "1.0.0"
            }
        }