from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobStatus
from app.jobs.schemas import JobCreate, JobUpdate


class JobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_job(self, job_in: JobCreate) -> Job:
        job = Job(
            id=str(uuid4()),
            video_id=str(job_in.video_id),
            user_id=job_in.user_id,
            job_type=job_in.job_type,
            status=job_in.status,
            progress=job_in.progress,
            input_data=job_in.input_data,
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_job(self, job_id: str) -> Optional[Job]:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        video_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Job]:
        q = select(Job)
        if user_id is not None:
            q = q.where(Job.user_id == user_id)
        if video_id is not None:
            q = q.where(Job.video_id == video_id)
        q = q.order_by(Job.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_job(self, job_id: str, update_in: JobUpdate) -> Optional[Job]:
        job = await self.get_job(job_id)
        if not job:
            return None
        for field, value in update_in.model_dump(exclude_none=True).items():
            setattr(job, field, value)
        job.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update_job_progress(
        self,
        job_id: str,
        progress: float,
        status: Optional[JobStatus] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        return await self.update_job(
            job_id,
            JobUpdate(progress=progress, status=status, error_message=error_message),
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel_job(self, job_id: str) -> Optional[Job]:
        return await self.update_job(job_id, JobUpdate(status=JobStatus.CANCELLED))
