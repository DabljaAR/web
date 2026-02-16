from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.models import User
from app.core.services import UserService 
from app.media.models import Video
from app.core.auth import get_current_user
from app.media.schemas import VideoResponse, VideoCreate, VideoUploadResponse, PaginatedVideoResponse, DashboardResponse
from app.media.service import VideoService

router = APIRouter(
    prefix="/videos",
    tags=["Media"],
    dependencies=[Depends(get_current_user)]
)


async def get_video_service(db: AsyncSession = Depends(get_db)) -> VideoService:
    return VideoService(db)

@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a video file.
    """
    video = await service.upload_video(current_user.user_id, file, background_tasks)
    return VideoUploadResponse(id=video.id, status=video.status)

@router.post("/upload/audio", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Upload an audio file.
    """
    audio = await service.upload_audio(current_user.user_id, file, background_tasks)
    return VideoUploadResponse(id=audio.id, status=audio.status)

@router.post("/upload/text", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_text(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a text file.
    """
    text = await service.upload_text(current_user.user_id, file, background_tasks)
    return VideoUploadResponse(id=text.id, status=text.status)

@router.post("/upload/hls", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video_hls(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a video file and process it into HLS (HTTP Live Streaming) chunks.
    This creates an .m3u8 playlist and .ts segment files in storage.
    """
    video = await service.upload_video_hls(current_user.user_id, file, background_tasks)
    return VideoUploadResponse(id=video.id, status=video.status)

@router.get("/", response_model=PaginatedVideoResponse)
async def list_videos(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by title or filename"),
    sort_by: str = Query("date-desc", alias="sortBy", description="Sort order"),
    date_range: str = Query("allTime", alias="dateRange", description="Date range filter"),
    status: Optional[str] = Query(None, description="Filter by status"),
    media_type: Optional[str] = Query(None, alias="mediaType", description="Filter by media type (VIDEO, AUDIO, TEXT)"),
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    List videos for the current user with pagination and search support.
    """
    return await service.get_user_videos(current_user.user_id, page, limit, search, sort_by, date_range, status, media_type)

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_data(
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard data: active jobs and recent history.
    """
    return await service.get_dashboard_jobs(current_user.user_id)

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

@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
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
    
    return {"message": "Video deleted successfully"}
