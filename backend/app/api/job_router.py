"""Job status API router.

Endpoints:
  GET    /api/jobs/{job_id}            — Fetch a single job by ID.
  GET    /api/jobs/video/{video_id}    — List all jobs for a given video.
  GET    /api/jobs/                    — List jobs for the authenticated user.
  POST   /api/jobs/{job_id}/cancel     — Cancel a queued / processing job.
  PATCH  /api/jobs/{job_id}/progress   — Worker callback to update progress.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import User
from app.jobs.models import JobStatus
from app.jobs.schemas import JobProgressUpdate, JobResponse
from app.jobs.service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


# ------------------------------------------------------------------
# Dependency helpers
# ------------------------------------------------------------------

def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(db)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Return a single job.  Users can only see their own jobs."""
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return job


@router.get("/video/{video_id}", response_model=List[JobResponse])
async def list_jobs_for_video(
    video_id: str,
    skip: int = 0,
    limit: int = 50,
    service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> List[JobResponse]:
    """Return all jobs associated with a video owned by the current user."""
    jobs = await service.list_jobs(user_id=current_user.user_id, video_id=video_id, skip=skip, limit=limit)
    return jobs


@router.get("/", response_model=List[JobResponse])
async def list_my_jobs(
    skip: int = 0,
    limit: int = 50,
    service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> List[JobResponse]:
    """Return all jobs belonging to the authenticated user."""
    return await service.list_jobs(user_id=current_user.user_id, skip=skip, limit=limit)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Cancel a job that is still QUEUED or PROCESSING.

    Raises 404 if the job does not exist, 403 if it belongs to another user,
    and 409 if it is already in a terminal state.
    """
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    terminal_states = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    if job.status in terminal_states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already in terminal state: {job.status.value}",
        )
    cancelled = await service.cancel_job(job_id)
    if cancelled is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cancelled


@router.patch("/{job_id}/progress", response_model=JobResponse)
async def update_job_progress(
    job_id: str,
    payload: JobProgressUpdate,
    service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Worker callback: update progress and optionally status / error message.

    In production this endpoint would be protected by a shared secret rather
    than a user JWT, but we keep the auth consistent with the rest of the API
    for now.
    """
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    updated = await service.update_job_progress(
        job_id,
        progress=payload.progress,
        status=payload.status,
        error_message=payload.error_message,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return updated
