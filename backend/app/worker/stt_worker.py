"""STT worker — transcribes audio using Whisper.

Consumes ``job.start.stt`` and publishes results to ``job.results.stt``.
"""
import logging
import os
import tempfile
import time
from pathlib import Path

from app.media.storage import get_storage_service
from app.stt.models import WhisperModelManager
from app.worker._db import (
    create_child_job,
    get_video_file_key,
    load_job,
    update_job_output,
)
from app.worker.base_worker import BaseWorker
from app.worker.registry import register

logger = logging.getLogger(__name__)


@register(
    routing_key="job.start.stt",
    result_key="job.results.stt",
    job_type="STT_TRANSCRIBE",
    description="Speech-to-text transcription using Whisper",
)
async def handle_stt(job_id: str) -> dict:
    """Transcribe audio for the given pipeline job_id."""
    # 1. Load the pipeline job (type: FULL_DUBBING_PIPELINE)
    pipeline_job = load_job(job_id)
    if pipeline_job is None:
        raise ValueError(f"Pipeline job {job_id} not found")

    video_id = pipeline_job.get("video_id")
    if not video_id:
        raise ValueError(f"Pipeline job {job_id} has no video_id")

    input_data = pipeline_job.get("input_data", {})
    language = input_data.get("source_lang")
    target_lang = input_data.get("target_lang", "arb_Arab")
    processing_mode = input_data.get("processing_mode", "single")
    task_id = input_data.get("task_id")

    # 2. Create STT child job
    stt_job_id = create_child_job(
        job_id,
        "STT_TRANSCRIBE",
        input_data={
            "video_id": video_id,
            "source_lang": language,
            "target_lang": target_lang,
            "processing_mode": processing_mode,
            "task_id": task_id,
        },
    )

    update_job_output(stt_job_id, {"status": "processing"})

    # 3. Get audio file key
    file_key = get_video_file_key(video_id)
    if not file_key:
        raise ValueError(f"No audio/file path for video {video_id}")

    # 4. Download audio from MinIO
    storage = get_storage_service()
    import asyncio

    with tempfile.TemporaryDirectory() as tmp_dir:
        suffix = Path(file_key).suffix or ".mp3"
        local_path = Path(tmp_dir) / f"audio{suffix}"

        loop = asyncio.new_event_loop()
        if isinstance(loop, asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
        try:
            downloaded = loop.run_until_complete(
                storage.download(file_key, str(local_path))
            )
        finally:
            loop.close()

        if not downloaded:
            raise RuntimeError(f"Failed to download {file_key}")

        # 5. Run Whisper transcription
        whisper = WhisperModelManager()
        structured_segments = []
        transcript_parts = []

        try:
            segments_generator, info = whisper.model.transcribe(
                str(local_path),
                language=language,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 50},
                word_timestamps=True,
            )

            for seg in segments_generator:
                segment_dict = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": " ".join(seg.text.split()),
                }
                structured_segments.append(segment_dict)
                transcript_parts.append(segment_dict["text"])

            full_transcript = " ".join(transcript_parts)

        except Exception as exc:
            logger.error("[STT] Transcription error: %s", exc)
            update_job_output(
                stt_job_id,
                {"status": "failed", "error": str(exc)},
                status="FAILED",
                error=str(exc),
            )
            raise  # base_worker will publish FAILED result

        # 6. Store result
        metadata = {
            "language": info.language,
            "duration": round(info.duration, 2),
            "segment_count": len(structured_segments),
        }

        output = {
            "_result_job_id": stt_job_id,
            "status": "completed",
            "video_id": video_id,
            "transcript": full_transcript,
            "segments": structured_segments,
            "metadata": metadata,
        }

        update_job_output(stt_job_id, output, status="COMPLETED")

        logger.info(
            "[STT] Done | job=%s | segments=%d | duration=%.1fs",
            stt_job_id, len(structured_segments), info.duration,
        )

        return output


def create_worker(rabbitmq_url: str, concurrency: int = 1) -> BaseWorker:
    """Create and configure an STT worker."""
    worker = BaseWorker(
        rabbitmq_url=rabbitmq_url,
        concurrency=concurrency,
        worker_name="stt",
    )

    # Register the STT handler
    worker.register_handler(
        routing_key="job.start.stt",
        fn=handle_stt,
        result_key="job.results.stt",
        job_type="STT_TRANSCRIBE",
    )

    return worker
