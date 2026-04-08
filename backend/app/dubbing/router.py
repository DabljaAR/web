"""
FastAPI router for Dubbing Pipeline endpoints.

Endpoints:
  POST /api/dubbing/full-pipeline     - Trigger full STT → NMT → TTS → Merge pipeline
  GET  /api/dubbing/jobs/{job_id}     - Get job status and results
  GET  /api/dubbing/videos/{video_id}/dubbed - Get dubbed video URL
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.core.db import get_db
from app.core.auth import get_current_user, get_current_active_user
from app.core.models import User
from app.jobs.models import Job, JobType, JobStatus
from app.media.models import Video, VideoStatus
from app.media.storage import get_storage_service
from app.dubbing.schemas import (
    FullPipelineResponse,
    PipelineJobStatusResponse,
    DubbedVideoResponse,
)
from app.jobs.tasks.pipeline import dispatch_full_dubbing_pipeline


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dubbing",
    tags=["dubbing"],
    responses={
        400: {"description": "Bad request"},
        403: {"description": "Access denied"},
        404: {"description": "Resource not found"},
        500: {"description": "Server error"},
    },
)


# ===========================================================================
# POST /api/dubbing/full-pipeline — Trigger full dubbing pipeline
# ===========================================================================

@router.post(
    "/full-pipeline",
    response_model=FullPipelineResponse,
    summary="Start full dubbing pipeline",
    description="""
Trigger the complete dubbing pipeline for a video:
1. STT (Speech-to-Text) transcription
2. NMT (Neural Machine Translation) of segments
3. TTS (Text-to-Speech) synthesis
4. Dubbing merge (replace audio with synthesized speech)

**Requirements:**
- Video must be uploaded and fully processed (status = COMPLETED)
- Video must have extracted audio_path

