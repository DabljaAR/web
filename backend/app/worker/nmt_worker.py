"""NMT worker — translates transcribed segments using NLLB-200.

Consumes ``job.start.nmt`` and publishes results to ``job.results.nmt``.
"""
import logging
from typing import Optional

from app.config import settings
from app.nmt.length_adjuster import adjust_ar
from app.nmt.service import translator
from app.worker._db import create_child_job, load_job, update_job_output
from app.worker.base_worker import BaseWorker
from app.worker.registry import register

logger = logging.getLogger(__name__)


@register(
    routing_key="job.start.nmt",
    result_key="job.results.nmt",
    job_type="NMT_TRANSLATE",
    description="Neural machine translation using NLLB-200",
)
async def handle_nmt(job_id: str) -> dict:
    """Translate all segments using NLLB-200.

    ``job_id`` is the STT child job's ID. Load its output_data to get
    the transcribed segments, translate them all, and create an NMT
    child job for the result.
    """
    # 1. Load the STT child job
    stt_job = load_job(job_id)
    if stt_job is None:
        raise ValueError(f"STT job {job_id} not found")

    stt_output = stt_job.get("output_data", {})
    segments = stt_output.get("segments", [])
    if not segments:
        logger.warning("[NMT] No segments to translate | job=%s", job_id)
        return {"status": "completed", "segments": [], "translated_transcript": ""}

    input_data = stt_job.get("input_data", {})
    source_lang = input_data.get("source_lang", "auto")
    target_lang = input_data.get("target_lang", "arb_Arab")
    task_id = input_data.get("task_id")
    video_id = stt_job.get("video_id")

    # 2. Create NMT child job
    nmt_job_id = create_child_job(
        job_id,
        "NMT_TRANSLATE",
        input_data={
            "task_id": task_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
        },
    )

    update_job_output(nmt_job_id, {"status": "processing"})

    # 3. Resolve source language
    actual_src_lang = None if source_lang in {None, "auto"} else source_lang

    # 4. Translate segments one by one
    translated_segments = []
    import asyncio

    def translate_sync(text: str) -> str:
        return translator._translate_item(
            text,
            actual_src_lang,
            target_lang,
            512,
            num_beams=5,
            english_ratio_threshold=0.5,
        )

    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            logger.debug("[NMT] Skipping empty segment %d", idx)
            translated_text = ""
        else:
            try:
                translated_text = await asyncio.to_thread(translate_sync, text)

                # 5. Optional length adjustment via Groq
                if settings.NMT_LENGTH_ADJUST_ENABLED and translated_text:
                    try:
                        translated_text = adjust_ar(
                            translated_text,
                            text,
                            scale=settings.NMT_LENGTH_ADJUST_SCALE,
                            max_iters=settings.NMT_LENGTH_ADJUST_MAX_ITERS,
                            groq_api_key=settings.GROQ_API_KEY,
                            groq_model=settings.GROQ_MODEL,
                        )
                    except Exception as adj_exc:
                        logger.warning(
                            "[NMT] Length adjustment failed for segment %d: %s",
                            idx, adj_exc,
                        )
            except Exception as exc:
                logger.error("[NMT] Segment %d translation failed: %s", idx, exc)
                translated_text = text  # fallback to original

        translated_segments.append({
            "segment_id": idx,
            "start": seg.get("start"),
            "end": seg.get("end"),
            "original_text": text,
            "translated_text": translated_text,
        })

    translated_transcript = " ".join(
        s["translated_text"] for s in translated_segments
    ).strip()

    output = {
        "_result_job_id": nmt_job_id,
        "status": "completed",
        "video_id": video_id,
        "segments": translated_segments,
        "translated_transcript": translated_transcript,
        "metadata": {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "segment_count": len(translated_segments),
        },
    }

    update_job_output(nmt_job_id, output, status="COMPLETED")

    logger.info(
        "[NMT] Done | job=%s | segments=%d",
        nmt_job_id, len(translated_segments),
    )

    return output


def create_worker(rabbitmq_url: str, concurrency: int = 2) -> BaseWorker:
    """Create and configure an NMT worker."""
    worker = BaseWorker(
        rabbitmq_url=rabbitmq_url,
        concurrency=concurrency,
        worker_name="nmt",
    )
    worker.register_handler(
        routing_key="job.start.nmt",
        fn=handle_nmt,
        result_key="job.results.nmt",
        job_type="NMT_TRANSLATE",
    )
    return worker
