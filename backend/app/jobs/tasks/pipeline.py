"""AI pipeline Celery tasks (stubs — full implementation in future WBS phases).

Each task follows the same contract:
  - First positional arg is ``job_id`` (consumed by BaseJobTask lifecycle hooks).
  - Returns a dict that downstream tasks in a chain can consume.
"""
import logging
from datetime import datetime

from celery import chain

from app.jobs.celery_app import celery_app
from app.jobs.tasks.base import BaseJobTask
from app.jobs.models import JobStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Speech-to-Text
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.stt_transcribe",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_stt",
)
def stt_transcribe(self, job_id: str, video_id: str, language: str = "auto") -> dict:
    """
    Stub: transcribe audio track of *video_id* to text.

    Returns:
        ``{"job_id": job_id, "video_id": video_id, "transcript_key": "<storage_key>"}``
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call STT service
    logger.info("[STUB] stt_transcribe job=%s video=%s lang=%s", job_id, video_id, language)
    return {"job_id": job_id, "video_id": video_id, "transcript_key": None}


# ---------------------------------------------------------------------------
# Neural Machine Translation
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.nmt_translate",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_nmt",
)
def nmt_translate(
    self,
    job_id: str,
    video_id: str,
    transcript_key: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> dict:
    """
    Stub: translate the transcript produced by ``stt_transcribe``.

    Returns:
        ``{"job_id": job_id, "video_id": video_id, "translation_key": "<storage_key>"}``
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call NMT service
    logger.info(
        "[STUB] nmt_translate job=%s video=%s %s→%s",
        job_id, video_id, source_lang, target_lang,
    )
    return {"job_id": job_id, "video_id": video_id, "translation_key": None}


# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.tts_synthesize",
    max_retries=3,
    default_retry_delay=60,
    queue="ai_tts",
)
def tts_synthesize(
    self,
    job_id: str,
    video_id: str,
    translation_key: str,
    target_lang: str = "en",
) -> dict:
    """
    Stub: synthesise speech from the translated text.

    Returns:
        ``{"job_id": job_id, "video_id": video_id, "audio_key": "<storage_key>"}``
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call TTS service
    logger.info("[STUB] tts_synthesize job=%s video=%s lang=%s", job_id, video_id, target_lang)
    return {"job_id": job_id, "video_id": video_id, "audio_key": None}


# ---------------------------------------------------------------------------
# Dubbing merge
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=BaseJobTask,
    name="app.jobs.tasks.pipeline.dubbing_merge",
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
)
def dubbing_merge(self, job_id: str, video_id: str, audio_key: str) -> dict:
    """
    Stub: merge the synthesised audio track with the original video.

    Returns:
        ``{"job_id": job_id, "video_id": video_id, "output_key": "<storage_key>"}``
    """
    self._run_sync(
        self._patch_job(
            job_id,
            JobStatus.PROCESSING,
            celery_task_id=self.request.id,
            started_at=datetime.utcnow(),
        )
    )
    # TODO: call FFmpeg merge service
    logger.info("[STUB] dubbing_merge job=%s video=%s", job_id, video_id)
    return {"job_id": job_id, "video_id": video_id, "output_key": None}


# ---------------------------------------------------------------------------
# Full dubbing pipeline (orchestrator)
# ---------------------------------------------------------------------------

def dispatch_full_dubbing_pipeline(
    job_id: str,
    video_id: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> None:
    """
    Dispatch the full dubbing pipeline as a Celery ``chain``.

    Sequence: stt_transcribe → nmt_translate → tts_synthesize → dubbing_merge

    Each task receives the return value of the previous one as its first
    positional argument (Celery chain semantics), so the task signatures
    are defined accordingly via ``s()`` / ``si()``.

    Note: ``job_id`` is passed to every task so that ``BaseJobTask`` hooks
    can update the correct row.  For a real implementation each step should
    have its **own** job row; this wires them all to the parent pipeline job
    for simplicity.
    """
    pipeline = chain(
        stt_transcribe.s(job_id, video_id, source_lang),
        nmt_translate.s(),
        tts_synthesize.s(),
        dubbing_merge.si(),
    )
    pipeline.apply_async()
