"""
Standalone async background-task functions for media processing.
No dependency on app.media.* — all video-table writes go through the
Rust media-service via httpx; Job/VideoTask writes use SQLAlchemy directly.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.db import AsyncSessionLocal
from app.jobs.models import Job, JobStatus, JobType
from app.shared.processing_mode import resolve_processing_mode

logger = logging.getLogger(__name__)

_MEDIA_SVC = lambda: os.getenv("MEDIA_SERVICE_URL", "http://media-service:8001")  # noqa: E731


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# process_video_task
# ---------------------------------------------------------------------------

async def process_video_task(video_id: str, file_path_key: str, options: dict = None):
    """
    Background task: probe, extract audio/thumbnail, then optionally trigger
    the STT pipeline.  All video-row writes go to the Rust media-service.
    """
    media_svc_url = _MEDIA_SVC()
    logger.info("Starting processing for video %s", video_id)

    async def _patch_status(payload: dict):
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.patch(f"{media_svc_url}/videos/{video_id}/status", json=payload)
            r.raise_for_status()

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{media_svc_url}/videos/{video_id}")
        if r.status_code == 404:
            logger.error("Video %s not found during processing", video_id)
            return
        r.raise_for_status()
        video_data = r.json()
        user_id = video_data["user_id"]
        media_type_str = str(video_data.get("media_type", "VIDEO")).upper()

        await _patch_status({"status": "PROCESSING"})

        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.get(f"{media_svc_url}/ffmpeg/metadata", params={"path": file_path_key})
            r.raise_for_status()
            meta = r.json()

        await _patch_status({
            "status": "PROCESSING",
            "duration": meta.get("duration"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "size_bytes": meta.get("size"),
            "format": meta.get("format"),
            "codec": meta.get("codec"),
            "frame_rate": meta.get("frame_rate"),
        })

        audio_key = None
        thumbnail_key = None

        if media_type_str == "VIDEO":
            if meta.get("audio_present"):
                audio_key = f"audio/{user_id}/{video_id}.mp3"
                async with httpx.AsyncClient(timeout=300.0) as c:
                    r = await c.post(
                        f"{media_svc_url}/ffmpeg/extract-audio",
                        json={"input_key": file_path_key, "output_key": audio_key},
                    )
                if r.status_code != 200:
                    logger.warning("Audio extraction failed (%s): %s", r.status_code, r.text)
                    audio_key = None

            thumbnail_key = f"thumbnails/{user_id}/{video_id}.jpg"
            async with httpx.AsyncClient(timeout=120.0) as c:
                r = await c.post(
                    f"{media_svc_url}/ffmpeg/thumbnail",
                    json={"input_key": file_path_key, "output_key": thumbnail_key},
                )
            if r.status_code != 200:
                logger.warning("Thumbnail generation failed (%s): %s", r.status_code, r.text)
                thumbnail_key = None

        paths_payload = {}
        if audio_key:
            paths_payload["audio_path"] = audio_key
        if thumbnail_key:
            paths_payload["thumbnail_path"] = thumbnail_key
        if paths_payload:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.patch(f"{media_svc_url}/videos/{video_id}/paths", json=paths_payload)
                r.raise_for_status()

        await _patch_status({"status": "COMPLETED"})
        logger.info("Processing completed for %s %s", media_type_str, video_id)

        if options and media_type_str in ("VIDEO", "AUDIO"):
            output_type = options.get("output_type", "fullDubbing")
            if output_type == "uploadOnly":
                return
            processing_mode = resolve_processing_mode(output_type)
            target_lang = options.get("target_lang", "arb_Arab")

            from app.tasks.models import VideoTask, TaskStatus
            async with AsyncSessionLocal() as db:
                video_task = VideoTask(
                    id=str(uuid.uuid4()),
                    video_id=video_id,
                    user_id=user_id,
                    source_lang=options.get("source_lang"),
                    target_lang=target_lang,
                    output_type=output_type,
                    processing_mode=processing_mode,
                    num_beams=int(options.get("num_beams", 5)),
                    english_ratio_threshold=float(options.get("english_ratio_threshold", 0.5)),
                    status=TaskStatus.QUEUED,
                )
                db.add(video_task)
                await db.flush()

                stt_job_id = str(uuid.uuid4())
                stt_job = Job(
                    id=stt_job_id,
                    video_id=video_id,
                    user_id=user_id,
                    job_type=JobType.STT_TRANSCRIBE,
                    status=JobStatus.QUEUED,
                    input_data={
                        **options,
                        "task_id": video_task.id,
                        "audio_key": audio_key or file_path_key,
                        "target_lang": target_lang,
                        "processing_mode": processing_mode,
                    },
                )
                db.add(stt_job)
                video_task.root_job_id = stt_job_id
                await db.commit()

                from app.jobs.tasks.pipeline import stt_transcribe
                celery_result = stt_transcribe.apply_async(
                    kwargs={"job_id": stt_job_id, "video_id": video_id, "target_lang": target_lang},
                    task_id=stt_job_id,
                )
                stt_job.celery_task_id = celery_result.id
                db.add(stt_job)
                await db.commit()

    except Exception as e:
        logger.error("Processing failed for video %s: %s", video_id, e)
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.patch(
                    f"{media_svc_url}/videos/{video_id}/status",
                    json={"status": "FAILED", "error_message": str(e)},
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# process_video_hls_task
# ---------------------------------------------------------------------------

async def process_video_hls_task(video_id: str, file_path_key: str):
    """
    Background task: generate HLS via the Rust /ffmpeg/hls endpoint.
    Also extracts audio and thumbnail for the source video.
    """
    media_svc_url = _MEDIA_SVC()
    logger.info("Starting HLS processing for video %s", video_id)

    async def _patch_status(payload: dict):
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.patch(f"{media_svc_url}/videos/{video_id}/status", json=payload)
            r.raise_for_status()

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{media_svc_url}/videos/{video_id}")
        if r.status_code == 404:
            logger.error("Video %s not found during HLS processing", video_id)
            return
        r.raise_for_status()
        user_id = r.json()["user_id"]

        await _patch_status({"status": "PROCESSING"})

        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.get(f"{media_svc_url}/ffmpeg/metadata", params={"path": file_path_key})
            r.raise_for_status()
            meta = r.json()

        await _patch_status({
            "status": "PROCESSING",
            "duration": meta.get("duration"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "size_bytes": meta.get("size"),
            "format": meta.get("format"),
            "codec": meta.get("codec"),
            "frame_rate": meta.get("frame_rate"),
        })

        output_prefix = f"videos/{user_id}/{video_id}/hls"
        async with httpx.AsyncClient(timeout=600.0) as c:
            r = await c.post(f"{media_svc_url}/ffmpeg/hls", json={
                "input_key": file_path_key,
                "output_prefix": output_prefix,
                "segment_time": 10,
            })
            r.raise_for_status()
            hls_playlist_key = r.json().get("playlist_key", f"{output_prefix}/index.m3u8")

        audio_key = None
        if meta.get("audio_present"):
            audio_key = f"audio/{user_id}/{video_id}.mp3"
            async with httpx.AsyncClient(timeout=300.0) as c:
                r = await c.post(
                    f"{media_svc_url}/ffmpeg/extract-audio",
                    json={"input_key": file_path_key, "output_key": audio_key},
                )
            if r.status_code != 200:
                audio_key = None

        thumbnail_key = f"thumbnails/{user_id}/{video_id}.jpg"
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                f"{media_svc_url}/ffmpeg/thumbnail",
                json={"input_key": file_path_key, "output_key": thumbnail_key},
            )
        if r.status_code != 200:
            thumbnail_key = None

        paths_payload: dict = {"file_path": hls_playlist_key}
        if audio_key:
            paths_payload["audio_path"] = audio_key
        if thumbnail_key:
            paths_payload["thumbnail_path"] = thumbnail_key

        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.patch(f"{media_svc_url}/videos/{video_id}/paths", json=paths_payload)
            r.raise_for_status()

        await _patch_status({"status": "COMPLETED"})
        logger.info("HLS processing completed for video %s", video_id)

    except Exception as e:
        logger.error("HLS processing failed for video %s: %s", video_id, e)
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.patch(
                    f"{media_svc_url}/videos/{video_id}/status",
                    json={"status": "FAILED", "error_message": str(e)},
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# download_youtube_task
# ---------------------------------------------------------------------------

async def download_youtube_task(
    video_id: str,
    user_id: int,
    youtube_url: str,
    fmt: str,
    quality: str,
    options: dict = None,
):
    """
    Background task: download from YouTube via yt-dlp, upload to S3 via the
    Rust media-service presigned PUT, then run process_video_task.
    """
    try:
        import yt_dlp
    except ModuleNotFoundError as e:
        raise RuntimeError("YouTube support requires yt-dlp to be installed") from e

    import tempfile
    from app.media_service.client import MediaServiceClient

    media_svc_url = _MEDIA_SVC()
    logger.info("Starting YouTube download for video %s: %s", video_id, youtube_url)

    async def _patch_status(payload: dict):
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.patch(f"{media_svc_url}/videos/{video_id}/status", json=payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.patch(f"{media_svc_url}/videos/{video_id}/status", json={"status": "PROCESSING"})

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = str(Path(temp_dir) / "yt_download")

            if fmt == "audio":
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": out_path + ".%(ext)s",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
                    "quiet": True,
                }
            else:
                height = quality.replace("p", "")
                ydl_opts = {
                    "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                    "outtmpl": out_path + ".%(ext)s",
                    "merge_output_format": "mp4",
                    "quiet": True,
                }

            def _do_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(youtube_url, download=True)

            await asyncio.to_thread(_do_download)

            downloaded_file = next(
                (f for f in Path(temp_dir).iterdir() if f.name.startswith("yt_download")),
                None,
            )
            if not downloaded_file:
                raise RuntimeError("yt-dlp did not produce an output file")

            ext = downloaded_file.suffix
            directory = f"audio/{user_id}" if fmt == "audio" else f"videos/{user_id}"
            file_key = f"{directory}/{video_id}{ext}"
            content_type = "audio/mpeg" if fmt == "audio" else "video/mp4"

            client = MediaServiceClient()
            await client.upload_file(downloaded_file, key=file_key, content_type=content_type)

        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.patch(
                f"{media_svc_url}/videos/{video_id}/paths",
                json={"file_path": file_key},
            )
            r.raise_for_status()

        await _patch_status({"status": "PENDING"})
        await process_video_task(video_id, file_key, options=options)

    except Exception as e:
        logger.error("YouTube download failed for video %s: %s", video_id, e)
        await _patch_status({"status": "FAILED", "error_message": str(e)})
