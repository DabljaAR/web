"""Celery application factory for DabljaAR async job processing."""
from celery import Celery
from app.config import settings

celery_app = Celery("dabljaar")

celery_app.conf.update(
    # Broker & backend
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,

    # Time limits (seconds)
    task_soft_time_limit=600,
    task_time_limit=900,

    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Queue routing
    task_routes={
        "app.jobs.tasks.media.*": {"queue": "media"},
        "app.jobs.tasks.pipeline.*": {"queue": "pipeline"},
        "app.jobs.tasks.stt.*": {"queue": "ai_stt"},
        "app.jobs.tasks.nmt.*": {"queue": "ai_nmt"},
        "app.jobs.tasks.tts.*": {"queue": "ai_tts"},
    },

    # Autodiscovery target packages
    imports=[
        "app.jobs.tasks.media",
        "app.jobs.tasks.pipeline",
    ],
)
