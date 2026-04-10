"""Base Celery task class with automatic job lifecycle management."""
import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from app.jobs.models import Job, JobStatus
from app.media.models import Video  # noqa: F401 - needed for SQLAlchemy mapper resolution
import celery

from app.jobs.models import JobStatus

logger = logging.getLogger(__name__)


class BaseJobTask(celery.Task):
    """
    Abstract base task that syncs Celery task state back to the ``jobs``
    table after every execution.

    Sub-tasks only need to:
    1. Declare ``job_id`` as their first positional argument.
    2. Call ``self.update_progress(job_id, pct)`` when they want to
       report intermediate progress.

    The ``on_failure`` / ``on_retry`` / ``on_success`` hooks handle
    COMPLETED / FAILED / RETRYING transitions automatically.
    """

    abstract = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_sync(coro) -> Any:
        """Run an async coroutine from a sync Celery worker context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    @staticmethod
    def _make_db():
        """Fresh sync engine for Celery workers — uses psycopg2 with NullPool
        to avoid asyncpg incompatibility issues in Celery context."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        from app.config import settings
        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        engine = create_engine(sync_url, poolclass=NullPool)
        return engine, sessionmaker(bind=engine)

    @staticmethod
    def _patch_job(
        job_id: str,
        status: JobStatus,
        *,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
        output_data: Optional[dict] = None,
        celery_task_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update a job row directly — no service layer to avoid circular
        imports between the task module and the service."""
        from app.jobs.models import Job

        engine, SessionLocal = BaseJobTask._make_db()
        try:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job is None:
                    logger.warning("BaseJobTask: job %s not found, skipping patch", job_id)
                    return
                job.status = status
                if progress is not None:
                    job.progress = progress
                if error_message is not None:
                    job.error_message = error_message
                if output_data is not None:
                    job.output_data = output_data
                if celery_task_id is not None:
                    job.celery_task_id = celery_task_id
                if started_at is not None:
                    job.started_at = started_at
                if completed_at is not None:
                    job.completed_at = completed_at
                job.updated_at = datetime.utcnow()
                db.commit()
        finally:
            engine.dispose()

    # ------------------------------------------------------------------
    # Public helpers for sub-tasks
    # ------------------------------------------------------------------

    @staticmethod
    def _create_next_job(
        parent_job_id: str,
        job_type: "JobType",
        *,
        input_data: Optional[dict] = None,
    ) -> str:
        """Create one child job row inheriting user_id/video_id from parent.

        Returns the new job's ID (UUID string).
        """
        from uuid import uuid4
        from app.jobs.models import Job, JobStatus

        new_id = str(uuid4())
        engine, SessionLocal = BaseJobTask._make_db()
        try:
            with SessionLocal() as db:
                parent = db.get(Job, parent_job_id)
                if not parent:
                    raise ValueError(f"Parent job {parent_job_id} not found")
                child = Job(
                    id=new_id,
                    parent_job_id=parent_job_id,
                    job_type=job_type,
                    status=JobStatus.QUEUED,
                    user_id=parent.user_id,
                    video_id=parent.video_id,
                    input_data=input_data or {},
                )
                db.add(child)
                db.commit()
        finally:
            engine.dispose()
        return new_id

    @staticmethod
    def _patch_task(
        task_id: str,
        status,
        *,
        progress: Optional[float] = None,
        transcript: Optional[str] = None,
        translated_transcript: Optional[str] = None,
        segments: Optional[list] = None,
        stt_metadata: Optional[dict] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        combined_audio_key: Optional[str] = None,
        combined_audio_url: Optional[str] = None,  # ignored — not stored in DB
    ) -> None:
        """Update a video_tasks row — mirrors _patch_job but targets VideoTask."""
        from app.tasks.models import VideoTask

        engine, SessionLocal = BaseJobTask._make_db()
        try:
            with SessionLocal() as db:
                task = db.get(VideoTask, task_id)
                if task is None:
                    logger.warning("BaseJobTask: task %s not found, skipping patch", task_id)
                    return
                task.status = status
                if progress is not None:
                    task.progress = progress
                if transcript is not None:
                    task.transcript = transcript
                if translated_transcript is not None:
                    task.translated_transcript = translated_transcript
                if segments is not None:
                    task.segments = segments
                if stt_metadata is not None:
                    task.stt_metadata = stt_metadata
                if error_message is not None:
                    task.error_message = error_message
                if started_at is not None:
                    task.started_at = started_at
                if completed_at is not None:
                    task.completed_at = completed_at
                if combined_audio_key is not None:
                    task.combined_audio_key = combined_audio_key
                task.updated_at = datetime.utcnow()
                db.commit()
        finally:
            engine.dispose()

    def update_progress(self, job_id: str, progress: float) -> None:
        """Persist a progress update (0–100) for the given job."""
        self._patch_job(job_id, JobStatus.PROCESSING, progress=progress)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        """Called by Celery when the task raises an unhandled exception."""
        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if isinstance(job_id, dict):
            job_id = job_id.get("job_id")
            
        if not job_id:
            return
        logger.error("Task %s failed for job %s: %s", task_id, job_id, exc)
        self._patch_job(
            job_id,
            JobStatus.FAILED,
            error_message=str(exc),
            completed_at=datetime.utcnow(),
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:
        """Called by Celery when the task is about to be retried."""
        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if isinstance(job_id, dict):
            job_id = job_id.get("job_id")
            
        if not job_id:
            return
        logger.warning("Task %s retrying for job %s: %s", task_id, job_id, exc)
        self._patch_job(job_id, JobStatus.RETRYING, error_message=str(exc))

    def on_success(self, retval, task_id, args, kwargs) -> None:
        """Called by Celery when the task succeeds."""
        # If the task delegates final completion to a downstream chord callback,
        # it signals this by returning a dict with _skip_completion=True.
        if isinstance(retval, dict) and retval.get("_skip_completion"):
            return

        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if isinstance(job_id, dict):
            job_id = job_id.get("job_id")

        if not job_id:
            return
        logger.info("Task %s succeeded for job %s", task_id, job_id)
        self._patch_job(
            job_id,
            JobStatus.COMPLETED,
            progress=100.0,
            completed_at=datetime.utcnow(),
        )