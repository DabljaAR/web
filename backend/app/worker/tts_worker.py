"""TTS worker — synthesizes translated segments using SILMA-TTS.

Consumes ``job.start.tts`` and publishes results to ``job.results.tts``.
"""
import logging

from app.config import settings
from app.jobs.celery_app import synthesize_tts
from app.worker._db import create_child_job, load_job, update_job_output
from app.worker.base_worker import BaseWorker
from app.worker.registry import register

logger = logging.getLogger(__name__)


def _synthesize_segment(
    text: str,
    segment_id: int,
    tts_job_id: str,
    ref_audio: str,
) -> dict:
    """Run SILMA-TTS for one segment and upload to MinIO.

    Returns ``{"tts_key": ..., "audio_url": ...}`` or raises.
    """
    minio_key = f"tts/{tts_job_id}/segment_{segment_id}.wav"

    if synthesize_tts is None:
        raise RuntimeError("SILMA-TTS is not available (synthesize_tts is None)")

    result = synthesize_tts.run(
        text=text.strip(),
        ref_audio_path=ref_audio,
        job_id=f"{tts_job_id}_seg_{segment_id}",
        upload_to_minio=True,
        minio_key=minio_key,
    )

    return {
        "tts_key": result.get("minio_key"),
        "audio_url": result.get("audio_url"),
    }


@register(
    routing_key="job.start.tts",
    result_key="job.results.tts",
    job_type="TTS_SYNTHESIZE",
    description="Text-to-speech synthesis using SILMA-TTS",
)
async def handle_tts(job_id: str) -> dict:
    """Synthesize all translated segments.

    ``job_id`` is the NMT child job's ID. Load its output_data to get
    the translated segments, synthesize each one, and create a TTS child
    job for the combined result.
    """
    # 1. Load the NMT child job
    nmt_job = load_job(job_id)
    if nmt_job is None:
        raise ValueError(f"NMT job {job_id} not found")

    nmt_output = nmt_job.get("output_data", {})
    segments = nmt_output.get("segments", [])
    if not segments:
        logger.warning("[TTS] No segments to synthesize | job=%s", job_id)
        return {"status": "completed", "segments": []}

    input_data = nmt_job.get("input_data", {})
    task_id = input_data.get("task_id")
    video_id = nmt_job.get("video_id")

    # 2. Create TTS child job
    tts_job_id = create_child_job(
        job_id,
        "TTS_SYNTHESIZE",
        input_data={"task_id": task_id},
    )

    update_job_output(tts_job_id, {"status": "processing"})

    # 3. Resolve reference audio
    ref_audio = settings.get_silma_reference_audio()

    # 4. Synthesize each segment
    import asyncio

    result_segments = []
    for idx, seg in enumerate(segments):
        translated_text = seg.get("translated_text", "").strip()
        if not translated_text:
            logger.debug("[TTS] Empty text for segment %d — skipping", idx)
            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start"),
                "end": seg.get("end"),
                "original_text": seg.get("original_text", ""),
                "translated_text": translated_text,
                "tts_key": None,
                "audio_url": None,
            })
            continue

        try:
            synth_result = await asyncio.to_thread(
                _synthesize_segment,
                translated_text,
                idx,
                tts_job_id,
                ref_audio,
            )
            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start"),
                "end": seg.get("end"),
                "original_text": seg.get("original_text", ""),
                "translated_text": translated_text,
                "tts_key": synth_result["tts_key"],
                "audio_url": synth_result["audio_url"],
            })
        except Exception as exc:
            logger.exception("[TTS] Segment %d synthesis failed", idx)
            result_segments.append({
                "segment_id": idx,
                "start": seg.get("start"),
                "end": seg.get("end"),
                "original_text": seg.get("original_text", ""),
                "translated_text": translated_text,
                "tts_key": None,
                "audio_url": None,
                "tts_error": str(exc),
            })

    output = {
        "_result_job_id": tts_job_id,
        "status": "completed",
        "video_id": video_id,
        "segments": result_segments,
        "metadata": {
            "total_segments": len(result_segments),
            "failed": sum(1 for s in result_segments if s.get("tts_error")),
        },
    }

    update_job_output(tts_job_id, output, status="COMPLETED")

    logger.info(
        "[TTS] Done | job=%s | segments=%d | failed=%d",
        tts_job_id, len(result_segments), output["metadata"]["failed"],
    )

    return output


def create_worker(rabbitmq_url: str, concurrency: int = 1) -> BaseWorker:
    """Create and configure a TTS worker."""
    worker = BaseWorker(
        rabbitmq_url=rabbitmq_url,
        concurrency=concurrency,
        worker_name="tts",
    )
    worker.register_handler(
        routing_key="job.start.tts",
        fn=handle_tts,
        result_key="job.results.tts",
        job_type="TTS_SYNTHESIZE",
    )
    return worker
