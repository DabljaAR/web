"""Base worker that connects to RabbitMQ, consumes messages for registered
task handlers, and publishes results back.

::

    worker = BaseWorker(rabbitmq_url="amqp://guest:guest@rabbitmq:5672/")
    worker.register_handler("job.start.stt", handle_stt, "job.results.stt", "STT_TRANSCRIBE")
    await worker.start()
"""
import asyncio
import json
import logging
import signal
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

import aio_pika

from app.worker.connection import RabbitMQConnection, EXCHANGE_NAME
from app.worker.types import WorkerResultPayload

logger = logging.getLogger(__name__)


@dataclass
class _HandlerBinding:
    routing_key: str
    result_key: str
    job_type: str
    fn: Callable[..., Coroutine[Any, Any, dict]]


class BaseWorker:
    """RabbitMQ consumer that dispatches messages to registered handlers.

    Each handler is bound to a RabbitMQ routing key. When a message arrives,
    the worker:
    1. Deserialises ``{"job_id": "..."}``
    2. Calls the registered async handler
    3. Publishes ``WorkerResultPayload`` to ``job.results.*`` on success
    4. Publishes a FAILED result on error

    Set ``concurrency`` to limit how many messages are processed at once
    (default 1 — good for GPU-bound STT/TTS).
    """

    def __init__(
        self,
        rabbitmq_url: str,
        *,
        concurrency: int = 1,
        worker_name: str = "unknown",
        prefetch_count: int = 1,
    ):
        self._rmq = RabbitMQConnection(rabbitmq_url)
        self._concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._worker_name = worker_name
        self._prefetch_count = prefetch_count
        self._handlers: dict[str, _HandlerBinding] = {}
        self._consumer_tags: list[str] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    def register_handler(
        self,
        routing_key: str,
        fn: Callable[..., Coroutine[Any, Any, dict]],
        result_key: str,
        job_type: str,
    ):
        """Register a handler for a given routing key."""
        if not asyncio.iscoroutinefunction(fn):
            raise TypeError(f"{fn.__name__} must be an async function")
        self._handlers[routing_key] = _HandlerBinding(
            routing_key=routing_key,
            result_key=result_key,
            job_type=job_type,
            fn=fn,
        )

    async def start(self):
        """Connect to RabbitMQ, declare queues, and start consuming."""
        channel = await self._rmq.connect()
        await channel.set_qos(prefetch_count=self._prefetch_count)

        dlq_args = {"x-dead-letter-exchange": "dablja.jobs.dlx"}

        for routing_key, handler in self._handlers.items():
            queue_name = f"worker.{self._worker_name}.{routing_key.replace('.', '_')}"
            queue = await channel.declare_queue(
                queue_name, durable=True, arguments=dlq_args,
            )
            await queue.bind(EXCHANGE_NAME, routing_key=routing_key)

            consumer_tag = await queue.consume(
                self._make_callback(handler),
                no_ack=False,
            )
            self._consumer_tags.append(consumer_tag)
            logger.info(
                "Worker %s | consuming %s → queue=%s",
                self._worker_name, routing_key, queue_name,
            )

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except (NotImplementedError, ValueError):
                pass

        self._running = True
        logger.info(
            "Worker %s started | concurrency=%d | handlers=%s",
            self._worker_name, self._concurrency,
            list(self._handlers.keys()),
        )

        # Keep running until shutdown
        await self._shutdown_event.wait()

    async def stop(self):
        """Graceful shutdown: cancel consumers and close connection."""
        if not self._running:
            return
        self._running = False
        logger.info("Worker %s shutting down...", self._worker_name)

        channel = self._rmq.channel
        for tag in self._consumer_tags:
            try:
                await channel.basic_cancel(tag)
            except Exception:
                pass

        await self._rmq.close()
        self._shutdown_event.set()
        logger.info("Worker %s stopped", self._worker_name)

    def _make_callback(self, handler: _HandlerBinding):
        """Create an async callback for a specific handler binding."""

        async def callback(message: aio_pika.IncomingMessage):
            await self._process_message(message, handler)

        return callback

    async def _process_message(
        self,
        message: aio_pika.IncomingMessage,
        handler: _HandlerBinding,
    ):
        """Deserialise, dispatch, and publish result.

        Handlers can return a dict optionally containing a special key
        ``_result_job_id`` to override the job_id used in the published
        ``WorkerResultPayload``. This is used when a worker creates its own
        child job and needs to publish the result under the child's ID.
        The ``_result_job_id`` key is stripped from ``output_data`` before
        publishing.

        The semaphore is acquired here (rather than only in the callback
        wrapper) so that direct calls — e.g. in tests — also respect the
        concurrency limit.
        """
        async with self._semaphore:
            start_time = time.time()
            routing_key = message.routing_key or handler.routing_key
            job_id = "<unknown>"

            try:
                body = json.loads(message.body)
                job_id = body.get("job_id", job_id)
                logger.info(
                    "[%s] Processing | job=%s | routing_key=%s",
                    handler.job_type, job_id, routing_key,
                )

                # Call the handler
                output_data = await handler.fn(job_id)

                # Support child-job pattern: handler can set _result_job_id
                # to override the job_id used in the published result.
                publish_job_id = output_data.pop("_result_job_id", None) or job_id

                # Publish success result
                payload = WorkerResultPayload(
                    job_id=publish_job_id,
                    job_type=handler.job_type,
                    status="COMPLETED",
                    output_data=output_data,
                )
                await self._rmq.publish(handler.result_key, payload.to_bytes())

                elapsed = time.time() - start_time
                logger.info(
                    "[%s] Completed | job=%s | publish_job_id=%s | elapsed_ms=%.0f",
                    handler.job_type, job_id, publish_job_id, elapsed * 1000,
                )

                await message.ack()

            except json.JSONDecodeError as exc:
                logger.error(
                    "[%s] Bad JSON from %s — discarding: %s",
                    handler.job_type, routing_key, exc,
                )
                await message.ack()

            except Exception as exc:
                elapsed = time.time() - start_time
                logger.exception(
                    "[%s] Failed | job=%s | elapsed_ms=%.0f | error=%s",
                    handler.job_type, job_id, elapsed * 1000, exc,
                )
                # Publish failure result
                try:
                    payload = WorkerResultPayload(
                        job_id=job_id,
                        job_type=handler.job_type,
                        status="FAILED",
                        error=str(exc)[:2000],
                    )
                    await self._rmq.publish(handler.result_key, payload.to_bytes())
                except Exception as pub_exc:
                    logger.error("Failed to publish failure result: %s", pub_exc)

                # Nack and requeue for transient errors, discard for permanent
                await message.reject(requeue=False)

    async def publish_result(
        self,
        result_key: str,
        job_id: str,
        job_type: str,
        status: str,
        *,
        output_data: Optional[dict] = None,
        error: str = "",
    ):
        """Publish a WorkerResultPayload to RabbitMQ."""
        payload = WorkerResultPayload(
            job_id=job_id,
            job_type=job_type,
            status=status,
            output_data=output_data or {},
            error=error,
        )
        await self._rmq.publish(result_key, payload.to_bytes())
