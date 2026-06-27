"""Database helpers for RabbitMQ workers.

Reuses the same sync psycopg2 + NullPool pattern as ``BaseJobTask._make_db()``
to avoid asyncpg incompatibility in worker processes.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

from app.config import settings

# Ensure SQLAlchemy mapper knows about the Video model so FK resolution
# on jobs.video_id → videos.id works in worker processes.
from app.videos.models import Video  # noqa: F401

logger = logging.getLogger(__name__)

_JOB_MODEL = None


def _get_job_model():
    global _JOB_MODEL
    if _JOB_MODEL is None:
        from app.jobs.models import Job
        _JOB_MODEL = Job
    return _JOB_MODEL


def _get_video_model():
    from app.videos.models import Video
    return Video


def _make_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, poolclass=NullPool)
    return engine, sessionmaker(bind=engine)


def load_job(job_id: str) -> Optional[dict]:
    """Load a job row from DB and return as dict, or None."""
    Job = _get_job_model()
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                return None
            return {
                "id": job.id,
                "video_id": job.video_id,
                "user_id": job.user_id,
                "job_type": job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
                "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                "progress": job.progress,
                "parent_job_id": job.parent_job_id,
                "input_data": job.input_data or {},
                "output_data": job.output_data or {},
                "error_message": job.error_message,
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
            }
    finally:
        engine.dispose()


def update_job_output(job_id: str, output_data: dict, *, status: Optional[str] = None, error: Optional[str] = None):
    """Update a job's output_data and optionally status/error."""
    Job = _get_job_model()
    from app.jobs.models import JobStatus

    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                logger.warning("Job %s not found for update", job_id)
                return
            job.output_data = output_data
            if status:
                job.status = JobStatus(status)
            if error:
                job.error_message = error
            job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
    finally:
        engine.dispose()


def create_child_job(
    parent_job_id: str,
    job_type: str,
    *,
    input_data: Optional[dict] = None,
) -> str:
    """Create a child job row inheriting user_id/video_id from parent.

    Returns the new job's UUID string.
    """
    Job = _get_job_model()
    from app.jobs.models import JobStatus, JobType

    new_id = str(uuid.uuid4())
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            parent = db.get(Job, parent_job_id)
            if not parent:
                raise ValueError(f"Parent job {parent_job_id} not found")

            resolved_type = (
                JobType(job_type)
                if isinstance(job_type, str)
                else job_type
            )

            child = Job(
                id=new_id,
                parent_job_id=parent_job_id,
                job_type=resolved_type,
                status=JobStatus.QUEUED,
                user_id=parent.user_id,
                video_id=parent.video_id,
                input_data=dict(parent.input_data or {}, **(input_data or {})),
            )
            db.add(child)
            db.commit()
    finally:
        engine.dispose()
    logger.info("Created child job %s (type=%s, parent=%s)", new_id, job_type, parent_job_id)
    return new_id


def get_video_file_key(video_id: str) -> Optional[str]:
    """Get the audio or file key for a video from the DB."""
    Video = _get_video_model()
    engine, SessionLocal = _make_engine()
    try:
        with SessionLocal() as db:
            video = db.get(Video, video_id)
            if video is None:
                return None
            return video.audio_path or video.file_path
    finally:
        engine.dispose()
