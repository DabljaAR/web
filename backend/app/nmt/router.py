import logging
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
