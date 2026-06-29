"""Parallel S3 prefix download for model weight caches (F7)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional, Sequence

from boto3.s3.transfer import TransferConfig

logger = logging.getLogger(__name__)

_DEFAULT_MULTIPART_THRESHOLD = 8 * 1024 * 1024
_DEFAULT_MULTIPART_CHUNKSIZE = 8 * 1024 * 1024
_DEFAULT_MAX_CONCURRENCY = 10


def _collect_download_tasks(
    client,
    bucket: str,
    prefix: str,
    local_path: str,
) -> list[tuple[str, Path]]:
    """List object keys under *prefix* and map each to a local destination path."""
    paginator = client.get_paginator("list_objects_v2")
    prefix = prefix.strip("/")
    tasks: list[tuple[str, Path]] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix) :].lstrip("/")
            if not rel:
                continue
            tasks.append((key, Path(local_path) / rel))

    return tasks


def download_s3_prefix(
    client,
    bucket: str,
    prefix: str,
    local_path: str,
    *,
    max_workers: int = 8,
    multipart_threshold: int = _DEFAULT_MULTIPART_THRESHOLD,
    multipart_chunksize: int = _DEFAULT_MULTIPART_CHUNKSIZE,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> int:
    """Download all objects under *prefix* into *local_path* using bounded concurrency.

    Returns the number of files downloaded. Idempotent: existing keys are overwritten.
    """
    tasks = _collect_download_tasks(client, bucket, prefix, local_path)
    if not tasks:
        return 0

    transfer_config = TransferConfig(
        multipart_threshold=multipart_threshold,
        multipart_chunksize=multipart_chunksize,
        max_concurrency=max_concurrency,
        use_threads=True,
    )
    workers = max(1, min(max_workers, len(tasks)))
    completed = 0

    def _download_one(key: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(dest), Config=transfer_config)

    logger.info(
        "[S3] Downloading %d objects from s3://%s/%s → %s (workers=%d)",
        len(tasks),
        bucket,
        prefix.strip("/"),
        local_path,
        workers,
    )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_download_one, key, dest): (key, dest)
            for key, dest in tasks
        }
        for future in as_completed(future_map):
            future.result()
            completed += 1
            if on_progress is not None:
                on_progress(completed, len(tasks))

    return completed


def download_s3_keys(
    client,
    bucket: str,
    keys: Sequence[tuple[str, Path]],
    *,
    max_workers: int = 8,
    multipart_threshold: int = _DEFAULT_MULTIPART_THRESHOLD,
    multipart_chunksize: int = _DEFAULT_MULTIPART_CHUNKSIZE,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
) -> int:
    """Download explicit (key, dest) pairs — useful in tests."""
    if not keys:
        return 0

    transfer_config = TransferConfig(
        multipart_threshold=multipart_threshold,
        multipart_chunksize=multipart_chunksize,
        max_concurrency=max_concurrency,
        use_threads=True,
    )
    workers = max(1, min(max_workers, len(keys)))

    def _download_one(key: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(dest), Config=transfer_config)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_one, key, dest) for key, dest in keys]
        for future in as_completed(futures):
            future.result()

    return len(keys)
