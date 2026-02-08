from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.models import User
from app.core.services import UserService 
from app.media.models import Video
from app.media.schemas import VideoResponse, VideoCreate
from app.media.service import VideoService

# Note: We need a way to get the current user. Assuming app.core.dependencies or similar exists.
# I'll check existing auth dependencies.

from app.core.auth import get_current_user

router = APIRouter(prefix="/videos", tags=["Media"])


async def get_video_service(db: AsyncSession = Depends(get_db)) -> VideoService:
    return VideoService(db)

@router.post("/upload", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a video file.
    """
    return await service.upload_video(current_user.user_id, file, background_tasks)

@router.get("/", response_model=List[VideoResponse])
async def list_videos(
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    List all videos for the current user.
    """
    return await service.get_user_videos(current_user.user_id)

@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    video = await service.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this video")
    return video

@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a video by ID. This will remove the video record from the database 
    and delete the associated video, thumbnail, and audio files from storage (Observer-like behavior).
    """
    try:
        success = await service.delete_video(video_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Video not found")
    except HTTPException as e:
        raise e
    except Exception as e:
        # Log unexpected errors
        print(f"Error deleting video: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
    return None
