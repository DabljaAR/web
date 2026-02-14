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

    async def get_url(self, path: str, filename: str = None) -> str:
        """Get public or presigned URL for a file path. Optionally set download filename."""
        ...

    def get_absolute_path(self, path: str) -> str:
        """Get absolute filesystem path if applicable. Raises NotImplementedError for S3."""
        ...
        
    async def delete(self, path: str) -> bool:
        """Delete a file."""
        ...

    async def upload_directory(self, local_dir: str, remote_prefix: str) -> str:
        """Upload a local directory to storage."""
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

    async def get_url(self, path: str, filename: str = None) -> str:
        # Local storage serving usually doesn't support dynamic content-disposition via URL alone 
        # unless served by a smart controller. For now, just return path.
        return f"{self.base_url}/{path}"
        
    def get_absolute_path(self, path: str) -> str:
        return str(self.base_dir / path)

    async def delete(self, path: str) -> bool:
        full_path = self.base_dir / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False
        
    async def upload_directory(self, local_dir: str, remote_prefix: str) -> str:
        """For local storage, we just copy contents to the target dir."""
        target_dir = self.base_dir / remote_prefix
        target_dir.mkdir(parents=True, exist_ok=True)
        
        local_path = Path(local_dir)
        
        try:
            # We iterate and copy to ensure we control the structure
            if not local_path.is_dir():
                raise ValueError(f"{local_dir} is not a directory")
                
            for item in local_path.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(local_path)
                    dest = target_dir / relative_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
            
            return remote_prefix
        except Exception as e:
            logger.error(f"Error uploading directory locally: {e}")
            raise e

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
        # Create a specific config for presigning if needed, usually defaults work
        from botocore.config import Config
        self.config = Config(signature_version='s3v4')

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

    async def get_url(self, path: str, filename: str = None) -> str:
        # Generate presigned URL
        try:
            params = {'Bucket': self.bucket_name, 'Key': path}
            if filename:
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'

            async with self.session.client("s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=self.config
            ) as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params=params,
                    ExpiresIn=3600  # 1 hour
                )
                return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            # Fallback (though probably won't work if private)
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
            
    async def upload_directory(self, local_dir: str, remote_prefix: str) -> str:
        """Upload recursively to S3."""
        local_path = Path(local_dir)
        if not local_path.is_dir():
             raise ValueError(f"{local_dir} is not a directory")

        async with self.session.client("s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        ) as s3:
            await self._ensure_bucket(s3)
            
            for item in local_path.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(local_path)
                    # For windows paths, ensure forward slashes
                    key = f"{remote_prefix}/{relative_path}".replace("\\", "/")
                    await s3.upload_file(str(item), self.bucket_name, key)
                    
        return remote_prefix

def get_storage_service() -> StorageService:
    # Prefer S3/MinIO if configured, otherwise fallback to Local
    if settings.MINIO_ENDPOINT:
        return S3StorageService()
    return LocalStorageService()
