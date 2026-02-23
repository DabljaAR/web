import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import get_current_user
from app.nmt.schemas import TranslationCreate, TranslationResponse, DirectTranslationCreate
from app.nmt.service import TranslationService
from app.media.storage import get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nmt"])

@router.get("/nmt/queue-status")
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Check how many jobs are currently in the queue."""
    service = TranslationService(db)
    return await service.get_queue_stats()

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

@router.post("/nmt/translate-script", response_model=TranslationResponse)
async def translate_script(
    request: DirectTranslationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    logger.info(f"TRANSLATE SCRIPT REQUEST: user={current_user.user_id}, target={request.target_lang}")
    service = TranslationService(db)
    try:
        job = await service.create_direct_job(
            text=request.text,
            user_id=current_user.user_id,
            target_lang=request.target_lang,
            background_tasks=background_tasks,
            source_lang=request.source_lang
        )
        logger.info(f"TRANSLATE SCRIPT JOB CREATED: {job.id}")
        return job
    except Exception as e:
        logger.error(f"TRANSLATE SCRIPT FAILED: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/videos/{video_id}/translate", response_model=TranslationResponse)
async def create_translation_job(
    video_id: str,
    target_lang: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = TranslationService(db)
    try:
        job = await service.create_job(
            video_id=video_id,
            user_id=current_user.user_id,
            target_lang=target_lang,
            background_tasks=background_tasks
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/nmt/jobs/{job_id}", response_model=TranslationResponse)
async def get_translation_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = TranslationService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Populate URLs
    storage = get_storage_service()
    if job.source_text_path:
        job.source_url = await storage.get_url(job.source_text_path)
    if job.translated_text_path:
        job.translated_url = await storage.get_url(job.translated_text_path)
        
    return job

@router.get("/videos/{video_id}/translations", response_model=List[TranslationResponse])
async def get_video_translations(
    video_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = TranslationService(db)
    translations = await service.get_video_translations(video_id)
    
    storage = get_storage_service()
    for job in translations:
        if job.source_text_path:
            job.source_url = await storage.get_url(job.source_text_path)
        if job.translated_text_path:
            job.translated_url = await storage.get_url(job.translated_text_path)
            
    return translations
