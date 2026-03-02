import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.nmt.schemas import TranslationResponse
from app.nmt.service import TranslationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nmt"])

@router.post("/nmt/translate-file", response_model=TranslationResponse)
async def translate_file(
    background_tasks: BackgroundTasks,
    target_lang: str = Form(...),
    source_lang: str = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    logger.info(f"TRANSLATE FILE REQUEST: user={current_user.user_id}, target={target_lang}, filename={file.filename}")
    
    try:
        # Read file content
        content = await file.read()
        
        # Try decoding with several common encodings
        text = None
        for encoding in ["utf-8", "utf-8-sig", "windows-1256", "cp1252", "latin-1"]:
            try:
                text = content.decode(encoding)
                logger.info(f"Successfully decoded file using {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if text is None:
            # Last resort fallback: decode with replacement for bad characters
            text = content.decode("utf-8", errors="replace")
            logger.warning("File decoding failed all standard encodings. Used 'utf-8' with replacement characters.")
            
    except Exception as e:
        logger.error(f"FILE READ ERROR: {e}")
        raise HTTPException(status_code=400, detail=f"Could not read file: {str(e)}")

    service = TranslationService(db)
    try:
        job = await service.create_direct_job(
            text=text,
            user_id=current_user.user_id,
            target_lang=target_lang,
            background_tasks=background_tasks,
            source_lang=source_lang
        )
        logger.info(f"TRANSLATE FILE JOB CREATED: {job.id}")
        return job
    except Exception as e:
        logger.error(f"TRANSLATE FILE FAILED: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/nmt/translate-stt", response_model=dict)
async def translate_stt(
    stt_data: dict,
    target_lang: str = "arb_Arab",
    source_lang: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
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

