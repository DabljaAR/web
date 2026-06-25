import asyncio
import logging
from typing import Optional

import aio_pika

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "dablja.jobs.exchange"
EXCHANGE_TYPE = "topic"
DLX_NAME = "dablja.jobs.dlx"


class RabbitMQConnection:
    """Manages a single RabbitMQ connection with automatic reconnection."""

    def __init__(self, url: str):
        self._url = url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None

    async def connect(self) -> aio_pika.Channel:
        """Open a robust connection and return a channel with exchange declared."""
        self._connection = await aio_pika.connect_robust(self._url)
        ch = self._connection.channel()
        self._channel = await ch if asyncio.iscoroutine(ch) else ch
        await self._channel.set_qos(prefetch_count=1)

        # Declare the main topic exchange (must match orchestrator)
        await self._channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True,
        )
        # Declare the dead-letter exchange
        await self._channel.declare_exchange(
            DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True,
        )

        logger.info(
            "RabbitMQ connected | url=%s | exchange=%s",
            self._url, EXCHANGE_NAME,
        )
        return self._channel

    @property
    def channel(self) -> aio_pika.Channel:
        if self._channel is None:
            raise RuntimeError("Not connected — call connect() first")
        return self._channel

    @property
    def connection(self) -> aio_pika.RobustConnection:
        if self._connection is None:
            raise RuntimeError("Not connected — call connect() first")
        return self._connection

    async def close(self):
        if self._channel:
            try:
                await self._channel.close()
            except Exception:
                pass
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
        logger.info("RabbitMQ connection closed")

    async def declare_dlq(self, queue_name: str = "orchestrator.dlq") -> aio_pika.Queue:
        """Declare a dead-letter queue bound to the DLX."""
        dlq_args = {"x-dead-letter-exchange": DLX_NAME}
        queue = await self._channel.declare_queue(
            queue_name, durable=True, arguments=dlq_args,
        )
        return queue

    async def publish(
        self,
        routing_key: str,
        body: bytes,
        *,
        exchange_name: str = EXCHANGE_NAME,
        persistent: bool = True,
    ):
        """Publish a message to the exchange."""
        exchange = await self._channel.get_exchange(exchange_name)
        await exchange.publish(
            aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT if persistent else aio_pika.DeliveryMode.NOT_PERSISTENT,
                content_type="application/json",
            ),
            routing_key=routing_key,
        )
