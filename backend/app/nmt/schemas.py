from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class STTMetadata(BaseModel):
    language: str
    duration: float
    model_size: Optional[str] = None
    device: Optional[str] = None
    processing_time: Optional[float] = None
    segment_count: Optional[int] = None

class STTSegment(BaseModel):
    start: float
    end: float
    text: str

class STTResult(BaseModel):
    transcript: str
    segments: List[STTSegment]
    metadata: STTMetadata

class NMTTranslateSTTRequest(BaseModel):
    stt_data: STTResult
    target_lang: str = Field(default="arb_Arab")
    source_lang: Optional[str] = None

class NMTTranslateSTTResponse(BaseModel):
    stt_data: STTResult
    target_lang: str
