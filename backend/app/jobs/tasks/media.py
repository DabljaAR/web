"""Celery tasks for video media processing."""
import logging
from datetime import datetime

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.media.process_video",
    max_retries=3,
    default_retry_delay=30,
    queue="media",
)
def process_video(self, job_id: str, video_id: str, file_path_key: str) -> dict:
    """
    Celery wrapper around the async ``process_video_task`` in
    ``app.media.service``.

    Args:
        job_id:        UUID of the corresponding ``jobs`` row.
        video_id:      UUID of the ``videos`` row to process.
        file_path_key: Storage key (local path or S3 object key) for
                       the raw uploaded video file.

    Returns:
        dict with ``video_id`` and ``status`` on success.
    """
    from app.media.service import process_video_task  # lazy to avoid import loop

    # Mark as started
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )

    try:
        self._run_sync(process_video_task(video_id, file_path_key))
    except Exception as exc:
        logger.exception("process_video failed for video %s: %s", video_id, exc)
        raise self.retry(exc=exc)

    return {"video_id": video_id, "status": "COMPLETED"}


@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.media.process_video_hls",
    max_retries=3,
    default_retry_delay=30,
    queue="media",
)
def process_video_hls(self, job_id: str, video_id: str, file_path_key: str) -> dict:
    """
    Celery wrapper around the async ``process_video_hls_task`` in
    ``app.media.service``.

    Args:
        job_id:        UUID of the corresponding ``jobs`` row.
        video_id:      UUID of the ``videos`` row to transcode to HLS.
        file_path_key: Storage key for the raw uploaded video file.

    Returns:
        dict with ``video_id`` and ``status`` on success.
    """
    from app.media.service import process_video_hls_task  # lazy import

    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )

    try:
        self._run_sync(process_video_hls_task(video_id, file_path_key))
    except Exception as exc:
        logger.exception("process_video_hls failed for video %s: %s", video_id, exc)
        raise self.retry(exc=exc)

    return {"video_id": video_id, "status": "COMPLETED"}
