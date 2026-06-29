"""Video/audio mux for the dubbing merge stage (mux-only — TTS provides combined WAV).

Replaces original video audio with the TTS combined track using explicit stream
mapping (same approach as backend DubbingMergeService._replace_video_audio).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.ffmpeg import get_metadata
from app.storage import download_file, upload_file

logger = logging.getLogger(__name__)


async def _run_ffmpeg(*args: str) -> None:
    cmd = ["ffmpeg", "-y", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")


async def replace_video_audio(
    video_local: Path,
    audio_local: Path,
    output_local: Path,
) -> None:
    """Replace video audio track with combined TTS WAV (pad audio to video duration)."""
    try:
        video_meta = await get_metadata(str(video_local))
        video_duration = video_meta.duration
    except Exception as exc:
        logger.warning("[mux] Could not read video duration: %s — apad without whole_dur", exc)
        video_duration = None

    if video_duration and video_duration > 0:
        apad_filter = f"[1:a]apad=whole_dur={video_duration:.6f}[aout]"
    else:
        apad_filter = "[1:a]apad[aout]"

    codec = settings.DUBBING_OUTPUT_AUDIO_CODEC
    bitrate = settings.DUBBING_OUTPUT_AUDIO_BITRATE

    await _run_ffmpeg(
        "-i", str(video_local),
        "-i", str(audio_local),
        "-filter_complex", apad_filter,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", codec,
        "-b:a", bitrate,
        "-shortest",
        str(output_local),
    )

    if not output_local.exists():
        raise RuntimeError("FFmpeg mux succeeded but output file was not created")


async def mux_video_with_audio(
    *,
    video_key: str,
    audio_key: str,
    output_key: str,
    temp_dir: str,
) -> dict:
    """Download combined WAV + original video, mux, upload dubbed video.

    Returns dict with combined_audio_key and dubbed_video_key.
    """
    work = Path(temp_dir)
    work.mkdir(parents=True, exist_ok=True)

    audio_local = work / "combined_audio.wav"
    video_local = work / "original_video"
    dubbed_local = work / "dubbed_output.mp4"

    if not await download_file(audio_key, str(audio_local)):
        raise RuntimeError(f"Failed to download combined audio: {audio_key}")

    if not await download_file(video_key, str(video_local)):
        raise RuntimeError(f"Failed to download original video: {video_key}")

    logger.info("[mux] Replacing audio | video_key=%s audio_key=%s", video_key, audio_key)
    await replace_video_audio(video_local, audio_local, dubbed_local)

    await upload_file(str(dubbed_local), output_key, "video/mp4")
    logger.info("[mux] Dubbed video uploaded: %s", output_key)

    return {
        "combined_audio_key": audio_key,
        "dubbed_video_key": output_key,
    }
