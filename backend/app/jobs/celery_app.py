"""Celery application factory for DabljaAR async job processing."""
import logging
import os

logger = logging.getLogger(__name__)

from celery import Celery
from celery.signals import worker_ready
from app.config import settings
from app.jobs.models import JobStatus

celery_app = Celery("dabljaar")

celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,

    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=4,
    broker_transport_options={
        'visibility_timeout': 3600,
    },

    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    task_routes={
    },

    imports=[],
)


@worker_ready.connect
def _log_worker_runtime_context(sender=None, **kwargs):
    try:
        logger.info(
            "[CELERY][STARTUP] host=%s pid=%s",
            getattr(sender, "hostname", "unknown"),
            os.getpid(),
        )
        logger.info(
            "[CELERY][STARTUP] prefetch=%s max_tasks_per_child=%s broker=%s backend=%s",
            celery_app.conf.worker_prefetch_multiplier,
            celery_app.conf.worker_max_tasks_per_child,
            celery_app.conf.broker_url,
            celery_app.conf.result_backend,
        )
    except Exception as exc:
        logger.warning("[CELERY][STARTUP] failed to log runtime context: %s", exc)
