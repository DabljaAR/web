"""Thin wrapper over the shared NMT inference library (backend/app/nmt/).

The backend's NLLBTranslatorWrapper is the single source of truth for model
logic. This wrapper injects the microservice's own config and a boto3-based
model downloader in place of the backend's async StorageService.
"""
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

from nmt_core.model import NLLBTranslatorWrapper as _Base
from app.config import settings


def _s3_download_fn(prefix: str, local_path: str, bucket: str) -> bool:
    """boto3 prefix downloader — replaces the backend's async StorageService."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint(),
        aws_access_key_id=settings.s3_access_key(),
        aws_secret_access_key=settings.s3_secret_key(),
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    paginator = client.get_paginator("list_objects_v2")
    downloaded = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix):].lstrip("/")
            if not rel:
                continue
            dest = Path(local_path) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(dest))
            downloaded += 1
    return downloaded > 0


class NLLBTranslatorWrapper(_Base):
    """Uses nmt-service config and boto3 downloads instead of backend defaults."""

    def __init__(self):
        super().__init__(config=settings, download_fn=_s3_download_fn)
