import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import Protocol
from fastapi import UploadFile
from app.config import settings
import aioboto3

logger = logging.getLogger(__name__)

class StorageService(Protocol):
    async def save(self, file: UploadFile, directory: str = "") -> str:
        """Save an UploadFile and return its path/key."""
        ...

    async def save_file(self, file_path: str, directory: str = "") -> str:
        """Save a local file by path and return its key."""
        ...

    def get_url(self, path: str) -> str:
        """Get public URL for a file path."""
        ...

    def get_absolute_path(self, path: str) -> str:
        """Get absolute filesystem path if applicable. Raises NotImplementedError for S3."""
        ...
        
    async def delete(self, path: str) -> bool:
        """Delete a file."""
        ...

class LocalStorageService:
    def __init__(self, base_dir: str = "uploads", base_url: str = "/uploads"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")

    async def save(self, file: UploadFile, directory: str = "") -> str:
        target_dir = self.base_dir / directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_ext = Path(file.filename).suffix if file.filename else ""
        unique_name = f"{uuid.uuid4()}{file_ext}"
        file_path = target_dir / unique_name
        
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            logger.error(f"Error saving file locally: {e}")
            raise e
            
        if directory:
            return f"{directory}/{unique_name}"
        return unique_name

    async def save_file(self, file_path: str, directory: str = "") -> str:
        target_dir = self.base_dir / directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        src_path = Path(file_path)
        file_ext = src_path.suffix
        unique_name = f"{uuid.uuid4()}{file_ext}"
        dest_path = target_dir / unique_name
        
        try:
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            logger.error(f"Error copying local file: {e}")
            raise e
            
        if directory:
            return f"{directory}/{unique_name}"
        return unique_name

    def get_url(self, path: str) -> str:
        return f"{self.base_url}/{path}"
        
    def get_absolute_path(self, path: str) -> str:
        return str(self.base_dir / path)

    async def delete(self, path: str) -> bool:
        full_path = self.base_dir / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

class S3StorageService:
    def __init__(self):
        self.endpoint_url = settings.MINIO_ENDPOINT
        if not self.endpoint_url.startswith("http"):
             scheme = "https" if settings.MINIO_SECURE else "http"
             self.endpoint_url = f"{scheme}://{self.endpoint_url}"
             
        self.access_key = settings.MINIO_ACCESS_KEY
        self.secret_key = settings.MINIO_SECRET_KEY
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.session = aioboto3.Session()

    async def _ensure_bucket(self, s3_client):
        try:
            await s3_client.head_bucket(Bucket=self.bucket_name)
        except Exception:
            # Try to create bucket if it doesn't exist (only if permissions allow)
            try:
                await s3_client.create_bucket(Bucket=self.bucket_name)
            except Exception as e:
                logger.warning(f"Could not check/create bucket {self.bucket_name}: {e}")

    async def save(self, file: UploadFile, directory: str = "") -> str:
        file_ext = Path(file.filename).suffix if file.filename else ""
        unique_name = f"{uuid.uuid4()}{file_ext}"
        key = f"{directory}/{unique_name}" if directory else unique_name

        async with self.session.client("s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        ) as s3:
            await self._ensure_bucket(s3)
            # Use file.file which is a file-like object
            await file.seek(0)
            await s3.upload_fileobj(file.file, self.bucket_name, key)
            
        return key

    async def save_file(self, file_path: str, directory: str = "") -> str:
        src_path = Path(file_path)
        file_ext = src_path.suffix
        unique_name = f"{uuid.uuid4()}{file_ext}"
        key = f"{directory}/{unique_name}" if directory else unique_name

        async with self.session.client("s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        ) as s3:
            await self._ensure_bucket(s3)
            await s3.upload_file(str(file_path), self.bucket_name, key)
            
        return key

    def get_url(self, path: str) -> str:
        # Assuming public bucket
        return f"{self.endpoint_url}/{self.bucket_name}/{path}"

    def get_absolute_path(self, path: str) -> str:
        raise NotImplementedError("S3 storage does not support direct filesystem access.")

    async def delete(self, path: str) -> bool:
        try:
            async with self.session.client("s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            ) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=path)
            return True
        except Exception as e:
            logger.error(f"Error deleting from S3: {e}")
            return False

def get_storage_service() -> StorageService:
    # Prefer S3/MinIO if configured, otherwise fallback to Local
    if settings.MINIO_ENDPOINT:
        return S3StorageService()
    return LocalStorageService()
