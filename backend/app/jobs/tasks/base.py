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
        """Fresh engine + session for this event loop — never reuse FastAPI's pool."""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        from app.config import settings
        engine = create_async_engine(
            settings.DATABASE_URL, pool_size=1, max_overflow=0, pool_pre_ping=True
        )
        return engine, sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @staticmethod
    async def _patch_job(
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
            async with SessionLocal() as db:
                job = await db.get(Job, job_id)
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
                await db.commit()
        finally:
            await engine.dispose()

    # ------------------------------------------------------------------
    # Public helpers for sub-tasks
    # ------------------------------------------------------------------

    def update_progress(self, job_id: str, progress: float) -> None:
        """Persist a progress update (0–100) for the given job."""
        self._run_sync(
            self._patch_job(job_id, JobStatus.PROCESSING, progress=progress)
        )

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        """Called by Celery when the task raises an unhandled exception."""
        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if not job_id:
            return
        logger.error("Task %s failed for job %s: %s", task_id, job_id, exc)
        self._run_sync(
            self._patch_job(
                job_id,
                JobStatus.FAILED,
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:
        """Called by Celery when the task is about to be retried."""
        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if not job_id:
            return
        logger.warning("Task %s retrying for job %s: %s", task_id, job_id, exc)
        self._run_sync(
            self._patch_job(job_id, JobStatus.RETRYING, error_message=str(exc))
        )

    def on_success(self, retval, task_id, args, kwargs) -> None:
        """Called by Celery when the task succeeds."""
        job_id: Optional[str] = args[0] if args else kwargs.get("job_id")
        if not job_id:
            return
        logger.info("Task %s succeeded for job %s", task_id, job_id)
        self._run_sync(
            self._patch_job(
                job_id,
                JobStatus.COMPLETED,
                progress=100.0,
                completed_at=datetime.utcnow(),
            )
        )