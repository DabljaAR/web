"""FFmpeg-based progressive video builder."""
import asyncio
import logging
from pathlib import Path
from typing import Optional
import subprocess
import shutil

logger = logging.getLogger(__name__)


class ProgressiveFFmpegBuilder:
    """
    FFmpeg-based progressive video builder.
    
    Strategy: Audio overlay insertion at specific timeline positions
    """
    
    def __init__(self, temp_dir: Path = Path("/tmp/progressive_videos")):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(exist_ok=True)
        
        # Verify FFmpeg is available
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg not found in PATH")
    
    async def create_silent_base_video(
        self, 
        original_video_path: str, 
        job_id: str,
        duration: float
    ) -> Path:
        """
        Create base video with visuals but silent audio track.
        This serves as the foundation for progressive audio insertion.
        """
        
        # CRITICAL DEBUG: Check input duration
        logger.critical(f"[DURATION-DEBUG] create_silent_base_video called | job={job_id} | input_duration={duration}s | original_video={original_video_path}")
        
        # Validate input duration - anything over 10 minutes is suspicious for typical videos
        if duration > 600:
            logger.error(f"[DURATION-DEBUG] Suspicious duration detected: {duration}s ({duration/60:.1f} minutes) - this seems wrong!")
            
        output_path = self.temp_dir / f"{job_id}_base_silent.mp4"
        
        cmd = [
            "ffmpeg",
            "-i", original_video_path,
            # Create silent audio track matching video duration
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "copy",  # Copy video stream (no re-encoding)
            "-c:a", "aac",   # Encode silent audio
            "-t", str(duration),
            "-y",
            str(output_path)
        ]
        
        # CRITICAL DEBUG: Log exact FFmpeg command
        logger.critical(f"[DURATION-DEBUG] FFmpeg command: {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.temp_dir)
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"[FFMPEG] Silent base creation failed | job={job_id} | error={error_msg}")
                raise RuntimeError(f"Failed to create silent base video: {error_msg}")
            
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError(f"Silent base video file is empty or missing: {output_path}")
            
            # CRITICAL DEBUG: Verify output duration
            actual_duration = await self._get_video_duration(output_path)
            file_size_mb = output_path.stat().st_size / 1024 / 1024
            
            logger.critical(f"[DURATION-DEBUG] Silent base created | job={job_id} | expected={duration}s | actual={actual_duration}s | size={file_size_mb:.1f}MB")
            
            # Alert on duration mismatch
            duration_diff = abs(actual_duration - duration)
            if duration_diff > 5.0:  # More than 5 second difference is concerning
                logger.error(f"[DURATION-DEBUG] DURATION MISMATCH! | job={job_id} | expected={duration}s | actual={actual_duration}s | diff={duration_diff}s")
                # Don't raise exception yet, just log - we want to see the pattern
            
            logger.info(f"[FFMPEG] Created silent base | job={job_id} | output={output_path} | size={file_size_mb:.1f}MB | duration={actual_duration}s")
            return output_path
            
        except Exception as e:
            logger.error(f"[FFMPEG] Exception during silent base creation | job={job_id} | error={e}")
            raise
    
    async def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(video_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                duration_str = stdout.decode().strip()
                return float(duration_str) if duration_str else 0.0
            else:
                logger.warning(f"[FFPROBE] Failed to get duration | path={video_path} | error={stderr.decode()}")
                return 0.0
                
        except Exception as e:
            logger.warning(f"[FFPROBE] Exception getting duration | path={video_path} | error={e}")
            return 0.0
    
    async def insert_audio_segment(
        self,
        current_video_path: Path,
        audio_path: Path, 
        start_time: float,
        end_time: float,
        job_id: str,
        segment_id: int
    ) -> Optional[Path]:
        """
        Insert audio segment at specific timeline position using FFmpeg filter_complex.
        
        Technical approach:
        1. Use adelay to position audio at correct timeline offset
        2. Use amix to blend with existing audio (replacing silent sections)
        3. Copy video stream to avoid re-encoding
        """
        
        # Generate unique output path to avoid FFmpeg "same as input" error
        # Use timestamp to ensure uniqueness even on retries
        import time
        timestamp = int(time.time() * 1000)  # milliseconds
        output_path = self.temp_dir / f"{job_id}_seg_{segment_id:04d}_{timestamp}.mp4"
        
        # Calculate delay in samples (44100 Hz sample rate)
        delay_samples = int(start_time * 44100)
        segment_duration = end_time - start_time
        
        logger.info(f"[FFMPEG-DEBUG] Starting segment insert | job={job_id} | segment={segment_id}")
        
        # Validate that output path is different from input (FFmpeg requirement)
        if output_path == current_video_path:
            logger.error(f"[FFMPEG-DEBUG] Output path same as input! | job={job_id} | segment={segment_id} | path={output_path}")
            raise ValueError(f"FFmpeg cannot use same file as input and output: {output_path}")
        
        # Input validation with safe size calculation
        video_size = f"{current_video_path.stat().st_size / 1024 / 1024:.1f}MB" if current_video_path.exists() else "N/A"
        logger.info(f"[FFMPEG-DEBUG] Input validation | current_video={current_video_path} | exists={current_video_path.exists()} | size={video_size}")
        
        audio_size = f"{audio_path.stat().st_size / 1024:.1f}KB" if audio_path.exists() else "N/A"
        logger.info(f"[FFMPEG-DEBUG] Audio input | audio_path={audio_path} | exists={audio_path.exists()} | size={audio_size}")
        
        logger.info(f"[FFMPEG-DEBUG] Timing | start={start_time:.2f}s | end={end_time:.2f}s | duration={segment_duration:.2f}s | delay_samples={delay_samples}")
        logger.info(f"[FFMPEG-DEBUG] Output | output_path={output_path} | different_from_input={output_path != current_video_path}")
        
        # Build filter_complex command
        filter_complex = (
            f"[1:a]adelay={delay_samples}|{delay_samples}[delayed_audio];"  # Delay new audio to timeline position
            f"[0:a][delayed_audio]amix=inputs=2:duration=longest:dropout_transition=0[mixed_audio]"  # Mix with existing audio
        )
        
        cmd = [
            "ffmpeg",
            "-i", str(current_video_path),  # Input 0: current video
            "-i", str(audio_path),          # Input 1: new audio segment
            "-filter_complex", filter_complex,
            "-map", "0:v",           # Copy video from input 0
            "-map", "[mixed_audio]", # Use mixed audio
            "-c:v", "copy",          # Copy video (no re-encoding) 
            "-c:a", "aac",           # Encode mixed audio
            "-b:a", "192k",          # Audio bitrate
            "-avoid_negative_ts", "make_zero",  # Handle timing issues
            "-y",
            str(output_path)
        ]
        
        # Log the full FFmpeg command for debugging
        logger.info(f"[FFMPEG-DEBUG] Command | job={job_id} | segment={segment_id} | cmd={' '.join(cmd)}")
        
        try:
            logger.debug(f"[FFMPEG] Inserting segment | job={job_id} | segment={segment_id} | start={start_time:.1f}s | duration={segment_duration:.1f}s")
            
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.temp_dir)
            )
            stdout, stderr = await process.communicate()
            
            # Log FFmpeg output for debugging
            if stdout:
                logger.debug(f"[FFMPEG-DEBUG] stdout | job={job_id} | segment={segment_id} | output={stdout.decode()}")
            if stderr:
                logger.info(f"[FFMPEG-DEBUG] stderr | job={job_id} | segment={segment_id} | error={stderr.decode()}")
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"[FFMPEG-DEBUG] Command failed | job={job_id} | segment={segment_id} | return_code={process.returncode} | error={error_msg}")
                return None
            
            # Validate output file
            if not output_path.exists():
                logger.error(f"[FFMPEG-DEBUG] Output file not created | job={job_id} | segment={segment_id} | path={output_path}")
                return None
                
            if output_path.stat().st_size == 0:
                logger.error(f"[FFMPEG-DEBUG] Output file is empty | job={job_id} | segment={segment_id} | path={output_path}")
                return None
            
            # Log successful insertion with file size info
            file_size_mb = output_path.stat().st_size / 1024 / 1024
            logger.info(f"[FFMPEG-DEBUG] Segment inserted successfully | job={job_id} | segment={segment_id} | start={start_time:.1f}s | duration={segment_duration:.1f}s | size={file_size_mb:.1f}MB")
            return output_path
            
        except Exception as e:
            logger.error(f"[FFMPEG-DEBUG] Exception during segment insertion | job={job_id} | segment={segment_id} | error={e}", exc_info=True)
            return None
    
    async def optimize_final_video(self, job_id: str, input_path: Path) -> Path:
        """
        Final optimization pass after all segments are merged.
        This ensures optimal compression and quality.
        """
        
        output_path = self.temp_dir / f"{job_id}_final_optimized.mp4"
        
        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-c:v", "libx264",      # Re-encode video for optimal compression
            "-preset", "medium",     # Balance quality vs speed
            "-crf", "23",           # Constant Rate Factor (quality)
            "-c:a", "aac",          # Audio codec
            "-b:a", "192k",         # Audio bitrate
            "-movflags", "+faststart",  # Enable progressive download
            "-y",
            str(output_path)
        ]
        
        try:
            logger.info(f"[FFMPEG] Starting final optimization | job={job_id}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.temp_dir)
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"[FFMPEG] Final optimization failed | job={job_id} | error={error_msg}")
                return input_path  # Return original if optimization fails
            
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error(f"[FFMPEG] Optimized file invalid | job={job_id}")
                return input_path
            
            # Compare file sizes
            original_size_mb = input_path.stat().st_size / 1024 / 1024
            optimized_size_mb = output_path.stat().st_size / 1024 / 1024
            compression_ratio = (original_size_mb - optimized_size_mb) / original_size_mb * 100
            
            logger.info(f"[FFMPEG] Final optimization complete | job={job_id} | original={original_size_mb:.1f}MB | optimized={optimized_size_mb:.1f}MB | saved={compression_ratio:.1f}%")
            return output_path
            
        except Exception as e:
            logger.error(f"[FFMPEG] Exception during final optimization | job={job_id} | error={e}")
            return input_path
    
    async def extract_audio_info(self, video_path: Path) -> dict:
        """Extract audio information from video file."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json", 
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {"error": stderr.decode()}
            
            import json
            probe_data = json.loads(stdout.decode())
            
            # Extract audio stream info
            audio_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]
            
            return {
                "duration": float(probe_data.get("format", {}).get("duration", 0)),
                "audio_streams": len(audio_streams),
                "sample_rate": audio_streams[0].get("sample_rate") if audio_streams else None,
                "channels": audio_streams[0].get("channels") if audio_streams else None,
                "codec": audio_streams[0].get("codec_name") if audio_streams else None
            }
            
        except Exception as e:
            logger.error(f"[FFMPEG] Failed to extract audio info | path={video_path} | error={e}")
            return {"error": str(e)}
    
    async def create_silence_segment(self, duration: float, output_path: Path) -> bool:
        """Create a silence audio segment of specified duration."""
        cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(duration),
            "-c:a", "aac",
            "-y",
            str(output_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return process.returncode == 0 and output_path.exists()
            
        except Exception as e:
            logger.error(f"[FFMPEG] Failed to create silence segment | duration={duration} | error={e}")
            return False
    
    def cleanup_temp_files(self, job_id: str, keep_final: bool = True):
        """Clean up temporary files for a job."""
        try:
            pattern = f"{job_id}_*.mp4"
            temp_files = list(self.temp_dir.glob(pattern))
            
            final_file = self.temp_dir / f"{job_id}_final_optimized.mp4"
            
            for temp_file in temp_files:
                if keep_final and temp_file == final_file:
                    continue  # Keep the final optimized file
                
                temp_file.unlink(missing_ok=True)
                logger.debug(f"[FFMPEG] Cleaned up temp file | file={temp_file}")
                
        except Exception as e:
            logger.warning(f"[FFMPEG] Failed to cleanup temp files | job={job_id} | error={e}")