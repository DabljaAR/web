"""Tests for S3StorageService.download_prefix."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.media.storage import S3StorageService


def test_download_prefix_no_objects_returns_false(tmp_path):
    svc = S3StorageService()

    async def empty_pages():
        if False:
            yield {}

    mock_paginator = MagicMock()
    mock_paginator.paginate = MagicMock(return_value=empty_pages())

    mock_s3 = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.download_file = AsyncMock()

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_s3)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_cm)
    svc.session = mock_session

    dest = tmp_path / "out"
    dest.mkdir()

    ok = asyncio.run(
        svc.download_prefix("whisper-small", str(dest), bucket_name="model")
    )

    assert ok is False
    mock_s3.download_file.assert_not_called()


def test_download_prefix_downloads_files(tmp_path):
    svc = S3StorageService()

    async def one_page():
        yield {
            "Contents": [
                {"Key": "whisper-small/model.bin"},
                {"Key": "whisper-small/config.json"},
            ]
        }

    mock_paginator = MagicMock()
    mock_paginator.paginate = MagicMock(return_value=one_page())

    mock_s3 = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.download_file = AsyncMock()

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_s3)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_cm)
    svc.session = mock_session

    dest = tmp_path / "out"
    dest.mkdir()

    ok = asyncio.run(
        svc.download_prefix("whisper-small", str(dest), bucket_name="model")
    )

    assert ok is True
    assert mock_s3.download_file.await_count == 2
