import logging
import time
from pathlib import Path
from typing import Optional

import aioboto3
from botocore.config import Config

from app.config import settings

logger = logging.getLogger(__name__)

_bucket_exists_cache: dict[str, float] = {}
_BUCKET_CHECK_TTL = 300


def _make_session() -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION,
    )


def _client_kwargs() -> dict:
    return {
        "endpoint_url": settings.AWS_ENDPOINT_URL,
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    }


async def _ensure_bucket(s3_client) -> None:
    bucket = settings.S3_MEDIA_BUCKET
    now = time.time()
    if _bucket_exists_cache.get(bucket, 0) > now:
        return
    try:
        await s3_client.head_bucket(Bucket=bucket)
        _bucket_exists_cache[bucket] = now + _BUCKET_CHECK_TTL
    except Exception:
        try:
            await s3_client.create_bucket(Bucket=bucket)
            _bucket_exists_cache[bucket] = now + _BUCKET_CHECK_TTL
            logger.info("Created bucket %s", bucket)
        except Exception as exc:
            logger.warning("Could not create bucket %s: %s", bucket, exc)


async def download_file(key: str, local_path: str) -> bool:
    session = _make_session()
    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with session.client("s3", **_client_kwargs()) as s3:
            await s3.download_file(settings.S3_MEDIA_BUCKET, key, str(dest))
        return True
    except Exception as exc:
        logger.error("download_file key=%s failed: %s", key, exc)
        return False


async def upload_file(local_path: str, key: str, content_type: Optional[str] = None) -> str:
    session = _make_session()
    extra: dict = {}
    if content_type:
        extra["ContentType"] = content_type
    async with session.client("s3", **_client_kwargs()) as s3:
        await _ensure_bucket(s3)
        await s3.upload_file(
            str(local_path),
            settings.S3_MEDIA_BUCKET,
            key,
            ExtraArgs=extra or None,
        )
    return key


async def generate_presigned_url(key: str, expires_secs: int = 3600) -> str:
    session = _make_session()
    async with session.client("s3", **_client_kwargs()) as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_MEDIA_BUCKET, "Key": key},
            ExpiresIn=expires_secs,
        )
    return url
