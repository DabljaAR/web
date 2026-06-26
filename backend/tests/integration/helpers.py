"""Shared constants and helpers for integration tests.

Imported by both conftest.py and test files.
"""

import os
import uuid

# ─── Connection defaults (override via env vars) ─────────────────────────────
PG_DSN: str = os.getenv(
    "TEST_PG_DSN",
    "host=localhost port=5433 dbname=dabljaar user=postgres password=postgres",
)
RMQ_URL: str = os.getenv("TEST_RMQ_URL", "amqp://guest:guest@localhost:5673/")
EXCHANGE = "dablja.jobs.exchange"


def new_id() -> str:
    """Generate a unique ID for test isolation."""
    return str(uuid.uuid4())
