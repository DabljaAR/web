from __future__ import annotations

import asyncio
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
    # Storage operations — use Rust media-service presign + HTTP PUT/GET
    # ------------------------------------------------------------------

    async def presign_url(
        self,
        key: str,
        *,
        expires_secs: int = 3600,
        method: str = "GET",
        content_type: Optional[str] = None,
    ) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "key": key,
                "expires_secs": int(expires_secs),
                "method": method.upper(),
            }
            if content_type:
                payload["content_type"] = content_type
            r = await client.post(f"{self.base_url}/storage/presign", json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("url")

    async def upload_file(self, local_path: Path, *, key: str, content_type: str) -> None:
        with open(local_path, "rb") as fh:
            data = fh.read()
        await self.upload_bytes(data, key=key, content_type=content_type)

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
        await self.upload_bytes(data, key=key, content_type=content_type)

    async def upload_bytes(self, data: bytes, *, key: str, content_type: str) -> None:
        # Get PUT presigned URL from media-service and PUT the bytes there.
        url = await self.presign_url(key, method="PUT", content_type=content_type)
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.put(url, content=data, headers=headers)
            resp.raise_for_status()

    async def delete_file(self, key: str) -> bool:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(f"{self.base_url}/storage/{key}")
            if resp.status_code == 200:
                return True
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            return True

    async def list_prefix(self, prefix: str) -> list[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/storage/list", params={"prefix": prefix})
            resp.raise_for_status()
            data = resp.json()
            return list(data.get("keys", []))

    async def download_prefix(self, prefix: str, local_dir: Path) -> bool:
        keys = await self.list_prefix(prefix)
        if not keys:
            return False

        local_dir.mkdir(parents=True, exist_ok=True)
        success = False
        for key in keys:
            relative = key[len(prefix):].lstrip("/") if key.startswith(prefix) else Path(key).name
            target = local_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            ok = await self.download_file(key, target)
            success = success or ok
        return success

    async def download_file(self, key: str, local_path: Path) -> bool:
        url = await self.presign_url(key, method="GET")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            with open(local_path, "wb") as fh:
                fh.write(resp.content)
            return True

    async def dub(self, payload: dict) -> dict:
        """Call the Rust media-service /ffmpeg/dub endpoint.

        Payload must follow the Rust DubRequest shape. Returns the JSON response.
        """
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(f"{self.base_url}/ffmpeg/dub", json=payload)
            response.raise_for_status()
            return response.json()


async def iter_upload_file(file_obj, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    while True:
        chunk = await file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk
