import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Set USE_GPU_FFMPEG=1 in the environment (via docker-compose.gpu.yml) to enable
# NVDEC hardware-accelerated decoding on the GTX 1080 Ti.
_USE_GPU = os.getenv("USE_GPU_FFMPEG", "0") == "1"


class VideoMetadata:
    __slots__ = ("duration", "width", "height", "format", "codec", "frame_rate", "size", "audio_present")

    def __init__(self, *, duration: float, width: Optional[int], height: Optional[int],
                 format: str, codec: str, frame_rate: float, size: int, audio_present: bool):
        self.duration = duration
        self.width = width
        self.height = height
        self.format = format
        self.codec = codec
        self.frame_rate = frame_rate
        self.size = size
        self.audio_present = audio_present

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "codec": self.codec,
            "frame_rate": self.frame_rate,
            "size": self.size,
            "audio_present": self.audio_present,
        }


async def get_metadata(file_path: str) -> VideoMetadata:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()}")

    data = json.loads(stdout.decode())
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream and not audio_stream:
        raise RuntimeError(f"No video or audio stream found in {file_path}")

    duration = float(fmt.get("duration") or 0)
    if duration == 0 and video_stream:
        duration = float(video_stream.get("duration") or 0)
    if duration == 0 and audio_stream:
        duration = float(audio_stream.get("duration") or 0)

    width = int(video_stream["width"]) if video_stream and video_stream.get("width") else None
    height = int(video_stream["height"]) if video_stream and video_stream.get("height") else None
    codec = (
        (video_stream.get("codec_name") if video_stream else None)
        or (audio_stream.get("codec_name") if audio_stream else None)
        or "unknown"
    )
    format_name = fmt.get("format_name") or "unknown"
    size = int(fmt.get("size") or 0)

    frame_rate = 0.0
    if video_stream:
        r = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, r.split("/"))
            frame_rate = num / den if den else 0.0
        except Exception:
            frame_rate = 0.0

    return VideoMetadata(
        duration=duration, width=width, height=height,
        format=format_name, codec=codec, frame_rate=frame_rate,
        size=size, audio_present=audio_stream is not None,
    )


async def extract_audio(input_path: str, output_path: str) -> bool:
    cmd = ["ffmpeg"]
    if _USE_GPU:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", "-y", output_path]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("extract_audio failed: %s", stderr.decode())
    return proc.returncode == 0


async def generate_thumbnail(input_path: str, output_path: str, time_offset: float = 1.0) -> bool:
    cmd = ["ffmpeg"]
    if _USE_GPU:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-ss", str(time_offset), "-i", input_path, "-vframes", "1", "-vf", "scale=640:-1", "-y", output_path]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0 and time_offset > 0:
        return await generate_thumbnail(input_path, output_path, 0.0)
    p = Path(output_path)
    return p.exists() and p.stat().st_size > 0
