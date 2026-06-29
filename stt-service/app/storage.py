"""MinIO/S3 client for the STT microservice."""
import logging

from dablja_worker.s3_client import make_s3_client

from app.config import settings

logger = logging.getLogger(__name__)


def _make_client():
    return make_s3_client(
        endpoint_url=settings.s3_endpoint(),
        aws_access_key_id=settings.s3_access_key(),
        aws_secret_access_key=settings.s3_secret_key(),
        region_name=getattr(settings, "S3_REGION", "us-east-1") or "us-east-1",
    )


def download_file(key: str, local_path: str, bucket: str = None) -> bool:
    bucket = bucket or settings.S3_MEDIA_BUCKET
    try:
        client = _make_client()
        client.download_file(bucket, key, local_path)
        logger.info("[STT][S3] Downloaded %s/%s → %s", bucket, key, local_path)
        return True
    except Exception as exc:
        logger.error("[STT][S3] Failed to download %s/%s: %s", bucket, key, exc)
        return False
