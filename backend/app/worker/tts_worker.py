"""TTS worker — synthesizes speech for translated segments using SILMA-TTS.

Consumes ``job.start.tts`` and publishes results to ``job.results.tts``.
"""
import logging
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger(__name__)


def _make_engine():
    """Wrapper so tests can patch tts_worker._make_engine."""
    import app.worker._db as _db
    return _db._make_engine()

from app.worker.base_worker import BaseWorker
from app.worker.registry import register

import app.worker._db as _db
from app.worker._db import (
    create_child_job,
    load_job,
    update_job_output,
)


# Module-level SilmaTTS singleton — loaded once per process.
_silma_tts = None
_silma_lock = None


def _get_silma_tts():
    """Lazily initialise SILMA-TTS model (thread-safe)."""
    global _silma_tts, _silma_lock
    if _silma_tts is not None:
        return _silma_tts

    import threading
    if _silma_lock is None:
        _silma_lock = threading.Lock()

    with _silma_lock:
        if _silma_tts is not None:
            return _silma_tts

        from app.config import settings
        from silma_tts.api import SilmaTTS

        ref_audio = settings.get_silma_reference_audio()
        device = settings.SILMA_DEVICE

        logger.info("[TTS] Loading SILMA model (device=%s)...", device)
        _silma_tts = SilmaTTS(
            device=device if device != "auto" else None,
            enable_normalizer=settings.TTS_ENABLE_NORMALIZER,
            force_tashkeel=settings.TTS_FORCE_TASHKEEL,
        )
        logger.info("[TTS] SILMA model loaded | ref_audio=%s", ref_audio or "<auto>")
    return _silma_tts


def _synthesize_segment(
    text: str,
    ref_audio: str,
    ref_text: str,
    output_path: str,
    seed: Optional[int] = None,
) -> str:
    """Run SILMA-TTS inference for a single segment. Returns output_path on success."""
    from app.config import settings

    tts = _get_silma_tts()

    tts.infer(
        ref_file=ref_audio,
        ref_text=ref_text,
        gen_text=text,
        file_wave=output_path,
        speed=settings.TTS_DEFAULT_SPEED,
        cfg_strength=settings.TTS_DEFAULT_CFG_STRENGTH,
        nfe_step=settings.TTS_DEFAULT_NFE_STEP,
        sway_sampling_coef=settings.TTS_DEFAULT_SWAY_COEF,
        target_rms=settings.TTS_DEFAULT_TARGET_RMS,
        seed=seed,
        show_info=logger.info,
        progress=None,
        remove_silence=False,
        normalize_numbers=settings.TTS_ENABLE_NORMALIZER,
        force_tashkeel=settings.TTS_FORCE_TASHKEEL,
    )
    return output_path


def _upload_wav(local_path: str, key: str) -> str:
    """Upload a WAV file to storage and return its URL."""
    import asyncio
    from app.storage import S3StorageService

    async def _upload():
        storage = S3StorageService()
        with open(local_path, "rb") as f:
            data = f.read()
        await storage.upload_bytes(data, key, "audio/wav")
        return await storage.get_url(key)

    return asyncio.run(_upload())


@register(
    routing_key="job.start.tts",
    result_key="job.results.tts",
    job_type="TTS_SYNTHESIZE",
    description="Synthesize speech for translated segments using SILMA-TTS",
)
async def handle_tts(job_id: str) -> dict:
    """Synthesize TTS for each translated segment.

    ``job_id`` is the NMT child job's ID. Load its output_data to get
    the translated segments, then run SILMA-TTS per segment.
    """
    import asyncio

    # 1. Load the NMT child job
    nmt_job = load_job(job_id)
    if nmt_job is None:
        raise ValueError(f"NMT job {job_id} not found")

    nmt_output = nmt_job.get("output_data", {})
    segments = nmt_output.get("segments", [])
    video_id = nmt_job.get("video_id")

    if not video_id:
        raise ValueError(f"No video_id for NMT job {job_id}")

    if not segments:
        logger.warning("[TTS] No segments to synthesize | job=%s", job_id)
        return {"status": "completed", "segments": []}

    # 2. Create TTS child job
    tts_job_id = create_child_job(
        job_id,
        "TTS_SYNTHESIZE",
        input_data={"video_id": video_id},
    )
    update_job_output(tts_job_id, {"status": "processing"})

    # 3. Preload SILMA-TTS model (blocking, but only once)
    try:
        _get_silma_tts()
    except Exception as e:
        logger.error("[TTS] Failed to load SILMA model: %s", e)
        update_job_output(tts_job_id, {"status": "failed"}, status="FAILED", error=str(e))
        return {"status": "failed", "error": str(e), "_result_job_id": tts_job_id}

    from app.config import settings
    ref_audio = settings.get_silma_reference_audio()
    ref_text = settings.SILMA_REFERENCE_TEXT

    # 4. Synthesize each segment in a thread pool
    result_segments = []
    max_workers = max(1, min(2, len(segments)))

    def _process_segment(idx: int, seg: dict) -> dict:
        base = {
            "segment_id": seg.get("segment_id", idx),
            "start": seg.get("start", 0),
            "end": seg.get("end", 0),
            "original_text": seg.get("original_text", ""),
            "translated_text": seg.get("translated_text", ""),
        }

        translated = seg.get("translated_text", "").strip()
        if not translated:
            base["tts_error"] = "Empty translated text"
            return base

        seg_wav_path = None
        try:
            seed = hash(f"{tts_job_id}_{idx}") % 4294967295
            seg_wav_path = os.path.join(
                tempfile.gettempdir(),
                f"tts_{tts_job_id}_seg_{idx}.wav",
            )
            _synthesize_segment(
                text=translated,
                ref_audio=ref_audio,
                ref_text=ref_text,
                output_path=seg_wav_path,
                seed=seed,
            )

            minio_key = f"tts/{tts_job_id}/segment_{idx}.wav"
            audio_url = _upload_wav(seg_wav_path, minio_key)
            base["tts_key"] = minio_key
            base["audio_url"] = audio_url
        except Exception as exc:
            logger.error("[TTS] Segment %d failed: %s", idx, exc)
            base["tts_error"] = str(exc)
        finally:
            if seg_wav_path and os.path.exists(seg_wav_path):
                try:
                    os.unlink(seg_wav_path)
                except OSError:
                    pass
        return base

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_process_segment, idx, seg): idx
            for idx, seg in enumerate(segments)
        }
        for future in as_completed(futures):
            result_segments.append(future.result())

    # Sort by segment_id to maintain order
    result_segments.sort(key=lambda s: s.get("segment_id", 0))

    failed = [s for s in result_segments if s.get("tts_error")]
    succeeded = [s for s in result_segments if not s.get("tts_error")]

    logger.info(
        "[TTS] Done | job=%s | total=%d | succeeded=%d | failed=%d",
        tts_job_id, len(result_segments), len(succeeded), len(failed),
    )

    output = {
        "_result_job_id": tts_job_id,
        "status": "completed",
        "video_id": video_id,
        "segments": result_segments,
        "metadata": {
            "total_segments": len(result_segments),
            "succeeded": len(succeeded),
            "failed": len(failed),
        },
    }

    update_job_output(tts_job_id, output, status="COMPLETED")
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
