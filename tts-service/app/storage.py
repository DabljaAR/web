"""MinIO/S3 helpers for the TTS microservice."""
import io
import logging
from typing import Optional

from dablja_worker.s3_client import make_s3_client

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        _client = make_s3_client(
            endpoint_url=settings.s3_endpoint(),
            aws_access_key_id=settings.s3_access_key(),
            aws_secret_access_key=settings.s3_secret_key(),
            region_name=settings.s3_region(),
        )
    return _client


def upload_wav(audio_bytes: bytes, key: str, bucket: str | None = None) -> str:
    """Upload WAV bytes to MinIO/S3. Returns the object key."""
    bucket = bucket or settings.S3_MEDIA_BUCKET
    buf = io.BytesIO(audio_bytes)
    _get_client().upload_fileobj(
        buf, bucket, key, ExtraArgs={"ContentType": "audio/wav"}
    )
    logger.debug("[TTS][S3] uploaded %dB → s3://%s/%s", len(audio_bytes), bucket, key)
    return key


def download_file(key: str, local_path: str, bucket: str | None = None) -> bool:
    bucket = bucket or settings.S3_MEDIA_BUCKET
    try:
        _get_client().download_file(bucket, key, local_path)
        logger.debug("[TTS][S3] downloaded s3://%s/%s → %s", bucket, key, local_path)
        return True
    except Exception as exc:
        logger.error("[TTS][S3] failed to download s3://%s/%s: %s", bucket, key, exc)
        return False
