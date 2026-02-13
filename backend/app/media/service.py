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
from app.media.models import Video, VideoStatus, MediaType
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

            # 2. Prepare file
            with tempfile.TemporaryDirectory() as temp_dir:
                local_video_path = Path(temp_dir) / "input_video"
                
                if isinstance(storage, S3StorageService):
                    async with storage.session.client("s3", endpoint_url=storage.endpoint_url, aws_access_key_id=storage.access_key, aws_secret_access_key=storage.secret_key) as s3:
                         await s3.download_file(storage.bucket_name, file_path_key, str(local_video_path))
                else:
                    abs_path = storage.get_absolute_path(file_path_key)
                    local_video_path = Path(abs_path) 

                # 3. Extract Metadata
                metadata = await ffmpeg.get_metadata(str(local_video_path))
                
                video.duration = metadata.duration
                video.width = metadata.width
                video.height = metadata.height
                video.size_bytes = metadata.size
                video.format = metadata.format
                video.codec = metadata.codec
                video.frame_rate = metadata.frame_rate
                
                # Metadata Done - Commit metadata
                await db.commit()
                await db.refresh(video)
                
                audio_key = None
                thumbnail_key = None
                
                logger.info(f"Media type: {video.media_type}")

                # Processing based on Media Type
                if video.media_type == MediaType.VIDEO:
                    # 4. Extract Audio
                    if metadata.audio_present:
                        logger.info("Audio present, extracting...")
                        
                        audio_filename = f"{video_id}.mp3"
                        audio_local_path = Path(temp_dir) / audio_filename
                        success = await ffmpeg.extract_audio(str(local_video_path), str(audio_local_path))
                        
                        logger.info(f"Audio extraction success: {success}")
                        if success and audio_local_path.exists():
                             audio_key = await storage.save_file(str(audio_local_path), directory=f"audio/{video.user_id}")
                    
                    # 5. Generate Thumbnail
                    thumbnail_filename = f"{video_id}.jpg"
                    thumbnail_local_path = Path(temp_dir) / thumbnail_filename
                    success = await ffmpeg.generate_thumbnail(str(local_video_path), str(thumbnail_local_path))
                    if success:
                        thumbnail_key = await storage.save_file(str(thumbnail_local_path), directory=f"thumbnails/{video.user_id}")
                        
                    video.audio_path = audio_key
                    video.thumbnail_path = thumbnail_key

                elif video.media_type == MediaType.AUDIO:
                     # Audio specific steps if any
                     # If it's pure audio, we might want to skip extraction but maybe validate?
                     logger.info("Processing AUDIO type")

                elif video.media_type == MediaType.TEXT:
                     logger.info("Processing TEXT type")

                video.status = VideoStatus.COMPLETED
                await db.commit()
                logger.info(f"Processing completed for {video.media_type} {video_id}")

        except Exception as e:
            logger.error(f"Processing failed for video {video_id}: {e}")
            video = await db.get(Video, video_id) # Re-fetch to be safe
            if video:
                video.status = VideoStatus.FAILED
                video.error_message = str(e)
                await db.commit()



