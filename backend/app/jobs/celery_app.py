"""Celery application factory for DabljaAR async job processing."""
from celery import Celery
from app.config import settings
from app.jobs.models import JobStatus

celery_app = Celery("dabljaar")

celery_app.conf.update(
    # Broker & backend
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=4,
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour to allow long-running AI tasks
    },

    # Time limits removed (per user request) to allow long video processing
    # task_soft_time_limit=1800,
    # task_time_limit=2100,

    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Queue routing
    task_routes={
        "app.jobs.tasks.media.*":    {"queue": "media"},
        "app.jobs.tasks.pipeline.stt_transcribe": {"queue": "ai_stt"},
        "app.jobs.tasks.pipeline.tts_synthesize": {"queue": "ai_tts"},
        "app.jobs.tasks.pipeline.dubbing_merge":  {"queue": "pipeline"},
        "app.jobs.tasks.nmt.*":      {"queue": "ai_nmt"},
    },

    # Autodiscovery target packages
    imports=[
        "app.jobs.tasks.media",
        "app.jobs.tasks.pipeline",
        "app.jobs.tasks.nmt",
        "app.stt.models",
    ],
)