**Returns:**
- job_id: Track progress at GET /api/dubbing/jobs/{job_id}
- status: Initial job status (queued)
""",
)
async def start_full_pipeline(
    video_id: str = Query(..., description="UUID of the video to dub"),
    source_lang: str = Query(default="auto", description="Source language (ISO-639-1 code or 'auto' for detection)"),
    target_lang: str = Query(default="arb_Arab", description="Target language (e.g., 'arb_Arab' for Arabic MSA)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start the full dubbing pipeline for a video."""
    
    # 1. Validate video exists and belongs to user
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.user_id)
    )
    video = result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(
            status_code=404,
            detail=f"Video {video_id} not found or access denied."
        )
    
    # 2. Verify video is fully processed
    if video.status != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail=f"Video must be fully processed before dubbing. Current status: {video.status}"
        )
    
    if not video.audio_path:
        raise HTTPException(
            status_code=400,
            detail="Video has no extracted audio. Upload a video with audio or wait for processing to complete."
        )
    
    # 3. Create Job record
    import uuid
    job_id = str(uuid.uuid4())
    
    job = Job(
        id=job_id,
        video_id=video_id,
        user_id=current_user.user_id,
        job_type=JobType.FULL_DUBBING_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0.0,
        input_data={
            "video_id": video_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "audio_path": video.audio_path,
        },
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(
        f"[DUBBING] Created job {job_id} for video {video_id} "
        f"(user={current_user.user_id}, {source_lang} → {target_lang})"
    )
    
    # 4. Dispatch Celery pipeline
    try:
        dispatch_full_dubbing_pipeline(
            job_id=job_id,
            video_id=video_id,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        logger.info(f"[DUBBING] Pipeline dispatched for job {job_id}")
    except Exception as exc:
        logger.error(f"[DUBBING] Failed to dispatch pipeline for job {job_id}: {exc}")
        job.status = JobStatus.FAILED
        job.error_message = f"Failed to dispatch pipeline: {str(exc)}"
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to start dubbing pipeline.")
    
    return FullPipelineResponse(
        job_id=job_id,
        video_id=video_id,
        status=JobStatus.QUEUED.value.lower(),
        message=f"Full dubbing pipeline queued. Poll status at /api/dubbing/jobs/{job_id}",
    )


# ===========================================================================
# POST /api/dubbing/progressive-pipeline — Progressive real-time dubbing
# ===========================================================================

@router.post(
    "/progressive-pipeline", 
    response_model=FullPipelineResponse,
    summary="Start progressive real-time dubbing pipeline",
    description="Initiates progressive dubbing with real-time video building as segments complete. Connect to WebSocket for live progress updates."
)
async def progressive_dubbing_pipeline(
    video_id: str = Query(..., description="UUID of the video to dub"),
    source_lang: str = Query(default="auto", description="Source language (ISO-639-1 code or 'auto' for detection)"),
    target_lang: str = Query(default="arb_Arab", description="Target language (e.g., 'arb_Arab' for Arabic MSA)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Progressive dubbing pipeline with real-time video building.
    
    Unlike the standard pipeline that waits for all segments to complete before merging,
    this progressive pipeline:
    1. Builds video progressively as each segment completes TTS
    2. Provides real-time preview URLs via WebSocket
    3. Delivers final video 10x faster than batch processing
    
    Connect to WebSocket at /ws/progressive/{job_id} for live updates.
    """
    
    video_id = video_id
    source_lang = source_lang
    target_lang = target_lang
    
    logger.info(f"[PROGRESSIVE-DUBBING] Starting progressive pipeline | video_id={video_id} | source_lang={source_lang} | target_lang={target_lang}")
    
    # 1. Verify video exists and user owns it
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found.")
    
    if video.user_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only process your own videos."
        )
    
    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Video must be processed before dubbing. Current status: {video.status}"
        )
    
    # 2. Create job record
    job_id = str(uuid4())
    job = Job(
        id=job_id,
        video_id=video_id,
        user_id=current_user.user_id,
        job_type=JobType.FULL_DUBBING_PIPELINE,
        status=JobStatus.QUEUED,
        input_data={
            "video_id": video_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "mode": "progressive",
            "created_by": current_user.username,
        }
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(f"[PROGRESSIVE-DUBBING] Job created | job_id={job_id} | video_id={video_id}")
    
    # 3. Dispatch progressive STT task
    try:
        from app.jobs.tasks.pipeline import stt_transcribe_progressive
        
        # Start progressive pipeline
        task_result = stt_transcribe_progressive.apply_async(
            kwargs={
                "job_id": job_id,
                "video_id": video_id,
                "language": source_lang,
                "target_lang": target_lang,
            },
            queue="ai_stt",
        )
        
        # Update job with Celery task ID
        job.celery_task_id = task_result.id
        await db.commit()
        
        logger.info(f"[PROGRESSIVE-DUBBING] Progressive STT task dispatched | job_id={job_id} | task_id={task_result.id}")
        
    except Exception as exc:
        logger.error(f"[PROGRESSIVE-DUBBING] Failed to dispatch progressive pipeline for job {job_id}: {exc}")
        job.status = JobStatus.FAILED
        job.error_message = f"Failed to dispatch progressive pipeline: {str(exc)}"
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to start progressive dubbing pipeline.")
    
    return FullPipelineResponse(
        job_id=job_id,
        video_id=video_id,
        status=JobStatus.QUEUED.value.lower(),
        message=f"Progressive dubbing pipeline started. Connect to WebSocket /ws/progressive/{job_id} for real-time updates.",
    )


# ===========================================================================
# GET /api/dubbing/jobs/{job_id} — Get job status
# ===========================================================================

@router.get(
    "/jobs/{job_id}",
    response_model=PipelineJobStatusResponse,
    summary="Get pipeline job status",
    description="""
Check the status of a dubbing pipeline job.

**Status values:**
- queued: Job is waiting in the queue
- processing: Job is currently running
- completed: Job finished successfully (result available)
- failed: Job failed (error message available)
- retrying: Job is retrying after a failure
- cancelled: Job was cancelled by user

**Progress:**
When status is 'processing', progress includes:
- percent: Completion percentage (0-100)
- stage: Current pipeline stage (stt, nmt, tts, merge)
""",
)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a dubbing pipeline job."""
    
    # Get job from database
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    
    # Verify user owns this job
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    
    # Build progress info
    progress = None
    if job.progress is not None:
        progress = {"percent": job.progress}
        # Add stage info if available in input_data
        if job.input_data and "current_stage" in job.input_data:
            progress["stage"] = job.input_data["current_stage"]
    
    # Build result (only for completed jobs)
    result_data = None
    if job.status == JobStatus.COMPLETED and job.output_data:
        result_data = job.output_data
    
    return PipelineJobStatusResponse(
        job_id=job.id,
        video_id=job.video_id,
        status=job.status.value.lower(),
        progress=progress,
        result=result_data,
        error=job.error_message,
    )


# ===========================================================================
# GET /api/dubbing/videos/{video_id}/dubbed — Get dubbed video URL
# ===========================================================================

@router.get(
    "/videos/{video_id}/dubbed",
    response_model=DubbedVideoResponse,
    summary="Get dubbed video",
    description="""
Get the presigned URL for a dubbed video.

**Requirements:**
- Video must have a completed dubbing pipeline
- dubbed_video_path must be set in the database

**Returns:**
- dubbed_video_url: Presigned URL valid for 1 hour
- created_at: When the dubbing was completed
- metadata: Video and dubbing information

**Note:** The presigned URL expires after 1 hour. Call this endpoint again to get a fresh URL.
""",
)
async def get_dubbed_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get presigned URL for a dubbed video."""
    
    # 1. Get video from database
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.user_id)
    )
    video = result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(
            status_code=404,
            detail=f"Video {video_id} not found or access denied."
        )
    
    # 2. Check if dubbed video exists
    if not video.dubbed_video_path:
        raise HTTPException(
            status_code=404,
            detail=f"No dubbed video available for video {video_id}. "
                   "Start a dubbing pipeline with POST /api/dubbing/full-pipeline"
        )
    
    # 3. Generate presigned URL from storage service
    storage = get_storage_service()
    try:
        dubbed_video_url = await storage.get_url(
            video.dubbed_video_path,
            filename=f"dubbed_{video.original_filename}"
        )
    except Exception as exc:
        logger.error(f"[DUBBING] Failed to generate URL for {video.dubbed_video_path}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate download URL for dubbed video."
        )
    
    # 4. Build metadata
    metadata = {
        "duration": video.duration,
        "format": video.format,
        "width": video.width,
        "height": video.height,
        "size_bytes": video.size_bytes,
    }
    
    # Add dubbing-specific metadata if available
    if video.dubbing_metadata:
        metadata.update(video.dubbing_metadata)
    
    return DubbedVideoResponse(
        video_id=video.id,
        dubbed_video_url=dubbed_video_url,
        created_at=video.updated_at.isoformat() if video.updated_at else datetime.utcnow().isoformat(),
        metadata=metadata,
    )
