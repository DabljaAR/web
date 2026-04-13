"""Celery application factory for DabljaAR async job processing."""
import logging
import os

logger = logging.getLogger(__name__)

# Pre-import guard: configure GPU/CPU before any AI libraries load
# This must be BEFORE importing any AI modules (torch, torchaudio, etc.)
def _configure_device():
    """Configure CUDA/CPU device based on SILMA_DEVICE setting."""
    # Load settings early to get SILMA_DEVICE
    from app.config import settings
    silma_device = settings.SILMA_DEVICE.lower()
    
    if silma_device == "cpu":
        # Disable CUDA before any AI library loads
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["TORCH_CUDA_ARCH_LIST"] = ""
        return "cpu"
    elif silma_device == "cuda":
        # Explicitly enable CUDA
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        return "cuda"
    else:  # "auto"
        # Let torch detect automatically
        return "auto"

_device_mode = _configure_device()

from celery import Celery
from app.config import settings
from app.jobs.models import JobStatus

celery_app = Celery("dabljaar")

_INSTALL_AI = os.getenv("INSTALL_AI", "false").lower() == "true"
_base_imports = ["app.jobs.tasks.media"]
_ai_imports = (
    [
        "app.jobs.tasks.pipeline",
        "app.jobs.tasks.nmt",
        "app.stt.models",
        "app.tts.models",
    ]
    if _INSTALL_AI
    else []
)

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
        "app.jobs.tasks.media.*":                              {"queue": "media"},
        "app.jobs.tasks.pipeline.stt_transcribe":              {"queue": "ai_stt"},
        "app.jobs.tasks.pipeline.tts_synthesize_segment":      {"queue": "ai_tts"},
        "app.jobs.tasks.pipeline.tts_combine_results":         {"queue": "ai_tts"},
        "app.jobs.tasks.nmt.nmt_translate":                    {"queue": "ai_nmt"},
        "app.jobs.tasks.nmt.translate_segment":                {"queue": "ai_nmt"},
        "app.jobs.tasks.nmt.nmt_combine_results":              {"queue": "ai_nmt"},
        "app.jobs.tasks.tts.synthesize":                       {"queue": "ai_tts"},
    },

    # Autodiscovery target packages (AI modules only when INSTALL_AI=true)
    imports=_base_imports + _ai_imports,
)

# Register TTS task (with graceful fallback if silma-tts not installed)
synthesize_tts = None
if _INSTALL_AI:
    try:
        from app.tts.models import register_tts_task

        synthesize_tts = register_tts_task(celery_app)
        logger.info("✅ SILMA-TTS task registered successfully")
    except ImportError as e:
        logger.warning(f"⚠️  SILMA-TTS task not registered: {e}")
        logger.warning(
            "Install silma-tts to enable TTS functionality: pip install silma-tts"
        )