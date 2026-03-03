import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.nmt.service import TranslationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nmt"])

@router.post("/nmt/translate-stt", response_model=dict)
async def translate_stt(
    stt_data: dict,
    target_lang: str = "arb_Arab",
    source_lang: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    # current_user = Depends(get_current_user)
):
    """
    Translates a structured STT result (transcript and segments).
    Returns the same structure with translated text.
    """
    # 1. Handle the structure { "stt_data": { ... }, "target_lang": "..." }
    # extracting stt_data from the payload if it's nested
    data_to_translate = stt_data.get("stt_data", stt_data)
    
    # 2. Extract target_lang from payload if not provided via query param
    final_target = target_lang
    if not target_lang or target_lang == "arb_Arab": # Default value
        payload_target = stt_data.get("target_lang")
        if payload_target:
            final_target = payload_target

    service = TranslationService(db)
    try:
        # We pass target_lang and source_lang to the service
        result = await service.translate_stt_result(data_to_translate, final_target, source_lang)
        
        # Return in the original requested structure if it was nested
        if "stt_data" in stt_data:
            return {
                "stt_data": result,
                "target_lang": final_target
            }
        return result
    except Exception as e:
        logger.error(f"TRANSLATE STT FAILED: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

