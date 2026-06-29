"""dablja_worker — shared RabbitMQ consumer utilities for DabljaAR pipeline workers.

Public API (backwards-compatible with the old per-service dablja_worker.py):

    from dablja_worker import consume_loop, make_engine, classify_failure, check_cancelled
"""
from dablja_worker.consumer import (
    consume_loop,
    make_engine,
    classify_failure,
    check_cancelled,
)
from dablja_worker.job_state import (
    is_completed,
    mark_processing,
    mark_completed,
    mark_failed,
)
from dablja_worker.results import publish_result
from dablja_worker.s3_model_download import download_s3_prefix

__all__ = [
    # consumer.py
    "consume_loop",
    "make_engine",
    "classify_failure",
    "check_cancelled",
    # job_state.py
    "is_completed",
    "mark_processing",
    "mark_completed",
    "mark_failed",
    # results.py
    "publish_result",
    # s3_model_download.py
    "download_s3_prefix",
]
