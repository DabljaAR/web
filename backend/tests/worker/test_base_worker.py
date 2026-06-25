"""Unit tests for BaseWorker message processing and lifecycle."""
import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import aio_pika
import pytest

from app.worker.base_worker import BaseWorker


@pytest.fixture
def worker():
    w = BaseWorker(
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        concurrency=1,
        worker_name="test",
    )
    return w


def _make_message(body: dict, routing_key: str = "job.start.stt"):
    """Build a mock aio_pika.IncomingMessage."""
    msg = AsyncMock(spec=aio_pika.IncomingMessage)
    msg.body = json.dumps(body).encode("utf-8")
    msg.routing_key = routing_key
    return msg


class TestBaseWorkerConstruction:
    def test_constructor_defaults(self):
        w = BaseWorker("amqp://localhost/")
        assert w._concurrency == 1
        assert w._prefetch_count == 1
        assert w._worker_name == "unknown"

    def test_register_handler_rejects_sync(self, worker):
        with pytest.raises(TypeError, match="must be an async function"):
            worker.register_handler(
                "job.start.stt", lambda x: {}, "job.results.stt", "STT"
            )

    def test_register_handler_accepts_async(self, worker):
        async def handler(job_id: str) -> dict:
            return {}

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        assert "job.start.stt" in worker._handlers
        assert worker._handlers["job.start.stt"].fn is handler


class TestBaseWorkerMessageProcessing:
    async def test_process_message_publishes_completed(self, worker):
        async def handler(job_id: str) -> dict:
            return {"transcript": "hello"}

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()

        msg = _make_message({"job_id": "job-001"})
        await worker._process_message(
            msg, worker._handlers["job.start.stt"]
        )

        worker._rmq.publish.assert_awaited_once()
        publish_args = worker._rmq.publish.await_args[0]
        assert publish_args[0] == "job.results.stt"
        published = json.loads(publish_args[1])
        assert published["job_id"] == "job-001"
        assert published["status"] == "COMPLETED"
        assert published["output_data"]["transcript"] == "hello"
        msg.ack.assert_awaited_once()

    async def test_process_message_uses_result_job_id(self, worker):
        async def handler(job_id: str) -> dict:
            return {"_result_job_id": "child-job-001", "transcript": "hello"}

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()

        msg = _make_message({"job_id": "job-001"})
        await worker._process_message(msg, worker._handlers["job.start.stt"])

        published = json.loads(worker._rmq.publish.await_args[0][1])
        assert published["job_id"] == "child-job-001"
        assert published["output_data"].get("_result_job_id") is None  # stripped

    async def test_process_message_publishes_failed_on_exception(self, worker):
        async def handler(job_id: str) -> dict:
            raise RuntimeError("GPU OOM")

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()

        msg = _make_message({"job_id": "job-001"})
        await worker._process_message(msg, worker._handlers["job.start.stt"])

        worker._rmq.publish.assert_awaited_once()
        published = json.loads(worker._rmq.publish.await_args[0][1])
        assert published["status"] == "FAILED"
        assert "GPU OOM" in published["error"]
        msg.reject.assert_awaited_once_with(requeue=False)

    async def test_process_message_discards_bad_json(self, worker):
        async def handler(job_id: str) -> dict:
            return {}

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()

        msg = _make_message({"job_id": "job-001"})
        msg.body = b"not-json"
        await worker._process_message(msg, worker._handlers["job.start.stt"])

        worker._rmq.publish.assert_not_called()
        msg.ack.assert_awaited_once()

    async def test_process_message_handles_missing_job_id(self, worker):
        async def handler(job_id: str) -> dict:
            return {"result": "ok"}

        worker.register_handler("job.start.stt", handler, "job.results.stt", "STT")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()

        msg = _make_message({})
        await worker._process_message(msg, worker._handlers["job.start.stt"])

        assert worker._rmq.publish.await_args is not None

    async def test_semaphore_limits_concurrency(self, worker):
        """Ensure semaphore prevents more than concurrency messages at once."""
        import asyncio

        in_flight = 0
        max_in_flight = 0

        async def slow_handler(job_id: str) -> dict:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1
            return {"done": True}

        worker.register_handler("job.start.test", slow_handler, "job.results.test", "TEST")
        worker._rmq = MagicMock()
        worker._rmq.publish = AsyncMock()
        worker._concurrency = 2
        worker._semaphore = asyncio.Semaphore(2)

        msgs = [
            _make_message({"job_id": f"job-{i}"}, "job.start.test")
            for i in range(5)
        ]

        tasks = [
            worker._process_message(m, worker._handlers["job.start.test"])
            for m in msgs
        ]
        await asyncio.gather(*tasks)

        assert max_in_flight <= 2
