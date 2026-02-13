import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class MediaProcessingError(Exception):
    pass

class VideoMetadata(BaseModel):
    duration: float
    width: Optional[int]
    height: Optional[int]
    format: str
    codec: str
    frame_rate: float
    size: int
    audio_present: bool

class FFmpegService:
    def __init__(self):
        # We assume ffmpeg is in PATH
        self.ffprobe_path = "ffprobe"
        self.ffmpeg_path = "ffmpeg"

    async def get_metadata(self, file_path: str) -> VideoMetadata:
        """Use ffprobe to get metadata."""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        
        try:
            # Using asyncio.create_subprocess_exec for non-blocking
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise MediaProcessingError(f"ffprobe failed: {stderr.decode()}")
            
            data = json.loads(stdout.decode())
            
            format_info = data.get("format", {})
            streams = data.get("streams", [])
            
            video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
            audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)
            
            if not video_stream and not audio_stream:
                raise MediaProcessingError("No video or audio stream found")
                
            # Extract duration safely
            duration = float(format_info.get("duration", 0))
            if duration == 0 and video_stream and video_stream.get("duration"):
                 duration = float(video_stream["duration"])
            elif duration == 0 and audio_stream and audio_stream.get("duration"):
                 duration = float(audio_stream["duration"])
            
            # Extract basic info
            width = int(video_stream.get("width", 0)) if video_stream else 0
            height = int(video_stream.get("height", 0)) if video_stream else 0
            codec = video_stream.get("codec_name", "unknown") if video_stream else (audio_stream.get("codec_name", "unknown") if audio_stream else "unknown")
            format_name = format_info.get("format_name", "unknown")
            size = int(format_info.get("size", 0))
            
            # Frame rate parsing (e.g. "30/1")
            frame_rate = 0.0
            if video_stream:
                frame_rate_str = video_stream.get("r_frame_rate", "0/0")
                try:
                    num, den = map(int, frame_rate_str.split('/'))
                    frame_rate = num / den if den != 0 else 0.0
                except:
                    frame_rate = 0.0

            return VideoMetadata(
                duration=duration,
                width=width,
                height=height,
                format=format_name,
                codec=codec,
                frame_rate=frame_rate,
                size=size,
                audio_present=audio_stream is not None
            )

        except Exception as e:
            logger.error(f"Error getting metadata for {file_path}: {e}")
            raise MediaProcessingError(f"Failed to analyze file: {str(e)}")

    async def extract_audio(self, input_path: str, output_path: str) -> bool:
        """Extract audio to MP3/AAC."""
        # Force overwrite (-y)
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-vn", # No video
            "-acodec", "libmp3lame", # Use MP3
            "-q:a", "2", # Quality VBR
            "-y",
            output_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"ffmpeg cleanup failed: {stderr.decode()}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error extracting audio: {e}")
            return False

    async def generate_thumbnail(self, input_path: str, output_path: str, time_offset: float = 1.0) -> bool:
        """Generate thumbnail at specified time."""
        cmd = [
            self.ffmpeg_path,
            "-ss", str(time_offset),
            "-i", input_path,
            "-vframes", "1",
            "-vf", "scale=640:-1", # Scale width to 640, keep aspect ratio
            "-y",
            output_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # Try at 0s if it fails (short video)
                if time_offset > 0:
                    return await self.generate_thumbnail(input_path, output_path, 0.0)
                return False
            
            # Additional check: ensure file exists
            if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
                 return False

            return True
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return False

    async def generate_hls(self, input_path: str, output_dir: str, segment_time: int = 10) -> bool:
        """
        Generate HLS playlist and segments.
        output_dir: Directory where .m3u8 and .ts files will be saved.
        """
        output_playlist = Path(output_dir) / "index.m3u8"
        
        # Simple HLS conversion: copy video if possible or transcode to h264/aac
        # We enforce h264/aac for compatibility
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-codec:v", "libx264",
            "-codec:a", "aac",
            "-map", "0",
            "-f", "hls",
            "-hls_time", str(segment_time),
            "-hls_list_size", "0", # Include all segments in the playlist
            "-hls_segment_filename", str(Path(output_dir) / "segment_%03d.ts"),
            str(output_playlist)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"ffmpeg hls failed: {stderr.decode()}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error generating HLS: {e}")
            return False
