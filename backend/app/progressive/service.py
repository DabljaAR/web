"""Core progressive video building service."""
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

from app.progressive.models import (
    VideoTimeline, 
    SegmentInfo, 
    ProgressiveSegment, 
    SegmentStatus
)
from app.progressive.ffmpeg_builder import ProgressiveFFmpegBuilder
from app.progressive.notifications import ProgressNotifier
from app.media.storage import get_storage_service
from app.config import settings

logger = logging.getLogger(__name__)


class ProgressiveVideoBuilder:
    """
    Core service for progressive video building.
    
    Key Responsibilities:
    1. Timeline state management
    2. Out-of-order segment handling
    3. FFmpeg progressive merge orchestration  
    4. Real-time progress updates
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ffmpeg_builder = ProgressiveFFmpegBuilder()
        self.notifier = ProgressNotifier()
        self.storage_service = get_storage_service()
        self.active_timelines: Dict[str, VideoTimeline] = {}
        self.merge_locks: Dict[str, asyncio.Lock] = {}
    
    async def initialize_timeline(
        self, 
        job_id: str, 
        video_id: str, 
        segments: List[Dict],
        original_video_path: str
    ) -> VideoTimeline:
        """Initialize progressive timeline from STT segments."""
        
        # Calculate total duration from segments
        total_duration = max(seg['end'] for seg in segments) if segments else 0.0
        
        # CRITICAL DEBUG: Validate duration calculation
        logger.critical(f"[DURATION-DEBUG] initialize_timeline called | job={job_id} | segments_count={len(segments)}")
        logger.critical(f"[DURATION-DEBUG] segments_end_times={[seg['end'] for seg in segments]}")
        logger.critical(f"[DURATION-DEBUG] calculated_total_duration={total_duration}s")
        
        # Validate reasonable duration  
        if total_duration > 600:  # More than 10 minutes
            logger.error(f"[DURATION-DEBUG] SUSPICIOUS DURATION! | job={job_id} | duration={total_duration}s ({total_duration/60:.1f} minutes)")
            logger.error(f"[DURATION-DEBUG] This suggests corrupted segment data or wrong calculation")
        
        # Create timeline object
        timeline = VideoTimeline(
            job_id=job_id,
            video_id=video_id,
            total_duration=total_duration,
            segments={}
        )
        
        # Initialize progressive segments in database
        for i, seg_data in enumerate(segments):
            seg_info = SegmentInfo(
                segment_id=i,
                start_time=seg_data['start'],
                end_time=seg_data['end'], 
                status=SegmentStatus.PENDING
            )
            timeline.segments[i] = seg_info
            
            # Insert into database
            await self._insert_segment_record(job_id, seg_info)
        
        # Initialize base video (silent video with original visuals)
        logger.critical(f"[DURATION-DEBUG] Calling create_silent_base_video | job={job_id} | duration={total_duration}s | original_video={original_video_path}")
        
        base_video_path = await self.ffmpeg_builder.create_silent_base_video(
            original_video_path, 
            job_id,
            total_duration
        )
        timeline.current_video_path = base_video_path
        
        logger.critical(f"[DURATION-DEBUG] Base video created | job={job_id} | path={base_video_path}")
        
        # Cache timeline and create lock
        self.active_timelines[job_id] = timeline
        self.merge_locks[job_id] = asyncio.Lock()
        
        # Update job record with base video path
        await self._update_job_timeline(job_id, len(segments), 0, video_url=None, current_video_path=str(base_video_path))
        
        logger.info(f"[PROGRESSIVE] Initialized timeline | job={job_id} | segments={len(segments)} | duration={total_duration:.1f}s")
        return timeline
    
    async def segment_ready_for_merge(
        self, 
        job_id: str, 
        segment_id: int, 
        tts_audio_key: str,
        nmt_result: Dict
    ) -> bool:
        """
        Called when a segment completes TTS and is ready for video merge.
        
        Implements buffering strategy: Segments wait for predecessors before merging.
        This ensures sequential merge order even with parallel TTS processing.
        """
        
        logger.info(f"[PROGRESSIVE-DEBUG] Starting merge | job={job_id} | segment={segment_id} | audio_key={tts_audio_key}")
        
        async with self.merge_locks.get(job_id, asyncio.Lock()):
            # Step 1: Validate timeline and segment
            timeline = await self._get_timeline(job_id)
            if not timeline:
                logger.error(f"[PROGRESSIVE-DEBUG] Timeline not found | job={job_id}")
                return False
                
            if segment_id not in timeline.segments:
                logger.error(f"[PROGRESSIVE-DEBUG] Segment not in timeline | job={job_id} | segment={segment_id} | available={list(timeline.segments.keys())}")
                return False
            
            # Step 2: Update segment status to READY_TO_MERGE
            segment = timeline.segments[segment_id]
            logger.info(f"[PROGRESSIVE-DEBUG] Segment details | job={job_id} | segment={segment_id} | start={segment.start_time:.1f}s | end={segment.end_time:.1f}s | current_status={segment.status}")
            
            segment.status = SegmentStatus.READY_TO_MERGE
            segment.tts_audio_key = tts_audio_key
            segment.nmt_result = nmt_result
            
            await self._update_segment_status(job_id, segment_id, segment)
            logger.info(f"[PROGRESSIVE-DEBUG] Segment status updated | job={job_id} | segment={segment_id}")
            
            # Step 3: CHECK SEQUENTIAL DEPENDENCY - Wait for predecessor
            if segment_id > 0:
                prev_segment_id = segment_id - 1
                prev_segment = timeline.segments.get(prev_segment_id)
                
                if not prev_segment or prev_segment.status != SegmentStatus.MERGED:
                    # Previous segment not merged yet - buffer this segment
                    merged_count = sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.MERGED)
                    ready_count = sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.READY_TO_MERGE)
                    
                    logger.warning(
                        f"[PROGRESSIVE-BUFFER] Segment {segment_id} waiting for predecessor {prev_segment_id} | "
                        f"job={job_id} | merged={merged_count}/{len(timeline.segments)} | ready={ready_count}"
                    )
                    
                    # Return False to trigger Celery retry - segment will retry later
                    return False
                    
                logger.info(f"[PROGRESSIVE-DEBUG] Predecessor segment {prev_segment_id} merged | job={job_id} | segment={segment_id}")
            
            # Step 4: CRITICAL VALIDATION - Check current video exists
            if not timeline.current_video_path:
                logger.error(f"[PROGRESSIVE-CRITICAL] Timeline corrupted - no current video path | job={job_id} | segment={segment_id}")
                self._log_timeline_state(job_id, timeline)
                
                # This is a critical error - timeline was never properly initialized
                # Don't retry, fail immediately to prevent endless retries
                raise ValueError(f"Timeline corrupted for job {job_id} - base video path missing. STT initialization likely failed.")
                
            if not timeline.current_video_path.exists():
                logger.error(f"[PROGRESSIVE-CRITICAL] Base video file missing | job={job_id} | segment={segment_id} | path={timeline.current_video_path}")
                self._log_timeline_state(job_id, timeline)
                
                # Base video file is missing - this indicates STT base video creation failed
                # Don't retry, fail immediately
                raise ValueError(f"Base video file missing for job {job_id}: {timeline.current_video_path}")
                
            logger.info(f"[PROGRESSIVE-DEBUG] Current video valid | job={job_id} | path={timeline.current_video_path} | size={timeline.current_video_path.stat().st_size / 1024 / 1024:.1f}MB")
            
            # Step 5: Trigger progressive merge
            logger.info(f"[PROGRESSIVE-DEBUG] Starting merge operation | job={job_id} | segment={segment_id}")
            merge_success = await self._merge_segment_into_timeline(job_id, segment)
            logger.info(f"[PROGRESSIVE-DEBUG] Merge operation result | job={job_id} | segment={segment_id} | success={merge_success}")
            
            if merge_success:
                segment.status = SegmentStatus.MERGED
                await self._update_segment_status(job_id, segment_id, segment)
                
                # Update current_video_path in DB (NEW)
                await self._update_job_timeline(
                    job_id,
                    len(timeline.segments),
                    sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.MERGED),
                    video_url=None,  # Will be set later
                    current_video_path=str(timeline.current_video_path) if timeline.current_video_path else None
                )
                
                # Update completion tracking
                timeline_completion = await self._update_completion_tracking(job_id)
                
                # Upload current video and get URL
                video_url = await self._upload_current_video(job_id, timeline)
                
                # Notify progress update
                await self.notifier.notify_segment_merged(
                    job_id, segment_id, timeline_completion, video_url
                )
                
                logger.info(f"[PROGRESSIVE] Segment merged successfully | job={job_id} | segment={segment_id} | completion={timeline_completion:.1f}%")
                
                # TRIGGER NEXT SEGMENT: Check if next segment is waiting
                await self._trigger_waiting_segments(job_id, segment_id)
                
                return True
            else:
                segment.status = SegmentStatus.FAILED
                segment.error_message = "FFmpeg merge failed"
                await self._update_segment_status(job_id, segment_id, segment)
                logger.error(f"[PROGRESSIVE-DEBUG] Merge failed, segment marked as failed | job={job_id} | segment={segment_id}")
                return False
    
    def _log_timeline_state(self, job_id: str, timeline: VideoTimeline):
        """Log detailed timeline state for debugging."""
        status_counts = {}
        for status in SegmentStatus:
            count = sum(1 for s in timeline.segments.values() if s.status == status)
            if count > 0:
                status_counts[status.value] = count
        
        merged_ids = [s.segment_id for s in timeline.segments.values() if s.status == SegmentStatus.MERGED]
        ready_ids = [s.segment_id for s in timeline.segments.values() if s.status == SegmentStatus.READY_TO_MERGE]
        
        logger.error(
            f"[PROGRESSIVE-DEBUG] Timeline state | job={job_id} | "
            f"status_counts={status_counts} | merged={merged_ids} | ready={ready_ids}"
        )
    
    async def _trigger_waiting_segments(self, job_id: str, just_merged_segment_id: int):
        """
        After a segment merges, trigger the next waiting segment.
        
        This implements the cascade effect where completing one segment
        unlocks the next buffered segment for merge.
        """
        next_segment_id = just_merged_segment_id + 1
        timeline = self.active_timelines.get(job_id)
        
        if not timeline or next_segment_id not in timeline.segments:
            return  # No next segment or timeline gone
        
        next_segment = timeline.segments[next_segment_id]
        
        if next_segment.status == SegmentStatus.READY_TO_MERGE:
            logger.info(
                f"[PROGRESSIVE-TRIGGER] Segment {next_segment_id} ready to merge after {just_merged_segment_id} | "
                f"job={job_id}"
            )
            
            # Dispatch merge task for the waiting segment
            from app.jobs.tasks.pipeline import progressive_merge_step
            
            progressive_merge_step.apply_async(
                kwargs={
                    "job_id": job_id,
                    "segment_id": next_segment_id,
                    "segment_data": {
                        "start": next_segment.start_time,
                        "end": next_segment.end_time,
                    },
                    "nmt_result": next_segment.nmt_result or {},
                    "tts_result": {
                        "audio_key": next_segment.tts_audio_key,
                        "status": "completed",
                        "segment_id": next_segment_id,
                        "job_id": job_id
                    }
                },
                queue="pipeline"
            )
    
    async def _merge_segment_into_timeline(
        self, 
        job_id: str, 
        segment: SegmentInfo
    ) -> bool:
        """Merge individual segment into the growing video timeline."""
        
        timeline = self.active_timelines[job_id]
        
        try:
            # Step 1: Download TTS audio from MinIO
            logger.info(f"[PROGRESSIVE-DEBUG] Starting audio download | job={job_id} | segment={segment.segment_id} | audio_key={segment.tts_audio_key}")
            audio_path = await self._download_tts_audio(segment.tts_audio_key)
            if not audio_path:
                logger.error(f"[PROGRESSIVE-DEBUG] Audio download failed | job={job_id} | segment={segment.segment_id} | audio_key={segment.tts_audio_key}")
                return False
            
            logger.info(f"[PROGRESSIVE-DEBUG] Audio downloaded | job={job_id} | segment={segment.segment_id} | path={audio_path} | size={audio_path.stat().st_size / 1024:.1f}KB")
            
            # Step 2: Validate audio file
            try:
                # Quick audio validation using ffprobe
                probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)]
                process = await asyncio.create_subprocess_exec(
                    *probe_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    duration = float(stdout.decode().strip())
                    logger.info(f"[PROGRESSIVE-DEBUG] Audio validation | job={job_id} | segment={segment.segment_id} | duration={duration:.2f}s")
                else:
                    logger.warning(f"[PROGRESSIVE-DEBUG] Audio validation failed | job={job_id} | segment={segment.segment_id} | error={stderr.decode()}")
            except Exception as e:
                logger.warning(f"[PROGRESSIVE-DEBUG] Audio validation exception | job={job_id} | segment={segment.segment_id} | error={e}")
            
            # Step 3: Use FFmpeg to insert audio at timeline position
            logger.info(f"[PROGRESSIVE-DEBUG] Starting FFmpeg merge | job={job_id} | segment={segment.segment_id} | start={segment.start_time:.2f}s | end={segment.end_time:.2f}s")
            new_video_path = await self.ffmpeg_builder.insert_audio_segment(
                current_video_path=timeline.current_video_path,
                audio_path=audio_path,
                start_time=segment.start_time,
                end_time=segment.end_time,
                job_id=job_id,
                segment_id=segment.segment_id
            )
            
            if new_video_path:
                logger.info(f"[PROGRESSIVE-DEBUG] FFmpeg merge successful | job={job_id} | segment={segment.segment_id} | new_video={new_video_path} | size={new_video_path.stat().st_size / 1024 / 1024:.1f}MB")
                
                # Update timeline with new video
                old_video = timeline.current_video_path
                timeline.current_video_path = new_video_path
                
                # Clean up old video file (keep last 2 versions for rollback)
                if old_video and old_video != new_video_path:
                    # Only delete if it's not one of the recent versions
                    await self._cleanup_old_video_versions(job_id, keep_count=2)
                
                return True
            else:
                logger.error(f"[PROGRESSIVE-DEBUG] FFmpeg merge returned None | job={job_id} | segment={segment.segment_id}")
                return False
            
        except Exception as e:
            logger.error(f"[PROGRESSIVE-DEBUG] Merge exception | job={job_id} | segment={segment.segment_id} | error={e}", exc_info=True)
            return False
        finally:
            # Clean up temporary audio file
            if 'audio_path' in locals() and audio_path and audio_path.exists():
                try:
                    audio_path.unlink(missing_ok=True)
                    logger.debug(f"[PROGRESSIVE-DEBUG] Cleaned up audio file | job={job_id} | segment={segment.segment_id} | path={audio_path}")
                except Exception as e:
                    logger.warning(f"[PROGRESSIVE-DEBUG] Failed to cleanup audio | job={job_id} | segment={segment.segment_id} | error={e}")
    
    async def get_current_progress(self, job_id: str) -> Dict:
        """Get current progress and video URL for job."""
        timeline = await self._get_timeline(job_id)
        if not timeline:
            return {"error": "Timeline not found"}
        
        # Get current video URL if available
        video_url = None
        if timeline.current_video_path and timeline.current_video_path.exists():
            video_url = await self._get_current_video_url(job_id)
        
        return {
            "job_id": job_id,
            "completion_percentage": timeline.completion_percentage,
            "segments_completed": sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.MERGED),
            "total_segments": len(timeline.segments),
            "current_video_url": video_url,
            "status": "completed" if timeline.completion_percentage >= 100.0 else "processing",
            "segments_by_status": self._get_segments_by_status(timeline)
        }
    
    # Helper methods
    
    async def _get_segments_from_db(self, job_id: str) -> List[SegmentInfo]:
        """Load segments from database for timeline reconstruction."""
        from app.progressive.models import ProgressiveSegment
        from sqlalchemy import select
        
        stmt = select(ProgressiveSegment).where(
            ProgressiveSegment.job_id == job_id
        ).order_by(ProgressiveSegment.segment_id)
        
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        
        segments = []
        for row in rows:
            segment_info = SegmentInfo(
                segment_id=row.segment_id,
                start_time=row.start_time,
                end_time=row.end_time,
                status=SegmentStatus(row.status),
                tts_audio_key=row.tts_audio_key,
                nmt_result=row.nmt_result,
                error_message=row.error_message
            )
            segments.append(segment_info)
        
        return segments
    
    async def _get_timeline(self, job_id: str) -> Optional[VideoTimeline]:
        """Get timeline, loading from DB if not cached."""
        
        # Fast path: Check memory cache
        if job_id in self.active_timelines:
            return self.active_timelines[job_id]
        
        # Slow path: Reconstruct from database
        logger.info(f"[PROGRESSIVE] Loading timeline from DB | job={job_id}")
        
        # Load job record
        from app.jobs.models import Job
        job_stmt = select(Job).where(Job.id == job_id)
        job_result = await self.db.execute(job_stmt)
        job = job_result.scalar_one_or_none()
        
        if not job:
            logger.error(f"[PROGRESSIVE] Job not found | job_id={job_id}")
            return None
        
        # Load segments from DB
        segments_data = await self._get_segments_from_db(job_id)
        if not segments_data:
            logger.error(f"[PROGRESSIVE] No segments found | job_id={job_id}")
            return None
        
        # Reconstruct timeline
        timeline = VideoTimeline(
            job_id=job_id,
            video_id=str(job.video_id),
            total_duration=max(s.end_time for s in segments_data),
            segments={s.segment_id: s for s in segments_data}
        )
        
        # Restore current_video_path from DB
        if job.merge_timeline and "current_video_path" in job.merge_timeline:
            path_str = job.merge_timeline["current_video_path"]
            timeline.current_video_path = Path(path_str)
            logger.info(f"[PROGRESSIVE] Timeline restored from DB | job={job_id} | path={path_str}")
        else:
            logger.warning(f"[PROGRESSIVE] No current_video_path in DB | job={job_id}")
        
        # Cache for future use
        self.active_timelines[job_id] = timeline
        if job_id not in self.merge_locks:
            self.merge_locks[job_id] = asyncio.Lock()
        
        return timeline
    
    async def _reconstruct_timeline_from_db(self, job_id: str) -> Optional[VideoTimeline]:
        """Deprecated: Use _get_timeline instead."""
        return await self._get_timeline(job_id)
    
    async def _insert_segment_record(self, job_id: str, segment: SegmentInfo):
        """Insert segment record into database."""
        stmt = insert(ProgressiveSegment).values(
            job_id=job_id,
            segment_id=segment.segment_id,
            start_time=segment.start_time,
            end_time=segment.end_time,
            status=segment.status.value
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _update_segment_status(self, job_id: str, segment_id: int, segment: SegmentInfo):
        """Update segment status in database."""
        from datetime import datetime
        
        stmt = update(ProgressiveSegment).where(
            ProgressiveSegment.job_id == job_id,
            ProgressiveSegment.segment_id == segment_id
        ).values(
            status=segment.status.value,
            nmt_result=segment.nmt_result,
            tts_audio_key=segment.tts_audio_key,
            error_message=segment.error_message,
            video_inserted_at=datetime.utcnow() if segment.status == SegmentStatus.MERGED else None
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _update_job_timeline(self, job_id: str, total_segments: int, completed_segments: int, video_url: Optional[str] = None, current_video_path: Optional[str] = None):
        """Update job record with timeline progress and current video path."""
        from app.jobs.models import Job
        from sqlalchemy import select
        
        # Get current job to update merge_timeline
        job_stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(job_stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            logger.error(f"[PROGRESSIVE] Job not found for timeline update | job_id={job_id}")
            return
        
        # Update basic fields
        update_values = {
            "segments_total": total_segments,
            "segments_completed": completed_segments,
            "current_video_url": video_url
        }
        
        # Update merge_timeline with current_video_path if provided
        if current_video_path is not None:
            merge_timeline = job.merge_timeline or {}
            merge_timeline["current_video_path"] = current_video_path
            update_values["merge_timeline"] = merge_timeline
            logger.info(f"[PROGRESSIVE] Saving current_video_path to DB | job={job_id} | path={current_video_path}")
        
        stmt = update(Job).where(Job.id == job_id).values(**update_values)
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _update_completion_tracking(self, job_id: str) -> float:
        """Update and return completion percentage."""
        timeline = self.active_timelines.get(job_id)
        if not timeline:
            return 0.0
        
        completed = sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.MERGED)
        completion_pct = timeline.completion_percentage
        
        await self._update_job_timeline(job_id, len(timeline.segments), completed, video_url=None)
        
        return completion_pct
    
    async def _download_tts_audio(self, tts_audio_key: str) -> Optional[Path]:
        """Download TTS audio from storage."""
        if not tts_audio_key:
            return None
        
        temp_dir = Path("/tmp/progressive_audio")
        temp_dir.mkdir(exist_ok=True)
        
        local_path = temp_dir / f"{uuid4().hex}.wav"
        
        try:
            # Download from MinIO/S3
            success = await self.storage_service.download(tts_audio_key, str(local_path))
            
            if success and local_path.exists() and local_path.stat().st_size > 0:
                return local_path
            else:
                logger.error(f"[PROGRESSIVE] Download failed or audio file is empty | key={tts_audio_key} | success={success}")
                return None
                
        except Exception as e:
            logger.error(f"[PROGRESSIVE] Failed to download TTS audio | key={tts_audio_key} | error={e}")
            return None
    
    async def _upload_current_video(self, job_id: str, timeline: VideoTimeline) -> Optional[str]:
        """Upload current video to storage and return URL."""
        if not timeline.current_video_path or not timeline.current_video_path.exists():
            return None
        
        try:
            # Upload to MinIO
            video_key = f"videos/{timeline.video_id}/progressive/{job_id}_current.mp4"
            await self.storage_service.upload_file(str(timeline.current_video_path), video_key)
            
            # Get signed URL
            video_url = await self.storage_service.get_file_url(video_key)
            
            # Update job record
            await self._update_job_timeline(job_id, len(timeline.segments), 
                                          sum(1 for s in timeline.segments.values() if s.status == SegmentStatus.MERGED),
                                          video_url)
            
            return video_url
            
        except Exception as e:
            logger.error(f"[PROGRESSIVE] Failed to upload current video | job={job_id} | error={e}")
            return None
    
    async def _get_current_video_url(self, job_id: str) -> Optional[str]:
        """Get current video URL from job record."""
        from app.jobs.models import Job
        
        stmt = select(Job.current_video_url).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    def _get_segments_by_status(self, timeline: VideoTimeline) -> Dict[str, int]:
        """Get count of segments by status."""
        status_counts = {}
        for status in SegmentStatus:
            status_counts[status.value] = sum(1 for s in timeline.segments.values() if s.status == status)
        return status_counts
    
    async def _find_latest_video_path(self, job_id: str) -> Optional[Path]:
        """Find the latest video file for a job."""
        video_dir = Path(f"/tmp/progressive_videos")
        if not video_dir.exists():
            return None
        
        # Look for video files for this job
        pattern = f"{job_id}_*.mp4"
        video_files = list(video_dir.glob(pattern))
        
        if not video_files:
            return None
        
        # Return the most recent file
        return max(video_files, key=lambda p: p.stat().st_mtime)
    
    async def _cleanup_old_video_versions(self, job_id: str, keep_count: int = 2):
        """Clean up old video versions, keeping only the most recent ones."""
        video_dir = Path(f"/tmp/progressive_videos")
        if not video_dir.exists():
            return
        
        pattern = f"{job_id}_*.mp4"
        video_files = sorted(video_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Delete files beyond keep_count
        for old_file in video_files[keep_count:]:
            try:
                old_file.unlink(missing_ok=True)
                logger.debug(f"[PROGRESSIVE] Cleaned up old video | file={old_file}")
            except Exception as e:
                logger.warning(f"[PROGRESSIVE] Failed to clean up old video | file={old_file} | error={e}")