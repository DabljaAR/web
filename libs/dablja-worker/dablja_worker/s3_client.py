"""S3 client factory for microservices (GCS / MinIO / AWS S3-interop).

botocore 1.36+ enables automatic request checksums by default; GCS and some
S3-compatible backends reject those headers with SignatureDoesNotMatch on PutObject.
"""
from __future__ import annotations

from typing import Optional

import boto3
from botocore.config import Config


def make_s3_client_config() -> Config:
    """Return botocore Config safe for GCS and other S3-interop endpoints."""
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )


def make_s3_client(
    *,
    endpoint_url: Optional[str],
    aws_access_key_id: str,
    aws_secret_access_key: str,
    region_name: str = "us-east-1",
):
    """Build a sync boto3 S3 client with interop-safe defaults."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=make_s3_client_config(),
        region_name=region_name or "us-east-1",
    )
