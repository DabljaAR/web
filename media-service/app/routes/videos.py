import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos")


class PatchPathsPayload(BaseModel):
    dubbed_video_path: Optional[str] = None
    dubbing_metadata: Optional[dict] = None
    audio_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    file_path: Optional[str] = None


class PatchStatusPayload(BaseModel):
    status: str
    error_message: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    format: Optional[str] = None
    codec: Optional[str] = None
    frame_rate: Optional[float] = None


@router.get("/{video_id}")
async def get_video(video_id: str):
    async with db.get_session() as session:
        video = await db.get_video(session, video_id)
    if video is None:
        return JSONResponse({"status": "error", "message": "Video not found"}, status_code=404)
    return JSONResponse(video)


@router.patch("/{video_id}/paths")
async def patch_video_paths(video_id: str, payload: PatchPathsPayload):
    try:
        async with db.get_session() as session:
            rows = await db.patch_video_paths(
                session, video_id,
                payload.dubbed_video_path,
                payload.dubbing_metadata,
                payload.audio_path,
                payload.thumbnail_path,
                payload.file_path,
            )
    except Exception as exc:
        logger.error("patch_video_paths failed for %s: %s", video_id, exc)
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

    if rows == 0:
        return JSONResponse({"status": "error", "message": "Video not found"}, status_code=404)
    return JSONResponse({"status": "ok", "rows_affected": rows, "video_id": video_id})


@router.patch("/{video_id}/status")
async def patch_video_status(video_id: str, payload: PatchStatusPayload):
    try:
        async with db.get_session() as session:
            rows = await db.patch_video_status(
                session, video_id,
                payload.status,
                payload.error_message,
                payload.duration,
                payload.width,
                payload.height,
                payload.size_bytes,
                payload.format,
                payload.codec,
                payload.frame_rate,
            )
    except Exception as exc:
        logger.error("patch_video_status failed for %s: %s", video_id, exc)
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

    if rows == 0:
        return JSONResponse({"status": "error", "message": "Video not found"}, status_code=404)
    return JSONResponse({"status": "ok", "rows_affected": rows, "video_id": video_id})
