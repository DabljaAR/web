import logging
import tempfile
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import ffmpeg, storage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ffmpeg/metadata")
async def get_metadata(path: str):
    with tempfile.TemporaryDirectory() as tmp:
        local_path = f"{tmp}/input"
        ok = await storage.download_file(path, local_path)
        if not ok:
            return JSONResponse({"error": "File not found in storage"}, status_code=404)
        try:
            meta = await ffmpeg.get_metadata(local_path)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(meta.to_dict())


class ExtractAudioRequest(BaseModel):
    input_key: str
    output_key: str


@router.post("/ffmpeg/extract-audio")
async def extract_audio(req: ExtractAudioRequest):
    with tempfile.TemporaryDirectory() as tmp:
        input_local = f"{tmp}/input"
        output_local = f"{tmp}/output.mp3"
        if not await storage.download_file(req.input_key, input_local):
            return JSONResponse({"error": "Input file not found"}, status_code=404)
        ok = await ffmpeg.extract_audio(input_local, output_local)
        if not ok:
            return JSONResponse({"error": "ffmpeg extract_audio failed"}, status_code=500)
        try:
            key = await storage.upload_file(output_local, req.output_key, "audio/mpeg")
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"status": "ok", "key": key})


class ThumbnailRequest(BaseModel):
    input_key: str
    output_key: str
    time_offset: Optional[float] = 1.0


@router.post("/ffmpeg/thumbnail")
async def generate_thumbnail(req: ThumbnailRequest):
    with tempfile.TemporaryDirectory() as tmp:
        input_local = f"{tmp}/input"
        output_local = f"{tmp}/thumb.jpg"
        if not await storage.download_file(req.input_key, input_local):
            return JSONResponse({"error": "Input file not found"}, status_code=404)
        ok = await ffmpeg.generate_thumbnail(input_local, output_local, req.time_offset or 1.0)
        if not ok:
            return JSONResponse({"error": "ffmpeg thumbnail failed"}, status_code=500)
        try:
            key = await storage.upload_file(output_local, req.output_key, "image/jpeg")
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"status": "ok", "key": key})


class PresignRequest(BaseModel):
    key: str
    expires_secs: Optional[int] = 3600


@router.post("/storage/presign")
async def get_presigned_url(req: PresignRequest):
    try:
        url = await storage.generate_presigned_url(req.key, req.expires_secs or 3600)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"url": url})
