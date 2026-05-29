from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx

from app.config import settings


class MediaServiceError(RuntimeError):
    pass


class MediaServiceClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.MEDIA_SERVICE_URL).rstrip("/")

    # ------------------------------------------------------------------
    # Video metadata CRUD (delegated to Rust media-service)
    # ------------------------------------------------------------------

    async def get_video(self, video_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/videos/{video_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def list_videos(
        self,
        *,
        user_id: int,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        date_range: Optional[str] = None,
        status: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> dict:
        params: dict[str, object] = {
            "user_id": user_id,
            "page": page,
            "limit": limit,
        }
        if search:
            params["search"] = search
        if sort_by:
            params["sort_by"] = sort_by
        if date_range:
            params["date_range"] = date_range
        if status:
            params["status"] = status
        if media_type:
            params["media_type"] = media_type

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/videos", params=params)
            response.raise_for_status()
            return response.json()

    async def create_video(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/videos", json=payload)
            response.raise_for_status()
            return response.json()

    async def delete_video(self, video_id: str) -> bool:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(f"{self.base_url}/videos/{video_id}")
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True

    # ------------------------------------------------------------------
    # Storage operations — use Python S3StorageService directly to avoid
    # the Rust SDK presign bug (PUT presigns return x-id=GetObject with
    # the aws-sdk-s3 v1.x + MinIO combination).
    # ------------------------------------------------------------------

    def _s3(self):
        from app.object_storage import S3StorageService
        return S3StorageService()

    async def presign_url(
        self,
        key: str,
        *,
        expires_secs: int = 3600,
        method: str = "GET",
        content_type: Optional[str] = None,
    ) -> str:
        s3 = self._s3()
        if method.upper() == "GET":
            return await s3.get_url(key)
        # For PUT presigns fall back to direct aioboto3
        import aioboto3
        from botocore.config import Config
        session = aioboto3.Session()
        cfg = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        params: dict = {"Bucket": s3.bucket_name, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        async with session.client(
            "s3",
            endpoint_url=s3.endpoint_url,
            aws_access_key_id=s3.access_key,
            aws_secret_access_key=s3.secret_key,
            config=cfg,
        ) as s3c:
            url = await s3c.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expires_secs
            )
        return s3._rewrite_presigned_url(url)

    async def upload_file(self, local_path: Path, *, key: str, content_type: str) -> None:
        await self._s3().upload_file(str(local_path), key, content_type)

    async def upload_stream(
        self,
        key: str,
        *,
        content_type: str,
        file_iter: AsyncIterator[bytes],
    ) -> None:
        chunks = []
        async for chunk in file_iter:
            chunks.append(chunk)
        data = b"".join(chunks)
        await self._s3().upload_bytes(data, key, content_type)

    async def upload_bytes(self, data: bytes, *, key: str, content_type: str) -> None:
        await self._s3().upload_bytes(data, key, content_type)

    async def delete_file(self, key: str) -> bool:
        return await self._s3().delete(key)

    async def download_file(self, key: str, local_path: Path) -> bool:
        return await self._s3().download(key, str(local_path))


async def iter_upload_file(file_obj, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    while True:
        chunk = await file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk
