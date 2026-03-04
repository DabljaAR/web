import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.nmt.service import TranslationService
from app.nmt.schemas import NMTTranslateSTTRequest, NMTTranslateSTTResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nmt"])

@router.post("/nmt", response_model=NMTTranslateSTTResponse)
async def translate_stt(
    request: NMTTranslateSTTRequest,
    db: AsyncSession = Depends(get_db),
    # current_user = Depends(get_current_user)
):
    """
    Translates a structured STT result (transcript and segments) using NMT.
    Input structure and output structure are strictly defined by NMTTranslateSTTRequest/Response.
    """
    service = TranslationService(db)
    
    try:
        # Pass the dictionary data to the service
        translated_stt = await service.translate_stt_result(
            request.stt_data.model_dump(),
            request.target_lang,
            request.source_lang
        )
        
        return NMTTranslateSTTResponse(
            stt_data=translated_stt,
            target_lang=request.target_lang
        )
    except Exception as e:
        logger.error(f"TRANSLATE STT FAILED: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

