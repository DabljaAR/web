import os
import uuid
import logging
import asyncio
import tempfile
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import UploadFile, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, exists, func, not_
from app.media.models import Video, VideoStatus, MediaType
from app.media.storage import get_storage_service, S3StorageService
from app.media.ffmpeg_service import FFmpegService, MediaProcessingError
from app.core.db import AsyncSessionLocal
from app.jobs.models import Job, JobStatus, JobType
from pathlib import Path

logger = logging.getLogger(__name__)

async def process_video_task(video_id: str, file_path_key: str, options: dict = None):
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

                # 6. Trigger pipeline if requested
                if options and video.media_type in [MediaType.VIDEO, MediaType.AUDIO]:
                    output_type = options.get("output_type", "fullDubbing")
                    logger.info(f"Triggering pipeline with output_type={output_type} for {video_id}")
                    

                    # Create VideoTask (single result record for this pipeline run)
                    from app.tasks.models import VideoTask, TaskStatus
                    video_task_id = str(uuid.uuid4())
                    video_task = VideoTask(
                        id=video_task_id,
                        video_id=video_id,
                        user_id=video.user_id,
                        source_lang=options.get("source_lang", "auto"),
                        target_lang=options.get("target_lang", "arb_Arab"),
                        output_type=output_type,
                        num_beams=int(options.get("num_beams", 5)),
                        english_ratio_threshold=float(options.get("english_ratio_threshold", 0.5)),
                        status=TaskStatus.QUEUED,
                    )
                    db.add(video_task)

                    # Create the initial STT job
                    stt_job_id = str(uuid.uuid4())
                    stt_job = Job(
                        id=stt_job_id,
                        video_id=video_id,
                        user_id=video.user_id,
                        job_type=JobType.STT_TRANSCRIBE,
                        status=JobStatus.QUEUED,
                        input_data={
                            **options,
                            "task_id": video_task_id,
                            "audio_key": audio_key or file_path_key,
                            "target_lang": "ar",
                        }
                    )
                    video_task.root_job_id = stt_job_id
                    db.add(stt_job)
                    await db.commit()

                    # Enqueue the STT task directly
                    from app.jobs.tasks.pipeline import stt_transcribe
                    celery_result = stt_transcribe.apply_async(
                        kwargs={
                            "job_id": stt_job_id,
                            "video_id": video_id,
                            "target_lang": stt_job.input_data.get("target_lang", "ar")
                        },
                        task_id=stt_job_id,
                    )
                    stt_job.celery_task_id = celery_result.id
                    db.add(stt_job)
                    await db.commit()

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
        background_tasks: BackgroundTasks,
        options: dict = None
    ) -> Video:
        # 1. Validation
        content_type = file.content_type or ""
        if not content_type.startswith("video/"):
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
            new_video.url = await self.storage.get_url(new_video.file_path)

        # 5. Task
        # 5. Task
        background_tasks.add_task(process_video_task, new_video.id, file_path_key, options=options)
        
        return new_video

    async def upload_audio(
        self, 
        user_id: int, 
        file: UploadFile, 
        background_tasks: BackgroundTasks,
        options: dict = None
    ) -> Video:
        # 1. Validation
        content_type = file.content_type or ""
        if not content_type.startswith("audio/"):
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
            new_audio.url = await self.storage.get_url(new_audio.file_path)

        # 5. Task
        # 5. Task
        background_tasks.add_task(process_video_task, new_audio.id, file_path_key, options=options)
        
        return new_audio

    async def upload_text(
        self,
        user_id: int,
        file: UploadFile,
        background_tasks: BackgroundTasks,
        options: dict = None
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
            new_text.url = await self.storage.get_url(new_text.file_path)
            
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
            new_video.url = await self.storage.get_url(new_video.file_path)

        # 5. Task - Use the HLS task
        background_tasks.add_task(process_video_hls_task, new_video.id, file_path_key)
        
        return new_video

    async def reprocess_existing_media(self, user_id: int, video_id: str, options: dict | None = None):
        """Create a fresh STT pipeline job for an existing uploaded media file."""

        media = await self.db.get(Video, video_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        if media.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to process this media")

        if media.media_type not in [MediaType.VIDEO, MediaType.AUDIO]:
            raise HTTPException(status_code=400, detail="Only video/audio can be reprocessed")

        selected_options = options or {}
        input_options = {
            "output_type": selected_options.get("output_type", "fullDubbing"),
            "domain": selected_options.get("domain", "general"),
            "voice": selected_options.get("voice", "male1"),
            "translation_style": selected_options.get("translation_style", "neutral"),
            "target_lang": "ar",
            "audio_key": media.audio_path or media.file_path,
        }

        # Create VideoTask (single result record for this pipeline run)
        from app.tasks.models import VideoTask, TaskStatus
        video_task = VideoTask(
            id=str(uuid.uuid4()),
            video_id=media.id,
            user_id=media.user_id,
            source_lang=selected_options.get("source_lang", "auto"),
            target_lang=input_options["target_lang"],
            output_type=input_options["output_type"],
            num_beams=int(selected_options.get("num_beams", 5)),
            english_ratio_threshold=float(selected_options.get("english_ratio_threshold", 0.5)),
            status=TaskStatus.QUEUED,
        )
        self.db.add(video_task)
        await self.db.flush()   # get video_task.id without committing

        input_options["task_id"] = video_task.id

        stt_job = Job(
            id=str(uuid.uuid4()),
            video_id=media.id,
            user_id=media.user_id,
            job_type=JobType.STT_TRANSCRIBE,
            status=JobStatus.QUEUED,
            input_data=input_options,
        )
        video_task.root_job_id = stt_job.id
        self.db.add(stt_job)
        await self.db.commit()
        await self.db.refresh(stt_job)

        # Enqueue the STT task directly
        from app.jobs.tasks.pipeline import stt_transcribe
        celery_result = stt_transcribe.apply_async(
            kwargs={
                "job_id": stt_job.id,
                "video_id": media.id,
                "target_lang": input_options["target_lang"]
            },
            task_id=stt_job.id,
        )
        stt_job.celery_task_id = celery_result.id
        self.db.add(stt_job)
        await self.db.commit()

        return stt_job


    async def get_user_videos(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        sort_by: str = "date-desc",
        date_range: str = "allTime",
        status: Optional[str] = None,
        media_type: Optional[str] = None,
    ):
        query = select(Video).where(Video.user_id == user_id)

        # Status Filter
        if status and status != 'all':
            requested_status = status.upper()

            active_statuses = [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING]
            active_job_exists = exists(
                select(Job.id).where(
                    and_(
                        Job.video_id == Video.id,
                        Job.status.in_(active_statuses)
                    )
                )
            )

            if requested_status in ['PROCESSING', 'PENDING', 'QUEUED', 'RETRYING']:
                query = query.where(
                    or_(
                        Video.status.in_([VideoStatus.PENDING, VideoStatus.PROCESSING]),
                        active_job_exists
                    )
                )
            else:
                query = query.where(Video.status == requested_status)
        
        # Media Type Filter
        if media_type and media_type != 'all':
            query = query.where(Video.media_type == media_type.upper())
        
        # Search filter
        if search:
            search = search.strip()
            if search:
                search_query = f"%{search}%"
                query = query.where(
                    or_(
                        Video.title.ilike(search_query),
                        Video.original_filename.ilike(search_query)
                    )
                )

        # Date Range Filter
        if date_range and date_range != 'allTime':
             now = datetime.utcnow()
             today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
             
             if date_range == 'today':
                 query = query.where(Video.created_at >= today_start)
             elif date_range == 'yesterday':
                 yesterday_start = today_start - timedelta(days=1)
                 query = query.where(Video.created_at >= yesterday_start, Video.created_at < today_start)
             elif date_range == 'thisWeek':
                 week_start = today_start - timedelta(days=today_start.weekday())
                 query = query.where(Video.created_at >= week_start)
             elif date_range == 'thisMonth':
                 month_start = today_start.replace(day=1)
                 query = query.where(Video.created_at >= month_start)
             elif date_range == 'lastMonth':
                 this_month_start = today_start.replace(day=1)
                 last_month_end = this_month_start - timedelta(days=1)
                 last_month_start = last_month_end.replace(day=1)
                 query = query.where(Video.created_at >= last_month_start, Video.created_at < this_month_start)
             elif date_range == 'last7Days':
                 query = query.where(Video.created_at >= now - timedelta(days=7))
             elif date_range == 'last30Days':
                 query = query.where(Video.created_at >= now - timedelta(days=30))
             elif date_range == 'last90Days':
                 query = query.where(Video.created_at >= now - timedelta(days=90))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0
        
        # Count completed
        completed_query = select(func.count()).select_from(
            query.where(Video.status == VideoStatus.COMPLETED).subquery()
        )
        total_completed = await self.db.scalar(completed_query) or 0
        
        # Count failed
        failed_query = select(func.count()).select_from(
            query.where(Video.status == VideoStatus.FAILED).subquery()
        )
        total_failed = await self.db.scalar(failed_query) or 0
        
        # Sorting
        if sort_by == 'date-desc' or sort_by == 'dateNewest':
            query = query.order_by(Video.created_at.desc())
        elif sort_by == 'date-asc' or sort_by == 'dateOldest':
            query = query.order_by(Video.created_at.asc())
        elif sort_by == 'size-desc':
            query = query.order_by(Video.size_bytes.desc().nulls_last())
        elif sort_by == 'size-asc':
            query = query.order_by(Video.size_bytes.asc().nulls_last())
        elif sort_by == 'duration-desc':
            query = query.order_by(Video.duration.desc().nulls_last())
        elif sort_by == 'duration-asc':
            query = query.order_by(Video.duration.asc().nulls_last())
        elif sort_by == 'name-asc' or sort_by == 'nameAZ':
            query = query.order_by(Video.title.asc())
        elif sort_by == 'name-desc' or sort_by == 'nameZA':
            query = query.order_by(Video.title.desc())
        else:
            query = query.order_by(Video.created_at.desc())

        # Pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        videos = result.scalars().all()

        # Fetch all jobs for the current page videos once, then enrich each row.
        jobs_by_video = {}
        video_ids = [v.id for v in videos]
        if video_ids:
            jobs_result = await self.db.execute(
                select(Job)
                .where(Job.video_id.in_(video_ids))
                .order_by(Job.created_at.desc())
            )
            all_jobs = jobs_result.scalars().all()
            for job in all_jobs:
                jobs_by_video.setdefault(job.video_id, []).append(job)
        
        # Process URLs (same as before)
        for video in videos:
             if video.file_path:
                 video.url = await self.storage.get_url(video.file_path, filename=video.original_filename)
             if video.thumbnail_path:
                 try:
                     video.thumbnail_url = await self.storage.get_url(video.thumbnail_path)
                 except Exception as e:
                     print(f"Error fetching thumbnail url: {e}")
             if video.audio_path:
                 # Derive audio filename from original filename
                 audio_name = video.original_filename
                 if audio_name:
                     base_name = os.path.splitext(audio_name)[0]
                     audio_name = f"{base_name}.mp3"
                 else:
                     audio_name = f"{video.title}.mp3"
                 try:
                    video.audio_url = await self.storage.get_url(video.audio_path, filename=audio_name)
                 except Exception as e:
                    print(f"Error fetching audio url: {e}")

             # Enrich with job-based fields (for history processing state + text preview)
             page_jobs = jobs_by_video.get(video.id, [])
             active_jobs = [j for j in page_jobs if j.status in [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING]]
             completed_jobs = [j for j in page_jobs if j.status == JobStatus.COMPLETED]

             video.has_active_job = len(active_jobs) > 0
             if active_jobs:
                 newest_active = active_jobs[0]
                 video.active_job_status = newest_active.status.value
                 video.active_job_progress = max((j.progress or 0.0) for j in active_jobs)
             else:
                 video.active_job_status = None
                 video.active_job_progress = 0.0

             transcript_url = None
             translation_url = None
             for job in completed_jobs:
                 if not job.output_data:
                     continue

                 if job.job_type == JobType.STT_TRANSCRIBE:
                     if isinstance(job.output_data.get("segments"), list) and job.output_data.get("segments"):
                         if not transcript_url:
                             transcript_url = f"/jobs/{job.id}/preview?kind=transcript"
                         # If this STT job also has translation data, use it for translation_url
                         if not translation_url and (job.output_data.get("translated_transcript") or any(s.get("translated_text") for s in job.output_data.get("segments", []))):
                             translation_url = f"/jobs/{job.id}/preview?kind=translation"
                 
                 if not translation_url and job.job_type == JobType.NMT_TRANSLATE:
                     if isinstance(job.output_data.get("segments"), list) and job.output_data.get("segments"):
                         translation_url = f"/jobs/{job.id}/preview?kind=translation"

                 if transcript_url and translation_url:
                     break

             video.transcript_url = transcript_url
             video.translation_url = translation_url
                 
        pages = (total + limit - 1) // limit if limit > 0 else 0
        
        response_data = {
            "items": videos,
            "total": total,
            "page": page,
            "size": limit,
            "pages": pages,
            "total_completed": total_completed,
            "total_failed": total_failed
        }
        return response_data

    async def get_dashboard_jobs(self, user_id: int) -> dict:

        # 1. Fetch active media processing (Videos marked PENDING/PROCESSING)
        query_active_videos = select(Video).where(
            Video.user_id == user_id,
            Video.status.in_([VideoStatus.PENDING, VideoStatus.PROCESSING])
        ).order_by(Video.created_at.desc())
        
        result_active_videos = await self.db.execute(query_active_videos)
        active_videos = result_active_videos.scalars().all()

        # 2. Fetch active background Jobs (STT, NMT, TTS, etc.)
        query_active_jobs = select(Job).where(
            Job.user_id == user_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING])
        ).order_by(Job.created_at.desc())
        
        result_active_jobs = await self.db.execute(query_active_jobs)
        active_jobs = result_active_jobs.scalars().all()
        
        # Merge them for the "Processing" UI
        # We wrap them in a consistent format
        active_items = []
        for v in active_videos:
             active_items.append({
                 "id": v.id,
                 "video_id": v.id,
                 "name": v.title or v.original_filename,
                 "status": v.status,
                 "type": "MEDIA_PROCESS",
                 "progress": 0.0,
                 "created_at": v.created_at
             })
        
        for j in active_jobs:
             # Check if we already have this video as processing (Media Process is often followed by Jobs)
             # but we want to show everything.
             active_items.append({
                 "id": j.id,
                 "video_id": j.video_id,
                 "name": f"{j.job_type.value}: {j.id[:8]}", # Simple label
                 "status": j.status,
                 "type": j.job_type,
                 "progress": j.progress,
                 "created_at": j.created_at
             })

        # Sort combined active items
        active_items.sort(key=lambda x: x["created_at"], reverse=True)

        # 3. Fetch recent completed items (Videos)
        query_recent_videos = select(Video).where(
             Video.user_id == user_id,
             Video.status.in_([VideoStatus.COMPLETED, VideoStatus.FAILED])
        ).order_by(Video.created_at.desc()).limit(10)
        
        result_recent_videos = await self.db.execute(query_recent_videos)
        recent_videos = result_recent_videos.scalars().all()
        
        # 4. For each recent video, find its completed Jobs (latest first)
        # to see if we have transcripts or translations.
        processed_recent = []
        for v in recent_videos:
             video_data = {
                 "id": v.id,
                 "title": v.title,
                 "original_filename": v.original_filename,
                 "status": v.status,
                 "media_type": v.media_type,
                 "created_at": v.created_at,
                 "url": await self.storage.get_url(v.file_path, filename=v.original_filename) if v.file_path else None,
                 "thumbnail_url": await self.storage.get_url(v.thumbnail_path) if v.thumbnail_path else None,
                 "audio_url": None
             }

             if v.audio_path:
                  audio_name = v.original_filename
                  if audio_name:
                      base_name = os.path.splitext(audio_name)[0]
                      audio_name = f"{base_name}.mp3"
                  video_data["audio_url"] = await self.storage.get_url(v.audio_path, filename=audio_name)

             # Get jobs for this video
             j_query = select(Job).where(Job.video_id == v.id).order_by(Job.completed_at.desc())
             j_result = await self.db.execute(j_query)
             jobs = j_result.scalars().all()
             
             video_data["jobs"] = []
             for j in jobs:
                 job_entry = {
                     "id": j.id,
                     "type": j.job_type,
                     "status": j.status,
                     "completed_at": j.completed_at
                 }
                 if j.status == JobStatus.COMPLETED and j.output_data:
                       if j.job_type == JobType.STT_TRANSCRIBE and j.output_data.get("segments"):
                           job_entry["transcript_url"] = f"/jobs/{j.id}/preview?kind=transcript"
                           # If this STT job also has translation data
                           if j.output_data.get("translated_transcript") or any(s.get("translated_text") for s in j.output_data.get("segments", [])):
                               job_entry["translation_url"] = f"/jobs/{j.id}/preview?kind=translation"
                       if j.job_type == JobType.NMT_TRANSLATE and j.output_data.get("segments"):
                           job_entry["translation_url"] = f"/jobs/{j.id}/preview?kind=translation"
                 video_data["jobs"].append(job_entry)
             
             processed_recent.append(video_data)
            
        return {
            "active": active_items,
            "recent": processed_recent
        }


    async def get_video(self, video_id: str) -> Optional[Video]:
        result = await self.db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video:
             if video.file_path:
                 video.url = await self.storage.get_url(video.file_path, filename=video.original_filename)
             if video.thumbnail_path:
                 video.thumbnail_url = await self.storage.get_url(video.thumbnail_path)
             if video.audio_path:
                 # Derive audio filename from original filename
                 audio_name = video.original_filename
                 if audio_name:
                     base_name = os.path.splitext(audio_name)[0]
                     audio_name = f"{base_name}.mp3"
                 else:
                     audio_name = f"{video.title}.mp3"
                 video.audio_url = await self.storage.get_url(video.audio_path, filename=audio_name)
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
            logger.info(f"Attempting to delete video {video_id} from DB")
            await self.db.delete(video)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error deleting video {video_id} from DB: {e}")
            await self.db.rollback()
            return False

        storage = self.storage
        
        try:
            if file_path_key:
                logger.info(f"Deleting file {file_path_key} from storage")
                await storage.delete(file_path_key)
            
            if thumbnail_key:
                logger.info(f"Deleting thumbnail {thumbnail_key} from storage")
                await storage.delete(thumbnail_key)
                
            if audio_key:
                logger.info(f"Deleting audio {audio_key} from storage")
                await storage.delete(audio_key)
        except Exception as e:
            logger.error(f"Error cleaning up files for video {video_id}: {e}")
            # Don't fail the request if file cleanup fails, as DB record is gone.
            
        logger.info(f"Video {video_id} and associated files deleted.")
        return True

    async def delete_user_media(self, user_id: int):
        """
        Delete all media records and associated files for a specific user.
        This should be called during user account deletion.
        """
        # 1. Fetch all videos for the user
        result = await self.db.execute(select(Video).where(Video.user_id == user_id))
        videos = result.scalars().all()
        
        if not videos:
            logger.info(f"No media found for user {user_id}")
            return
            
        logger.info(f"Found {len(videos)} media items to delete for user {user_id}")
        
        # 2. Collect all keys for deletion
        keys_to_delete = []
        for video in videos:
            if video.file_path:
                keys_to_delete.append(video.file_path)
            if video.thumbnail_path:
                keys_to_delete.append(video.thumbnail_path)
            if video.audio_path:
                keys_to_delete.append(video.audio_path)
        
        # 3. Delete from storage
        for key in keys_to_delete:
            try:
                logger.info(f"Deleting user media file: {key}")
                await self.storage.delete(key)
            except Exception as e:
                logger.error(f"Failed to delete file {key} during user media cleanup: {e}")
        
        # Note: DB records will be deleted by cascade when user is deleted
        logger.info(f"Successfully cleaned up media files for user {user_id}")