async def process_video_hls_task(video_id: str, file_path_key: str):
    """
    Background task logic for HLS processing.
    """
    logger.info(f"Starting HLS processing for video {video_id}")
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
                output_hls_dir = Path(temp_dir) / "hls"
                output_hls_dir.mkdir()
                
                # Check if storage is S3 or Local
                if isinstance(storage, S3StorageService):
                    # Download from S3
                    async with storage.session.client("s3", 
                        endpoint_url=storage.endpoint_url,
                        aws_access_key_id=storage.access_key,
                        aws_secret_access_key=storage.secret_key
                    ) as s3:
                         await s3.download_file(storage.bucket_name, file_path_key, str(local_video_path))
                else:
                    abs_path = storage.get_absolute_path(file_path_key)
                    local_video_path = Path(abs_path) 

                # 3. Generate HLS
                success = await ffmpeg.generate_hls(str(local_video_path), str(output_hls_dir))
                if not success:
                    raise MediaProcessingError("HLS Generation failed")

                # 4. Upload HLS Directory
                # We upload to videos/{user_id}/{video_id}/hls/
                hls_key_prefix = await storage.upload_directory(str(output_hls_dir), f"videos/{video.user_id}/{video.id}/hls")
                
                # Index file is at prefix/index.m3u8
                hls_playlist_key = f"{hls_key_prefix}/index.m3u8"
                
                # 5. Extract Metadata (from original)
                metadata = await ffmpeg.get_metadata(str(local_video_path))
                
                # Update DB with metadata
                video.duration = metadata.duration
                video.width = metadata.width
                video.height = metadata.height
                video.size_bytes = metadata.size
                video.format = "hls"
                video.codec = metadata.codec
                video.frame_rate = metadata.frame_rate
                
                # 6. Extract Audio (Optional, kept for consistency)
                audio_key = None
                if metadata.audio_present:
                    audio_filename = f"{video_id}.mp3"
                    audio_local_path = Path(temp_dir) / audio_filename
                    success = await ffmpeg.extract_audio(str(local_video_path), str(audio_local_path))
                    if success:
                         audio_key = await storage.save_file(str(audio_local_path), directory=f"audio/{video.user_id}")

                # 7. Generate Thumbnail
                thumbnail_key = None
                thumbnail_filename = f"{video_id}.jpg"
                thumbnail_local_path = Path(temp_dir) / thumbnail_filename
                success = await ffmpeg.generate_thumbnail(str(local_video_path), str(thumbnail_local_path))
                if success:
                    thumbnail_key = await storage.save_file(str(thumbnail_local_path), directory=f"thumbnails/{video.user_id}")

                # Update File Path to point to the m3u8 playlist instead of the raw file
                # Optional: Delete the raw file from storage if we only want to keep HLS?
                # For now, let's keep the raw file as a "source" but update the main path to HLS.
                # actually, user wants "store as chunk".
                # video.file_path was the raw uploads. 
                # Let's update file_path to be the HLS playlist.
                video.file_path = hls_playlist_key
                video.audio_path = audio_key
                video.thumbnail_path = thumbnail_key
                video.status = VideoStatus.COMPLETED
                await db.commit()
                logger.info(f"HLS Processing completed for video {video_id}")

        except Exception as e:
            logger.error(f"HLS Processing failed for video {video_id}: {e}")
            video = await db.get(Video, video_id)
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
            raise HTTPException(status_code=400, detail="Invalid file type. Expected video.")
            
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
            size_bytes=file.size,
            media_type=MediaType.VIDEO
        )
        self.db.add(new_video)
        await self.db.commit()
        await self.db.refresh(new_video)
        
        # 4. Populate URL for immediate response
        if new_video.file_path:
            new_video.url = self.storage.get_url(new_video.file_path)

        # 5. Task
        background_tasks.add_task(process_video_task, new_video.id, file_path_key)
        
        return new_video

    async def upload_audio(
        self, 
        user_id: int, 
        file: UploadFile, 
        background_tasks: BackgroundTasks
    ) -> Video:
        # 1. Validation
        # Strict check: Must be audio MIME type AND not be a video disguised
        if not file.content_type.startswith("audio/"):
            # Check for specific edge cases where browser might send application/octet-stream for audio
            # But here we want to STRICTLY forbid video/text
            if file.content_type.startswith("video/") or file.content_type.startswith("text/"):
                 raise HTTPException(status_code=400, detail="Invalid file type. Expected audio.")
            
            # If completely unknown, maybe check extension?
            # But let's enforce audio/ for now as per requirement.
            # Actually, user asked "if send file audio as type but the file found other like mp4".
            # This implies content-type says "audio/..." but extension is ".mp4".
            # Browsers set content-type based on extension mostly.
            # If a user manually renames .mp4 to .mp3, browser might send audio/mp3.
            # Backend validation usually inspects file header (magic bytes) which is expensive/complex here without magic library.
            # But we can check extension + MIME consistency.
            pass

        if not file.content_type.startswith("audio/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Expected audio.")

        # Extra Check: Reject if extension is clearly video
        filename = (file.filename or "").lower()
        if filename.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
             raise HTTPException(status_code=400, detail="Invalid file extension. Expected audio file.")

        # 2. Upload
        file_path_key = await self.storage.save(file, directory=f"audio/{user_id}")
        
        # 3. Create DB Record
        new_audio = Video(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=file.filename or "Untitled",
            original_filename=file.filename,
            file_path=file_path_key,
            status=VideoStatus.PENDING,
            size_bytes=file.size,
            media_type=MediaType.AUDIO
        )
        self.db.add(new_audio)
        await self.db.commit()
        await self.db.refresh(new_audio)
        
        # 4. Populate URL
        if new_audio.file_path:
            new_audio.url = self.storage.get_url(new_audio.file_path)

        # 5. Task
        background_tasks.add_task(process_video_task, new_audio.id, file_path_key)
        
        return new_audio

    async def upload_text(
        self, 
        user_id: int, 
        file: UploadFile, 
        background_tasks: BackgroundTasks
    ) -> Video:
        # 1. Validation
        if file.content_type.startswith("video/") or file.content_type.startswith("audio/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Expected text.")
             
        if not (file.content_type.startswith("text/") or file.filename.endswith(".txt")):
             raise HTTPException(status_code=400, detail="Invalid file type. Expected text.")

        # 2. Upload
        file_path_key = await self.storage.save(file, directory=f"text/{user_id}")
        
        # 3. Create DB Record
        new_text = Video(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=file.filename or "Untitled",
            original_filename=file.filename,
            file_path=file_path_key,
            status=VideoStatus.COMPLETED, # Text usually doesn't need heavy processing unless we do translation immediately
            size_bytes=file.size,
            media_type=MediaType.TEXT
        )
        self.db.add(new_text)
        await self.db.commit()
        await self.db.refresh(new_text)
        
        # 4. Populate URL
        if new_text.file_path:
            new_text.url = self.storage.get_url(new_text.file_path)
            
        return new_text

    async def upload_video_hls(
        self, 
        user_id: int, 
        file: UploadFile, 
        background_tasks: BackgroundTasks
    ) -> Video:
        # 1. Validation
        if not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail="Invalid file type.")
            
        # 2. Upload Raw Source first
        file_path_key = await self.storage.save(file, directory=f"videos/{user_id}/source")
        
        # 3. Create DB Record
        new_video = Video(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=file.filename or "Untitled",
            original_filename=file.filename,
            file_path=file_path_key, # Temporarily points to raw source
            status=VideoStatus.PENDING,
            size_bytes=file.size 
        )
        self.db.add(new_video)
        await self.db.commit()
        await self.db.refresh(new_video)
        
        # 4. Populate URL
        if new_video.file_path:
            new_video.url = self.storage.get_url(new_video.file_path)

        # 5. Task - Use the HLS task
        background_tasks.add_task(process_video_hls_task, new_video.id, file_path_key)
        
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
