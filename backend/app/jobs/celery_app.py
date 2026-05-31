"""Celery application factory for DabljaAR async job processing."""
import logging
import os
import time

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
from celery.signals import worker_ready
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

    # Flower/monitoring needs events enabled even when workers are launched
    # without an explicit -E flag (for example in docker-compose overrides).
    worker_send_task_events=True,
    task_send_sent_event=True,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,
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


@worker_ready.connect
def _log_worker_runtime_context(sender=None, **kwargs):
    try:
        logger.info(
            "[CELERY][STARTUP] host=%s pid=%s install_ai=%s device_mode=%s",
            getattr(sender, "hostname", "unknown"),
            os.getpid(),
            _INSTALL_AI,
            _device_mode,
        )
        logger.info(
            "[CELERY][STARTUP] prefetch=%s max_tasks_per_child=%s broker=%s backend=%s",
            celery_app.conf.worker_prefetch_multiplier,
            celery_app.conf.worker_max_tasks_per_child,
            celery_app.conf.broker_url,
            celery_app.conf.result_backend,
        )
        logger.info(
            "[CELERY][STARTUP] env_concurrency=%s pool_hint=%s",
            os.getenv("AI_WORKER_CONCURRENCY") or os.getenv("MEDIA_WORKER_CONCURRENCY") or "unset",
            os.getenv("CELERY_POOL", "unset"),
        )
    except Exception as exc:
        logger.warning("[CELERY][STARTUP] failed to log runtime context: %s", exc)


def _is_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


@worker_ready.connect
def _optional_prewarm_models(sender=None, **kwargs):
    if not _INSTALL_AI:
        return

    prewarm_stt = _is_enabled("PREWARM_STT_MODEL")
    prewarm_nmt = _is_enabled("PREWARM_NMT_MODEL")
    prewarm_tts = _is_enabled("PREWARM_TTS_MODEL")

    if not any((prewarm_stt, prewarm_nmt, prewarm_tts)):
        logger.info("[CELERY][PREWARM] disabled (all PREWARM_* flags false)")
        return

    logger.info(
        "[CELERY][PREWARM] starting | stt=%s nmt=%s tts=%s",
        prewarm_stt,
        prewarm_nmt,
        prewarm_tts,
    )

    if prewarm_stt:
        t0 = time.perf_counter()
        try:
            from app.stt.models import WhisperModelManager

            _ = WhisperModelManager().model
            logger.info(
                "[CELERY][PREWARM] STT ready in %.1fs",
                time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.warning("[CELERY][PREWARM] STT prewarm failed: %s", exc)

    if prewarm_nmt:
        t0 = time.perf_counter()
        try:
            from app.nmt.service import translator

            _ = translator.tokenizer
            _ = translator.model
            logger.info(
                "[CELERY][PREWARM] NMT ready in %.1fs",
                time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.warning("[CELERY][PREWARM] NMT prewarm failed: %s", exc)

    if prewarm_tts:
        t0 = time.perf_counter()
        try:
            from app.tts.models import SilmaTTSModelManager

            _ = SilmaTTSModelManager()._load_model()
            logger.info(
                "[CELERY][PREWARM] TTS ready in %.1fs",
                time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.warning("[CELERY][PREWARM] TTS prewarm failed: %s", exc)

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