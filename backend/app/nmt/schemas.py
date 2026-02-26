from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.nmt.models import TranslationStatus

class TranslationBase(BaseModel):
    video_id: Optional[str] = None
    target_lang: str # e.g. "arb_Arab"
    source_lang: Optional[str] = None # e.g. "eng_Latn", if None, will auto-detect

class TranslationResponse(TranslationBase):
    id: str
    user_id: int
    source_text_path: str
    translated_text_path: Optional[str] = None
    status: TranslationStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # URLs for the files (populated in service/router)
    source_url: Optional[str] = None
    translated_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
