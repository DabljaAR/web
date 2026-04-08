"""Dubbing merge service for syncing translated audio with video."""
import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import settings
from app.dubbing.schemas import SegmentTimingInfo, DubbingMergeResponse, TimingWarning
from app.media.ffmpeg_service import FFmpegService
from app.media.storage import get_storage_service, S3StorageService

logger = logging.getLogger(__name__)


class DubbingMergeService:
    """
    Service for merging TTS audio segments with video.
    
    Handles:
    - Downloading TTS segments from MinIO
    - Time-stretching audio to match original timing
    - Adding silence gaps between segments
    - Concatenating all segments
    - Merging final audio with video
    """
    
    def __init__(self):
        self.ffmpeg = FFmpegService()
        self.storage = get_storage_service()
        self.temp_dir = Path(settings.DUBBING_TEMP_DIR)
        self.max_stretch = settings.DUBBING_MAX_STRETCH_RATIO
        self.min_stretch = settings.DUBBING_MIN_STRETCH_RATIO
        self.silence_threshold = settings.DUBBING_SILENCE_THRESHOLD

    async def merge_segments(
        self,
        video_id: str,
        segments: List[SegmentTimingInfo],
        job_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        video_file_key: Optional[str] = None,
    ) -> DubbingMergeResponse:
        """
        Main orchestration method for dubbing merge.
        
        Args:
            video_id: Video ID to process
            segments: List of segment timing info with TTS audio keys
            job_id: Optional job ID for tracking
            progress_callback: Optional callback(percent: float) for progress updates
        
        Returns:
            DubbingMergeResponse with output location and metadata
        """
        start_time = time.time()
        warnings = []
        
        # Create temp workspace
        session_dir = self.temp_dir / f"{video_id}_{int(time.time())}"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            logger.info(f"[DubbingMerge] Starting merge for video_id={video_id}, segments={len(segments)}")
            
            # Update progress: 5%
            if progress_callback:
                await progress_callback(5.0)
            
            # Phase 1: Validate segments
            valid_segments = await self._validate_segments(segments)
            if not valid_segments:
                raise ValueError("No valid segments found for dubbing merge")
            
            logger.info(f"[DubbingMerge] {len(valid_segments)} valid segments")
            
            # Update progress: 10%
            if progress_callback:
                await progress_callback(10.0)
            
            # Phase 2: Download TTS segments from MinIO
            downloaded_segments = await self._download_tts_segments(
                valid_segments, 
                session_dir,
                progress_callback
            )
            
            # Update progress: 30%
            if progress_callback:
                await progress_callback(30.0)
            
            # Phase 3: Calculate stretch factors for each segment
            stretch_info = await self._calculate_stretch_factors(downloaded_segments)
            
            # Collect warnings
            for seg_info in stretch_info:
                if seg_info.get("will_trim", False):  # Use will_trim flag instead of impossible condition
                    warnings.append(
                        f"Segment {seg_info['segment_id']}: "
                        f"{seg_info['mismatch_percent']:.1f}% duration mismatch, "
                        f"applied max stretch {self.max_stretch}x and trimmed"
                    )
            
            # Update progress: 40%
            if progress_callback:
                await progress_callback(40.0)
            
            # Phase 4: Apply time-stretching and prepare audio timeline
            processed_segments = await self._process_audio_segments(
                stretch_info,
                session_dir,
                progress_callback
            )
            
            # Update progress: 70%
            if progress_callback:
                await progress_callback(70.0)
            
            # Phase 5: Concatenate all audio segments
            final_audio_path = await self._merge_audio_segments(
                processed_segments,
                session_dir
            )
            
            logger.info(f"[DubbingMerge] Final audio created: {final_audio_path}")
            
            # Update progress: 80%
            if progress_callback:
                await progress_callback(80.0)
            
            # Phase 6: Merge audio with video
            output_path = await self._merge_with_video(
                video_id,
                final_audio_path,
                session_dir,
                video_key=video_file_key,
            )
            
            # Update progress: 90%
            if progress_callback:
                await progress_callback(90.0)
            
            # Phase 7: Upload to MinIO
            output_key = f"videos/{video_id}/dubbed/{int(time.time())}.mp4"
            output_url = await self._upload_output(output_path, output_key)
            
            processing_time = time.time() - start_time
            
            # Calculate statistics
            segments_stretched = sum(1 for s in stretch_info if s["stretch_factor"] != 1.0)
            avg_stretch = sum(s["stretch_factor"] for s in stretch_info) / len(stretch_info)
            
            metadata = {
                "total_segments": len(valid_segments),
                "segments_stretched": segments_stretched,
                "avg_stretch_factor": round(avg_stretch, 3),
                "warnings": warnings,
                "processing_time": round(processing_time, 2)
            }
            
            logger.info(
                f"[DubbingMerge] Completed for video_id={video_id} | "
                f"segments={len(valid_segments)} | "
                f"stretched={segments_stretched} | "
                f"time={processing_time:.1f}s"
            )
            
            # Update progress: 100%
            if progress_callback:
                await progress_callback(100.0)
            
            return DubbingMergeResponse(
                job_id=job_id or f"dubbing_{video_id}",
                video_id=video_id,
                output_key=output_key,
                output_url=output_url,
                metadata=metadata
            )
        
        finally:
            # Cleanup temp files
            await self._cleanup_temp_files(session_dir)

    async def _validate_segments(
        self, 
        segments: List[SegmentTimingInfo]
    ) -> List[SegmentTimingInfo]:
        """
        Validate segments have required fields and sort by start time.
        
        Args:
            segments: List of segment timing info
        
        Returns:
            List of valid segments, sorted by start time
        """
        valid = []
        
        for seg in segments:
            if not seg.tts_audio_key:
                logger.warning(f"[DubbingMerge] Segment {seg.segment_id} missing tts_audio_key, skipping")
                continue
            
            if seg.start < 0 or seg.end <= seg.start:
                logger.warning(
                    f"[DubbingMerge] Segment {seg.segment_id} has invalid timing "
                    f"(start={seg.start}, end={seg.end}), skipping"
                )
                continue
            
            valid.append(seg)
        
        # Sort by start time
        valid.sort(key=lambda s: s.start)
        
        return valid

    async def _download_tts_segments(
        self,
        segments: List[SegmentTimingInfo],
        session_dir: Path,
        progress_callback: Optional[callable] = None
    ) -> List[Tuple[SegmentTimingInfo, Path]]:
        """
        Download all TTS segments from MinIO.
        
        Args:
            segments: List of segments to download
            session_dir: Temporary directory for downloads
            progress_callback: Progress callback for 10-30% range
        
        Returns:
            List of (segment_info, local_path) tuples
        """
        downloaded = []
        audio_dir = session_dir / "audio_segments"
        audio_dir.mkdir(exist_ok=True)
        
        total = len(segments)
        
        for idx, seg in enumerate(segments):
            local_path = audio_dir / f"segment_{seg.segment_id}.wav"
            
            try:
                # Download from MinIO
                success = await self.storage.download(seg.tts_audio_key, str(local_path))
                
                if not success or not local_path.exists():
                    logger.error(
                        f"[DubbingMerge] Failed to download segment {seg.segment_id} "
                        f"from {seg.tts_audio_key}"
                    )
                    continue
                
                # Get actual audio duration
                duration = await self.ffmpeg.get_audio_duration(str(local_path))
                if duration:
                    seg.tts_duration = duration
                
                downloaded.append((seg, local_path))
                logger.debug(
                    f"[DubbingMerge] Downloaded segment {seg.segment_id}: "
                    f"{seg.tts_audio_key} -> {local_path}"
                )
                
            except Exception as e:
                logger.error(
                    f"[DubbingMerge] Error downloading segment {seg.segment_id}: {e}"
                )
                continue
            
            # Update progress (10% to 30%)
            if progress_callback:
                progress = 10.0 + (20.0 * (idx + 1) / total)
                await progress_callback(progress)
        
        if not downloaded:
            raise ValueError("Failed to download any TTS segments")
        
        return downloaded

    async def _calculate_stretch_factors(
        self,
        segments: List[Tuple[SegmentTimingInfo, Path]]
    ) -> List[dict]:
        """
        Calculate stretch factor for each segment based on timing mismatch.
        
        Args:
            segments: List of (segment_info, audio_path) tuples
        
        Returns:
            List of dicts with segment_id, stretch_factor, mismatch_percent, etc.
        """
        stretch_info = []
        
        for seg_info, audio_path in segments:
            target_duration = seg_info.end - seg_info.start
            actual_duration = seg_info.tts_duration or target_duration
            
            # Calculate required stretch factor
            if target_duration > 0:
                required_stretch = actual_duration / target_duration
            else:
                required_stretch = 1.0
            
            # Clamp to min/max stretch limits
            stretch_factor = max(
                self.min_stretch,
                min(self.max_stretch, required_stretch)
            )
            
            # Calculate mismatch percentage
            mismatch_percent = ((actual_duration - target_duration) / target_duration) * 100
            
            stretch_info.append({
                "segment_id": seg_info.segment_id,
                "segment_info": seg_info,
                "audio_path": audio_path,
                "target_duration": target_duration,
                "actual_duration": actual_duration,
                "stretch_factor": stretch_factor,
                "mismatch_percent": mismatch_percent,
                "will_trim": required_stretch > self.max_stretch
            })
            
            logger.debug(
                f"[DubbingMerge] Segment {seg_info.segment_id}: "
                f"target={target_duration:.2f}s, actual={actual_duration:.2f}s, "
                f"stretch={stretch_factor:.3f}x, mismatch={mismatch_percent:.1f}%"
            )
        
        return stretch_info

    async def _process_audio_segments(
        self,
        stretch_info: List[dict],
        session_dir: Path,
        progress_callback: Optional[callable] = None
    ) -> List[dict]:
        """
        Apply time-stretching to audio segments.
        
        Args:
            stretch_info: List of segment stretch information
            session_dir: Working directory
            progress_callback: Progress callback for 40-70% range
        
        Returns:
            List of processed segment dicts with output_path
        """
        processed_dir = session_dir / "processed"
        processed_dir.mkdir(exist_ok=True)
        
        processed = []
        total = len(stretch_info)
        
        for idx, info in enumerate(stretch_info):
            output_path = processed_dir / f"segment_{info['segment_id']}_processed.wav"
            
            # Apply time-stretching if needed
            if abs(info["stretch_factor"] - 1.0) > 0.01:  # Stretch if >1% difference
                success = await self._apply_time_stretch(
                    str(info["audio_path"]),
                    str(output_path),
                    info["stretch_factor"]
                )
                
                if not success:
                    logger.warning(
                        f"[DubbingMerge] Time-stretch failed for segment {info['segment_id']}, "
                        f"using original"
                    )
                    output_path = info["audio_path"]
            else:
                # No stretch needed, use original
                output_path = info["audio_path"]
            
            info["output_path"] = output_path
            processed.append(info)
            
            # Update progress (40% to 70%)
            if progress_callback:
                progress = 40.0 + (30.0 * (idx + 1) / total)
                await progress_callback(progress)
        
        return processed

    async def _apply_time_stretch(
        self,
        input_path: str,
        output_path: str,
        stretch_factor: float
    ) -> bool:
        """
        Apply time-stretching using FFmpeg atempo filter.
        
        Note: atempo filter accepts values between 0.5 and 2.0.
        For larger stretches, chain multiple atempo filters.
        
        Args:
            input_path: Input audio file
            output_path: Output audio file
            stretch_factor: Stretch factor (>1.0 speeds up, <1.0 slows down)
        
        Returns:
            True if successful
        """
        # Build atempo filter chain
        # atempo range is 0.5-2.0, so chain if needed
        atempo_filters = []
        remaining_stretch = stretch_factor
        
        while remaining_stretch > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining_stretch /= 2.0
        
        while remaining_stretch < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining_stretch /= 0.5
        
        atempo_filters.append(f"atempo={remaining_stretch:.3f}")
        
        filter_str = ",".join(atempo_filters)
        
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-filter:a", filter_str,
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
                logger.error(f"[DubbingMerge] atempo failed: {stderr.decode()}")
                return False
            
            return Path(output_path).exists()
        
        except Exception as e:
            logger.error(f"[DubbingMerge] Error in time-stretch: {e}")
            return False

    async def _prepare_audio_timeline(
        self,
        processed_segments: List[dict]
    ) -> List[Tuple[Path, float]]:
        """
        Prepare audio timeline with silence gaps between segments.
        
        Args:
            processed_segments: List of processed segment dicts
        
        Returns:
            List of (audio_path, gap_after_seconds) tuples
        """
        timeline = []
        
        for i, seg in enumerate(processed_segments):
            audio_path = seg["output_path"]
            
            # Calculate gap after this segment
            if i < len(processed_segments) - 1:
                next_seg = processed_segments[i + 1]
                current_end = seg["segment_info"].end
                next_start = next_seg["segment_info"].start
                gap_after = max(0, next_start - current_end)
                
                # Apply minimum silence threshold - zero out tiny gaps
                if gap_after < self.silence_threshold:
                    gap_after = 0.0
            else:
                gap_after = 0  # No gap after last segment
            
            timeline.append((audio_path, gap_after))
        
        return timeline

    async def _merge_audio_segments(
        self,
        processed_segments: List[dict],
        session_dir: Path
    ) -> Path:
        """
        Concatenate all audio segments with silence gaps.
        
        Args:
            processed_segments: List of processed segments
            session_dir: Working directory
        
        Returns:
            Path to final merged audio file
        """
        concat_file = session_dir / "concat_list.txt"
        final_audio = session_dir / "final_audio.wav"
        
        # Prepare timeline with gaps
        timeline = await self._prepare_audio_timeline(processed_segments)
        
        # Build concat file
        with open(concat_file, "w") as f:
            # Add leading silence if first segment doesn't start at 0
            if processed_segments and processed_segments[0].get("start", 0.0) > 0:
                leading_silence = processed_segments[0]["start"]
                leading_silence_path = session_dir / "silence_leading.wav"
                await self._generate_silence(leading_silence_path, leading_silence)
                f.write(f"file '{leading_silence_path}'\n")
            
            for i, (audio_path, gap_after) in enumerate(timeline):
                f.write(f"file '{audio_path}'\n")
                
                # Add silence if gap > 0
                if gap_after > 0:
                    # Generate silence file (use index to avoid collision)
                    silence_path = session_dir / f"silence_{i}.wav"
                    await self._generate_silence(silence_path, gap_after)
                    f.write(f"file '{silence_path}'\n")
        
        # Concatenate using FFmpeg
        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            "-y",
            str(final_audio)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"[DubbingMerge] concat failed: {stderr.decode()}")
                raise RuntimeError("Audio concatenation failed")
            
            if not final_audio.exists():
                raise RuntimeError("Final audio file not created")
            
            return final_audio
        
        except Exception as e:
            logger.error(f"[DubbingMerge] Error merging audio segments: {e}")
            raise

    async def _generate_silence(self, output_path: Path, duration: float) -> bool:
        """Generate a silent WAV file of specified duration."""
        cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),  # Use -t for reliable duration
            "-y",
            str(output_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            return process.returncode == 0 and output_path.exists()
        except Exception as e:
            logger.error(f"[DubbingMerge] Error generating silence: {e}")
            return False

    async def _merge_with_video(
        self,
        video_id: str,
        audio_path: Path,
        session_dir: Path,
        video_key: Optional[str] = None,
    ) -> Path:
        """
        Merge final audio with original video.

        Args:
            video_id: Video ID (used only as fallback for DB lookup)
            audio_path: Path to final merged audio
            session_dir: Working directory
            video_key: MinIO key for the original video file.  Should always
                be supplied by the caller (fetched via sync psycopg2 in the
                Celery task) to avoid opening an asyncpg session on a
                worker-owned event loop, which causes
                "another operation is in progress" errors.

        Returns:
            Path to output video file
        """
        # Resolve the original video key.
        # The caller (dubbing_merge task) must provide this via _make_db() so
        # we never touch AsyncSessionLocal from a Celery worker event loop.
        if not video_key:
            # Last-resort fallback: only reached if the task layer failed to
            # supply the key.  Creates a FRESH async engine with NullPool so
            # we don't reuse connections from the FastAPI pool.
            logger.warning(
                f"[DubbingMerge] video_file_key not supplied for video {video_id}; "
                f"falling back to in-service DB lookup (may fail in worker context)"
            )
            from app.media.models import Video
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy.pool import NullPool

            _engine = create_async_engine(settings.ASYNC_DATABASE_URL, poolclass=NullPool)
            _AsyncSession = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with _AsyncSession() as db:
                    video = await db.get(Video, video_id)
                    if not video:
                        raise ValueError(f"Video {video_id} not found")
                    video_key = video.file_path
            finally:
                await _engine.dispose()

        # Download original video from MinIO
        local_video = session_dir / "original_video.mp4"
        success = await self.storage.download(video_key, str(local_video))

        if not success:
            raise RuntimeError(f"Failed to download video: {video_key}")

        # Merge audio with video
        output_video = session_dir / "output_dubbed.mp4"

        success = await self.ffmpeg.merge_audio_to_video(
            video_path=str(local_video),
            audio_path=str(audio_path),
            output_path=str(output_video),
            video_codec="copy",  # Don't re-encode video
            audio_codec=settings.DUBBING_OUTPUT_AUDIO_CODEC,
            audio_bitrate=settings.DUBBING_OUTPUT_AUDIO_BITRATE
        )

        if not success:
            raise RuntimeError("Failed to merge audio with video")

        return output_video

    async def _upload_output(self, local_path: Path, output_key: str) -> str:
        """Upload final video to MinIO and return presigned URL."""
        with open(local_path, "rb") as f:
            video_bytes = f.read()
        
        await self.storage.upload_bytes(video_bytes, output_key, "video/mp4")
        
        # Get presigned URL
        url = await self.storage.get_url(output_key)
        
        return url

    async def _cleanup_temp_files(self, session_dir: Path):
        """Clean up temporary files."""
        try:
            import shutil
            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.debug(f"[DubbingMerge] Cleaned up temp dir: {session_dir}")
        except Exception as e:
            logger.warning(f"[DubbingMerge] Failed to clean up {session_dir}: {e}")