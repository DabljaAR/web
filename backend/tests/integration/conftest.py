"""Fixtures for integration tests.

These connect to real infrastructure (PostgreSQL, RabbitMQ, MinIO)
running via docker-compose.test.yml.
"""

import pytest
import pytest_asyncio
import aio_pika
import psycopg2
import psycopg2.extras

from tests.integration.helpers import PG_DSN, RMQ_URL, EXCHANGE


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests (require real infrastructure)",
    )


# ─── PostgreSQL fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_conn():
    """Synchronous psycopg2 connection to the test PostgreSQL.

    Uses autocommit so DDL (enum creation) is visible immediately.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg_cursor(pg_conn):
    """A psycopg2 cursor with RealDictCursor for readable results."""
    return pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─── RabbitMQ fixtures ───────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def rmq_connection():
    """Async RabbitMQ connection to the test broker."""
    connection = await aio_pika.connect_robust(RMQ_URL)
    yield connection
    await connection.close()


@pytest_asyncio.fixture(scope="function")
async def rmq_channel(rmq_connection):
    """A fresh RabbitMQ channel per test function."""
    channel = await rmq_connection.channel()
    yield channel
    await channel.close()


# ─── Idempotent schema setup ────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=False)
def ensure_schema(pg_cursor):
    """Ensure required PostgreSQL enums exist (idempotent for CI).

    Use this fixture explicitly in tests that need custom enums::

        def test_foo(ensure_schema, ...):
            ...
    """
    pg_cursor.execute("""
        DO $$ BEGIN
            CREATE TYPE jobtype AS ENUM (
                'VIDEO_PROCESS', 'VIDEO_HLS', 'STT_TRANSCRIBE',
                'NMT_TRANSLATE', 'TTS_SYNTHESIZE', 'DUBBING_MERGE',
                'FULL_DUBBING_PIPELINE'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;

        DO $$ BEGIN
            CREATE TYPE jobstatus AS ENUM (
                'QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED',
                'RETRYING', 'CANCELLED'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
