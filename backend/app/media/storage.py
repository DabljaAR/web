import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import Protocol, Optional
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

    async def delete_prefix(self, prefix: str) -> bool:
        """Delete all files and directories matching a prefix."""
        ...


    async def upload_directory(self, local_dir: str, remote_prefix: str) -> str:
        """Upload a local directory to storage."""
        ...

    async def upload_bytes(self, data: bytes, key: str, content_type: str = "audio/wav") -> str:
        """Upload raw bytes to storage."""
        ...

    async def download(self, path: str, local_path: str) -> bool:
        """Download a file from storage to a local path."""
        ...

    async def download_prefix(
        self, prefix: str, local_dir: str, bucket_name: str = ""
    ) -> bool:
        """Download all objects under *prefix* into *local_dir*, preserving relative paths."""
        ...


class LocalStorageService:
    def __init__(self, base_dir: Optional[str] = None, base_url: Optional[str] = None):
        # Use settings if not provided explicitly
        if base_dir is None:
            base_dir = settings.LOCAL_STORAGE_DIR
        if base_url is None:
            base_url = settings.LOCAL_STORAGE_URL_PREFIX
            
        self.base_dir = Path(base_dir)
        self.base_url = base_url.rstrip("/")
        
        # Validate that the base directory exists (don't auto-create)
        if not self.base_dir.exists():
            error_msg = (
                f"Local storage directory does not exist: {self.base_dir.absolute()}\n"
                "Please create it manually or set STORAGE_BACKEND=s3 with S3_* / MINIO_* "
                "env vars to use object storage.\n"
                f"To create the directory: mkdir -p {self.base_dir}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

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
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            return True
        return False
        
    async def delete_prefix(self, prefix: str) -> bool:
        """For local storage, we can use shutil.rmtree if it's a directory or glob delete."""
        full_path = self.base_dir / prefix
        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            return True
        
        # If prefix is not a dir but part of filenames (not common here but for completeness)
        parent = full_path.parent
        if parent.exists():
            count = 0
            for item in parent.glob(f"{full_path.name}*"):
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                count += 1
            return count > 0
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

    async def upload_bytes(self, data: bytes, key: str, content_type: str = "audio/wav") -> str:
        """Upload raw bytes to local storage."""
        from pathlib import Path
        file_path = self.base_dir / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(data)
        return key

    async def download(self, path: str, local_path: str) -> bool:
        src_path = self.base_dir / path
        if not src_path.exists():
            return False
        
        dest_path = Path(local_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.copy2(src_path, dest_path)
            return True
        except Exception as e:
            logger.error(f"Error downloading local file: {e}")
            return False

    async def download_prefix(self, prefix: str, local_dir: str, bucket_name: str = "") -> bool:
        """Copy all files under base_dir/prefix into local_dir (bucket_name ignored)."""
        src = self.base_dir / prefix
        dest = Path(local_dir)
        if not src.exists():
            return False
        dest.mkdir(parents=True, exist_ok=True)
        try:
            if src.is_file():
                target = dest / src.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                return True
            for item in src.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(src)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
            return True
        except Exception as exc:
            logger.error("Local download_prefix failed: %s", exc)
            return False


class S3StorageService:
    def __init__(self):
        raw_endpoint = (settings.S3_ENDPOINT_URL or "").strip()
        if not raw_endpoint:
            raw_endpoint = (settings.MINIO_ENDPOINT or "").strip()
        if raw_endpoint and not raw_endpoint.startswith("http"):
            scheme = "https" if settings.S3_SECURE else "http"
            raw_endpoint = f"{scheme}://{raw_endpoint}"
        self.endpoint_url: str | None = raw_endpoint or None
        self.access_key = (settings.S3_ACCESS_KEY_ID or "").strip()
        self.secret_key = (settings.S3_SECRET_ACCESS_KEY or "").strip()
        self.bucket_name = settings.S3_MEDIA_BUCKET
        self.region = (settings.S3_REGION or "").strip() or None
        self.session = aioboto3.Session()
        from botocore.config import Config

        # GCS / R2: botocore 1.36+ default checksum headers break S3-interop PutObject.
        self.config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )

    def _client_kwargs(self) -> dict:
        """Common kwargs for every aioboto3 S3 client."""
        kw: dict = {
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "config": self.config,
        }
        if self.endpoint_url:
            kw["endpoint_url"] = self.endpoint_url
        if self.region:
            kw["region_name"] = self.region
        return kw

    async def _ensure_bucket(self, s3_client):
        logger.info(f"S3Storage: checking bucket {self.bucket_name}...")
        try:
            await s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3Storage: bucket {self.bucket_name} exists.")
        except Exception:
            # Try to create bucket if it doesn't exist (only if permissions allow)
            logger.warning(f"S3Storage: bucket {self.bucket_name} not found or inaccessible, attempting to create...")
            try:
                await s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"S3Storage: bucket {self.bucket_name} created successfully.")
            except Exception as e:
                logger.warning(f"S3Storage: could not check/create bucket {self.bucket_name}: {e}")


    async def save(self, file: UploadFile, directory: str = "") -> str:
        file_ext = Path(file.filename).suffix if file.filename else ""
        unique_name = f"{uuid.uuid4()}{file_ext}"
        key = f"{directory}/{unique_name}" if directory else unique_name

        async with self.session.client("s3", **self._client_kwargs()) as s3:
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

        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await self._ensure_bucket(s3)
            logger.info(f"S3Storage: uploading file {file_path} to key {key}...")
            await s3.upload_file(str(file_path), self.bucket_name, key)
            logger.info(f"S3Storage: upload complete.")

            
        return key

    async def get_url(self, path: str, filename: str = None) -> str:
        # Generate presigned URL
        try:
            params = {'Bucket': self.bucket_name, 'Key': path}
            if filename:
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'

            async with self.session.client("s3", **self._client_kwargs()) as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params=params,
                    ExpiresIn=3600  # 1 hour
                )
                return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            # Fallback (though probably won't work if private)
            base = self.endpoint_url or ""
            if base:
                return f"{base.rstrip('/')}/{self.bucket_name}/{path}"
            return f"s3://{self.bucket_name}/{path}"

    def get_absolute_path(self, path: str) -> str:
        raise NotImplementedError("S3 storage does not support direct filesystem access.")

    async def delete(self, path: str) -> bool:
        try:
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=path)
            return True
        except Exception as e:
            logger.error(f"Error deleting from S3: {e}")
            return False
            
    async def delete_prefix(self, prefix: str) -> bool:
        """Delete everything under a prefix in S3."""
        try:
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                # 1. List all objects with prefix
                paginator = s3.get_paginator('list_objects_v2')
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                    if 'Contents' in page:
                        objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
                        # 2. Delete them
                        if objects_to_delete:
                            await s3.delete_objects(
                                Bucket=self.bucket_name,
                                Delete={'Objects': objects_to_delete}
                            )
                return True
        except Exception as e:
            logger.error(f"Error deleting prefix from S3: {e}")
            return False
            

    async def upload_directory(self, local_dir: str, remote_prefix: str) -> str:
        """Upload recursively to S3."""
        local_path = Path(local_dir)
        if not local_path.is_dir():
             raise ValueError(f"{local_dir} is not a directory")

        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await self._ensure_bucket(s3)
            
            for item in local_path.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(local_path)
                    # For windows paths, ensure forward slashes
                    key = f"{remote_prefix}/{relative_path}".replace("\\", "/")
                    await s3.upload_file(str(item), self.bucket_name, key)
                    
        return remote_prefix

    async def upload_bytes(self, data: bytes, key: str, content_type: str = "audio/wav") -> str:
        """Upload raw bytes to S3/MinIO."""
        from io import BytesIO
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await self._ensure_bucket(s3)
            await s3.upload_fileobj(
                BytesIO(data),
                self.bucket_name,
                key,
                ExtraArgs={"ContentType": content_type}
            )
        return key

    async def download(self, path: str, local_path: str) -> bool:
        try:
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                logger.info("S3Storage: downloading key %s to %s...", path, local_path)
                await s3.download_file(self.bucket_name, path, local_path)
                logger.info("S3Storage: download complete.")
            return True
        except Exception as e:
            logger.error(f"Error downloading from S3: {e}")
            return False

    async def download_prefix(self, prefix: str, local_dir: str, bucket_name: str = "") -> bool:
        bucket = bucket_name or self.bucket_name
        dest_base = Path(local_dir)
        downloaded = 0
        try:
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith("/"):
                            continue
                        rel_path = os.path.relpath(key, prefix)
                        if rel_path == ".":
                            rel_path = os.path.basename(key)
                        dest = dest_base / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        await s3.download_file(bucket, key, str(dest))
                        downloaded += 1
            if downloaded == 0:
                logger.warning(
                    "S3 download_prefix: no objects under bucket=%s prefix=%r (nothing downloaded)",
                    bucket,
                    prefix,
                )
                return False
            return True
        except Exception as exc:
            logger.error("S3 download_prefix failed prefix=%s: %s", prefix, exc)
            return False


def get_storage_service() -> StorageService:
    if settings.STORAGE_BACKEND.lower() == "s3":
        return S3StorageService()
    return LocalStorageService()
