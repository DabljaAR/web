"""Audio/video merge operations for the dubbing merge stage."""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from app.ffmpeg import get_metadata
from app.storage import download_file, upload_file

logger = logging.getLogger(__name__)


async def _run_ffmpeg(*args: str) -> str:
    """Run ffmpeg and return stdout. Raises RuntimeError on failure."""
    cmd = ["ffmpeg", "-y", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")
    return ""


async def _generate_silence(duration_secs: float, output_path: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration_secs),
        "-c:a", "pcm_s16le",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0 and Path(output_path).exists()


async def merge_segments(
    segments: list[dict],
    video_id: str,
    job_id: str,
    original_media_key: Optional[str] = None,
    output_key_prefix: str = "dubbed",
    combined_audio_key: str = "",
    temp_dir: str = "/tmp/dubbing_merge",
) -> dict:
    """Download segment WAVs, concatenate, optionally mux with video.

    Returns dict with keys: combined_audio_key, combined_audio_url,
    dubbed_video_key, dubbed_video_url.
    """
    Path(temp_dir).mkdir(parents=True, exist_ok=True)

    # Download segment audio files
    local_segments: list[dict] = []
    for seg in segments:
        tts_key = seg.get("tts_audio_key") or seg.get("tts_key")
        if not tts_key:
            continue
        local_path = str(Path(temp_dir) / f"seg_{seg['segment_id']}.wav")
        if await download_file(tts_key, local_path):
            # Get actual duration
            try:
                meta = await get_metadata(local_path)
                actual_dur = meta.duration
            except Exception:
                actual_dur = seg.get("duration", seg.get("end", 0) - seg.get("start", 0))
            local_segments.append({
                **seg,
                "local_path": local_path,
                "actual_duration": actual_dur,
            })
        else:
            logger.warning("[merge] Could not download segment %s: %s", seg.get("segment_id"), tts_key)

    if not local_segments:
        raise RuntimeError(f"No segment audio files could be downloaded for job {job_id}")

    local_segments.sort(key=lambda s: s.get("start", 0))

    # Build concat file
    concat_list_path = str(Path(temp_dir) / "concat.txt")
    first_start = local_segments[0].get("start", 0)
    total_duration = first_start

    with open(concat_list_path, "w") as f:
        for i, seg in enumerate(local_segments):
            seg_start = seg.get("start", 0)

            # Add silence gap if needed
            if i == 0 and seg_start > 0.01:
                silence_path = str(Path(temp_dir) / "silence_lead.wav")
                if await _generate_silence(seg_start, silence_path):
                    f.write(f"file '{silence_path}'\n")
                    total_duration += seg_start
            elif i > 0:
                prev_end = local_segments[i - 1].get("end", 0)
                gap = seg_start - prev_end
                if gap > 0.01:
                    silence_path = str(Path(temp_dir) / f"silence_{i}.wav")
                    if await _generate_silence(gap, silence_path):
                        f.write(f"file '{silence_path}'\n")
                        total_duration += gap

            f.write(f"file '{seg['local_path']}'\n")
            total_duration += seg.get("actual_duration", seg.get("end", 0) - seg.get("start", 0))

    # Concatenate audio
    combined_wav = str(Path(temp_dir) / f"combined_{job_id}.wav")
    await _run_ffmpeg(
        "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c:a", "pcm_s16le", combined_wav,
    )

    # Upload combined audio
    await upload_file(combined_wav, combined_audio_key, "audio/wav")
    logger.info("[merge] Combined audio uploaded: %s", combined_audio_key)

    result = {
        "combined_audio_key": combined_audio_key,
        "dubbed_video_key": None,
    }

    # If video, mux combined audio with original video
    if original_media_key:
        original_local = str(Path(temp_dir) / "original_video")
        if await download_file(original_media_key, original_local):
            dubbed_local = str(Path(temp_dir) / f"dubbed_{job_id}.mp4")

            # Get combined audio duration for padding
            try:
                audio_meta = await get_metadata(combined_wav)
                audio_dur = audio_meta.duration
            except Exception:
                audio_dur = total_duration

            await _run_ffmpeg(
                "-i", original_local,
                "-i", combined_wav,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                dubbed_local,
            )

            dubbed_key = f"{output_key_prefix}/{video_id}/dubbed_{job_id}.mp4"
            await upload_file(dubbed_local, dubbed_key, "video/mp4")
            result["dubbed_video_key"] = dubbed_key
            logger.info("[merge] Dubbed video uploaded: %s", dubbed_key)

    return result
