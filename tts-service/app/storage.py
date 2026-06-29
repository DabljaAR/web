import io
import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint(),
        aws_access_key_id=settings.s3_access_key(),
        aws_secret_access_key=settings.s3_secret_key(),
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def upload_audio(wav_bytes: bytes, key: str) -> str:
    client = _s3_client()
    try:
        client.put_object(
            Bucket=settings.S3_MEDIA_BUCKET,
            Key=key,
            Body=wav_bytes,
            ContentType="audio/wav",
        )
        logger.info("Uploaded TTS audio to s3://%s/%s", settings.S3_MEDIA_BUCKET, key)
    except ClientError as exc:
        logger.exception("Failed to upload TTS audio to s3://%s/%s", settings.S3_MEDIA_BUCKET, key)
        raise

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_MEDIA_BUCKET, "Key": key},
        ExpiresIn=86400,
    )
    return url


def download_audio(key: str) -> Optional[bytes]:
    client = _s3_client()
    try:
        resp = client.get_object(Bucket=settings.S3_MEDIA_BUCKET, Key=key)
        return resp["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            logger.warning("Audio key not found: s3://%s/%s", settings.S3_MEDIA_BUCKET, key)
            return None
        logger.exception("Failed to download audio from s3://%s/%s", settings.S3_MEDIA_BUCKET, key)
        raise


def download_audio_to_bytes(key: str) -> Optional[bytes]:
    return download_audio(key)
