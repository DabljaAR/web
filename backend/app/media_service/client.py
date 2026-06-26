import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class MediaServiceClient:
    """HTTP client for the media microservice (http://media-service:8003)."""

    def __init__(self) -> None:
        self._base_url: Optional[str] = None

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            self._base_url = os.getenv("MEDIA_SERVICE_URL", "http://media-service:8003").rstrip("/")
        return self._base_url

    async def get_metadata(self, s3_key: str) -> dict:
        """Probe an S3-backed file via the media service ffprobe endpoint."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{self.base_url}/ffmpeg/metadata", params={"path": s3_key})
            resp.raise_for_status()
            return resp.json()

    async def extract_audio(self, input_key: str, output_key: str) -> str:
        """Extract MP3 audio from an S3-backed file. Returns the output S3 key."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.base_url}/ffmpeg/extract-audio",
                json={"input_key": input_key, "output_key": output_key},
            )
            resp.raise_for_status()
            return resp.json()["key"]

    async def generate_thumbnail(
        self, input_key: str, output_key: str, time_offset: float = 1.0
    ) -> str:
        """Generate a JPEG thumbnail from an S3-backed file. Returns the output S3 key."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/ffmpeg/thumbnail",
                json={"input_key": input_key, "output_key": output_key, "time_offset": time_offset},
            )
            resp.raise_for_status()
            return resp.json()["key"]

    async def patch_status(
        self,
        video_id: str,
        status: str,
        *,
        error_message: Optional[str] = None,
        duration: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        size_bytes: Optional[int] = None,
        format: Optional[str] = None,
        codec: Optional[str] = None,
        frame_rate: Optional[float] = None,
    ) -> None:
        """PATCH /videos/{id}/status on the media microservice."""
        payload: dict = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        if duration is not None:
            payload["duration"] = duration
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        if size_bytes is not None:
            payload["size_bytes"] = size_bytes
        if format is not None:
            payload["format"] = format
        if codec is not None:
            payload["codec"] = codec
        if frame_rate is not None:
            payload["frame_rate"] = frame_rate

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                f"{self.base_url}/videos/{video_id}/status", json=payload
            )
            resp.raise_for_status()
            logger.debug("patch_status video=%s status=%s → %s", video_id, status, resp.status_code)

    async def patch_paths(
        self,
        video_id: str,
        *,
        audio_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        dubbed_video_path: Optional[str] = None,
        dubbing_metadata: Optional[dict] = None,
        file_path: Optional[str] = None,
    ) -> None:
        """PATCH /videos/{id}/paths on the media microservice."""
        payload: dict = {}
        if audio_path is not None:
            payload["audio_path"] = audio_path
        if thumbnail_path is not None:
            payload["thumbnail_path"] = thumbnail_path
        if dubbed_video_path is not None:
            payload["dubbed_video_path"] = dubbed_video_path
        if dubbing_metadata is not None:
            payload["dubbing_metadata"] = dubbing_metadata
        if file_path is not None:
            payload["file_path"] = file_path
        if not payload:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                f"{self.base_url}/videos/{video_id}/paths", json=payload
            )
            resp.raise_for_status()
            logger.debug("patch_paths video=%s → %s", video_id, resp.status_code)

    async def get_presigned_url(self, key: str, expires_secs: int = 3600) -> str:
        """Generate a presigned URL via the media microservice."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/storage/presign",
                json={"key": key, "expires_secs": expires_secs},
            )
            resp.raise_for_status()
            return resp.json()["url"]


media_client = MediaServiceClient()
