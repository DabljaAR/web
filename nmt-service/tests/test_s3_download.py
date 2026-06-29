"""Tests for parallel S3 model download (F7)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from dablja_worker.s3_model_download import download_s3_prefix


def test_download_s3_prefix_downloads_all_keys_in_parallel():
    client = MagicMock()
    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "models/nmt-v4/config.json"},
                {"Key": "models/nmt-v4/model.safetensors"},
            ]
        }
    ]

    with patch("dablja_worker.s3_model_download.ThreadPoolExecutor") as pool_cls:
        pool = MagicMock()
        pool_cls.return_value.__enter__.return_value = pool

        future_a = MagicMock()
        future_b = MagicMock()
        pool.submit.side_effect = [future_a, future_b]

        with patch(
            "dablja_worker.s3_model_download.as_completed",
            return_value=[future_a, future_b],
        ):
            count = download_s3_prefix(
                client,
                "model-bucket",
                "models/nmt-v4",
                "/tmp/cache",
                max_workers=4,
            )

    assert count == 2
    assert pool.submit.call_count == 2
    first_dest = pool.submit.call_args_list[0].args[2]
    assert first_dest == Path("/tmp/cache/config.json")
