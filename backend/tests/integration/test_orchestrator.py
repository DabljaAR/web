"""Integration test for the orchestrator's pipeline state machine.

Validates the full state-machine transition table against real RabbitMQ and
PostgreSQL. The test acts as a fake AI worker — it:

1. Creates a ``FULL_DUBBING_PIPELINE`` job in PostgreSQL
2. Publishes ``job.created`` to RabbitMQ
3. Listens for ``job.start.*`` triggers from the orchestrator
4. Responds with synthetic ``job.results.*`` messages
5. Verifies every stage transition fires and the parent job is marked COMPLETED
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

import aio_pika
import pytest
import psycopg2
import psycopg2.extras

from tests.integration.helpers import PG_DSN, RMQ_URL, EXCHANGE, new_id

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "not config.getoption('--run-integration')",
        reason="Pass --run-integration to enable integration tests",
    ),
]

# ─── Constants ────────────────────────────────────────────────────────────────

STAGES = ["stt", "nmt", "tts"]
ROUTES = {s: f"job.start.{s}" for s in STAGES}
RESULT_KEYS = {s: f"job.results.{s}" for s in STAGES}
JOB_TYPES = {
    "stt": "STT_TRANSCRIBE",
    "nmt": "NMT_TRANSLATE",
    "tts": "TTS_SYNTHESIZE",
    "merge": "DUBBING_MERGE",
}

STAGE_TIMEOUT = 15  # seconds to wait for each stage trigger
FINAL_TIMEOUT = 10  # seconds to wait for parent job COMPLETED


# ─── Test ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_state_machine(pg_cursor, pg_conn, rmq_channel):
    """Drive the orchestrator through all pipeline stages via real messages.

    fullDubbing ends at TTS while the bridged Celery path performs merge inside
    tts_combine_results — no separate merge stage is dispatched.

    The test subscribes to ``job.start.*`` (triggers) and ``job.results.*``
    (results), creates a pipeline job in PostgreSQL, publishes ``job.created``,
    and for each ``job.start.*`` trigger it receives, sends back a fake result.
    Asserts every stage fires in order and the parent pipeline job ends COMPLETED.
    """
    pipeline_id = new_id()
    video_id = new_id()
    now = datetime.now(timezone.utc)

    _create_test_video(pg_cursor, video_id, now)
    _create_pipeline_job(pg_cursor, pipeline_id, video_id, now)
    pg_conn.commit()

    # Bind temporary queues
    trigger_queue = await _declare_and_bind(rmq_channel, "job.start.*")
    result_queue = await _declare_and_bind(rmq_channel, "job.results.*")

    # Get a reference to the exchange
    exchange = await rmq_channel.get_exchange(EXCHANGE)

    # Publish job.created — this kicks off the pipeline
    await _publish(exchange, "job.created", {"job_id": pipeline_id})

    # State-machine handshake: for each stage, wait for trigger → respond
    stages_seen: list[str] = []

    for expected_stage in STAGES:
        trigger = await _consume_one(trigger_queue, timeout=STAGE_TIMEOUT)
        assert trigger is not None, (
            f"Timed out waiting for {ROUTES[expected_stage]} "
            f"(seen: {stages_seen})"
        )

        stage = trigger.routing_key.split(".")[-1]
        assert stage == expected_stage, (
            f"Expected {ROUTES[expected_stage]}, got {trigger.routing_key} "
            f"(seen: {stages_seen})"
        )
        stages_seen.append(stage)
        trigger.ack()

        # Create a child job (as a real worker would)
        child_id = _create_child_job(pg_cursor, child_of=pipeline_id,
                                     job_type=JOB_TYPES[stage], video_id=video_id)
        pg_conn.commit()

        # Respond with a fake result
        await _publish(exchange, RESULT_KEYS[stage], {
            "job_id": child_id,
            "job_type": JOB_TYPES[stage],
            "status": "COMPLETED",
            "output_data": {"result": f"fake-{stage}-output"},
            "error": "",
        })

    # All stages completed — verify parent pipeline job is COMPLETED
    status = _wait_for_status(pipeline_id, "COMPLETED", timeout=FINAL_TIMEOUT)
    assert status == "COMPLETED", (
        f"Pipeline job ended with status {status}, expected COMPLETED"
    )

    # Drain leftover messages on result_queue
    async with result_queue.iterator() as qiter:
        async for _ in qiter:
            pass


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _declare_and_bind(channel: aio_pika.Channel, binding_key: str) -> aio_pika.Queue:
    """Create an auto-delete exclusive queue bound to the exchange."""
    queue = await channel.declare_queue("", exclusive=True, auto_delete=True)
    await queue.bind(EXCHANGE, binding_key)
    return queue


async def _publish(exchange: aio_pika.Exchange, routing_key: str, body: dict):
    """Publish a JSON message to the pipeline exchange."""
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(body).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=routing_key,
    )


async def _consume_one(queue: aio_pika.Queue, timeout: float = 10) -> Optional[aio_pika.IncomingMessage]:
    """Wait for and return one message from the queue, or None on timeout."""
    try:
        return await asyncio.wait_for(queue.get(timeout=False), timeout=timeout)
    except asyncio.TimeoutError:
        return None


def _create_test_video(cursor, video_id: str, now: datetime):
    cursor.execute(
        """
        INSERT INTO videos (id, user_id, title, status, file_path, created_at, updated_at)
        VALUES (%s, 1, 'integration-test-video', 'COMPLETED', %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (video_id, f"videos/1/{video_id}.mp4", now, now),
    )


def _create_pipeline_job(cursor, job_id: str, video_id: str, now: datetime):
    cursor.execute(
        """
        INSERT INTO jobs (id, user_id, job_type, status, video_id,
                          input_data, output_data, created_at, updated_at)
        VALUES (%s, 1, %s::jobtype, %s::jobstatus, %s,
                %s::jsonb, '{}'::jsonb, %s, %s)
        """,
        (job_id, "FULL_DUBBING_PIPELINE", "QUEUED", video_id,
         json.dumps({"video_id": video_id}), now, now),
    )


def _create_child_job(cursor, *, child_of: str, job_type: str, video_id: str) -> str:
    """Insert a child job and return its ID."""
    child_id = new_id()
    now = datetime.now(timezone.utc)
    cursor.execute(
        """
        INSERT INTO jobs (id, user_id, job_type, status, video_id,
                          parent_job_id, input_data, output_data,
                          created_at, updated_at)
        VALUES (%s, 1, %s::jobtype, %s::jobstatus, %s,
                %s, '{}'::jsonb, %s::jsonb, %s, %s)
        """,
        (child_id, job_type, "PROCESSING", video_id, child_of,
         json.dumps({"result": f"fake-{job_type}"}), now, now),
    )
    return child_id


def _wait_for_status(job_id: str, expected: str, timeout: float = 10) -> Optional[str]:
    """Poll PostgreSQL until the job reaches the expected status."""
    conn = psycopg2.connect(PG_DSN)
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status FROM jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
        if row:
            status = row["status"]
            if status == expected:
                conn.close()
                return status
        time.sleep(0.5)
    conn.close()
    return status
