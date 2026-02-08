import os
import uuid
import logging
import asyncio
import tempfile
from datetime import datetime
from typing import List, Optional
from fastapi import UploadFile, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.media.models import Video, VideoStatus
from app.media.storage import get_storage_service, S3StorageService
from app.media.ffmpeg_service import FFmpegService, MediaProcessingError
from app.core.db import AsyncSessionLocal
from pathlib import Path

logger = logging.getLogger(__name__)

async def process_video_task(video_id: str, file_path_key: str):
    """
    Background task logic. It creates its own DB session.
    """
    logger.info(f"Starting processing for video {video_id}")
    storage = get_storage_service()
    ffmpeg = FFmpegService()
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. Update status to PROCESSING
            video = await db.get(Video, video_id)
            if not video:
                logger.error(f"Video {video_id} not found during processing")
                return
            
            video.status = VideoStatus.PROCESSING
            await db.commit()

            # 2. Prepare file for ffmpeg (Download if S3)
            with tempfile.TemporaryDirectory() as temp_dir:
                local_video_path = Path(temp_dir) / "input_video"
                
                # Check if storage is S3 or Local
                # If S3, we must download. If Local, we could use path effectively if we knew absolute path mapping.
                # safely: always download/copy to temp for processing to avoid lock issues or network latency during processing
                
                if isinstance(storage, S3StorageService):
                    # Download from S3
                    async with storage.session.client("s3", 
                        endpoint_url=storage.endpoint_url,
                        aws_access_key_id=storage.access_key,
                        aws_secret_access_key=storage.secret_key
                    ) as s3:
                         await s3.download_file(storage.bucket_name, file_path_key, str(local_video_path))
                else:
                    # Local storage: copy or symlink? Copy is safer.
                    # Use get_absolute_path if available
                    abs_path = storage.get_absolute_path(file_path_key)
                    # We can use it directly? Yes, but ffmpeg might be slow.
                    local_video_path = Path(abs_path) 

                # 3. Extract Metadata
                metadata = await ffmpeg.get_metadata(str(local_video_path))
                
                # Update DB with metadata
                video.duration = metadata.duration
                video.width = metadata.width
                video.height = metadata.height
                video.size_bytes = metadata.size
                video.format = metadata.format
                video.codec = metadata.codec
                video.frame_rate = metadata.frame_rate
                
                # 4. Extract Audio
                audio_key = None
                if metadata.audio_present:
                    audio_filename = f"{video_id}.mp3"
                    audio_local_path = Path(temp_dir) / audio_filename
                    success = await ffmpeg.extract_audio(str(local_video_path), str(audio_local_path))
                    if success:
                         # Upload Audio
                         audio_key = await storage.save_file(str(audio_local_path), directory=f"audio/{video.user_id}")

                # 5. Generate Thumbnail
                thumbnail_key = None
                thumbnail_filename = f"{video_id}.jpg"
                thumbnail_local_path = Path(temp_dir) / thumbnail_filename
                success = await ffmpeg.generate_thumbnail(str(local_video_path), str(thumbnail_local_path))
                if success:
                    thumbnail_key = await storage.save_file(str(thumbnail_local_path), directory=f"thumbnails/{video.user_id}")

                video.audio_path = audio_key
                video.thumbnail_path = thumbnail_key
                video.status = VideoStatus.COMPLETED
                await db.commit()
                logger.info(f"Processing completed for video {video_id}")

        except Exception as e:
            logger.error(f"Processing failed for video {video_id}: {e}")
            video = await db.get(Video, video_id) # Re-fetch to be safe
            if video:
                video.status = VideoStatus.FAILED
                video.error_message = str(e)
                await db.commit()


class VideoService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_service()

    async def upload_video(
        self, 
        user_id: int, 
        file: UploadFile, 
        background_tasks: BackgroundTasks
    ) -> Video:
        # 1. Validation
        if not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail="Invalid file type.")
            
        # 2. Upload
        file_path_key = await self.storage.save(file, directory=f"videos/{user_id}")
        
        # 3. Create DB Record
        new_video = Video(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=file.filename or "Untitled",
            original_filename=file.filename,
            file_path=file_path_key,
            status=VideoStatus.PENDING,
            size_bytes=file.size 
        )
        self.db.add(new_video)
        await self.db.commit()
        await self.db.refresh(new_video)
        
        # 4. Task
        background_tasks.add_task(process_video_task, new_video.id, file_path_key)
        
        return new_video

    async def get_user_videos(self, user_id: int) -> List[Video]:
        result = await self.db.execute(select(Video).where(Video.user_id == user_id))
        videos = result.scalars().all()
        for video in videos:
             if video.file_path:
                 video.url = self.storage.get_url(video.file_path)
             if video.thumbnail_path:
                 video.thumbnail_url = self.storage.get_url(video.thumbnail_path)
             if video.audio_path:
                 video.audio_url = self.storage.get_url(video.audio_path)
        return videos

    async def get_video(self, video_id: str) -> Optional[Video]:
        result = await self.db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video:
             if video.file_path:
                 video.url = self.storage.get_url(video.file_path)
             if video.thumbnail_path:
                 video.thumbnail_url = self.storage.get_url(video.thumbnail_path)
             if video.audio_path:
                 video.audio_url = self.storage.get_url(video.audio_path)
        return video

    async def delete_video(self, video_id: str, user_id: int) -> bool:
        """
        Delete a video record and its associated files from storage.
        Acts like an Observer: when the row is deleted, related files are unlinked.
        """
        # 1. Get video
        video = await self.get_video(video_id)
        if not video:
            return False
            
        if video.user_id != user_id:
            # Authorization check
            # Raise exception so we can catch it in router with correct 403 status
            raise HTTPException(status_code=403, detail="Not authorized to delete this video")

        # 2. Cleanup Files (Observer-like behavior: Pre-deletion or Post-deletion)
        # We'll save paths first because video object might be detached or empty after delete?
        # Typically objects are still available in session until commit.
        # But safest is to extract paths before delete.
        
        file_path_key = video.file_path
        thumbnail_key = video.thumbnail_path
        audio_key = video.audio_path
        
        # 3. Delete from DB
        try:
            await self.db.delete(video)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error deleting video from DB: {e}")
            return False

        # 4. Cleanup Files after successful DB delete
        storage = self.storage
        
        if file_path_key:
            await storage.delete(file_path_key)
        
        if thumbnail_key:
            await storage.delete(thumbnail_key)
            
        if audio_key:
            await storage.delete(audio_key)
            
        logger.info(f"Video {video_id} and associated files deleted.")
        return True
