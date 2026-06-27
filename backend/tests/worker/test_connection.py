"""Unit tests for RabbitMQ connection manager."""
from unittest.mock import AsyncMock, MagicMock, patch

import aio_pika
import pytest

from app.worker.connection import RabbitMQConnection, EXCHANGE_NAME, DLX_NAME


@pytest.fixture
def connection():
    return RabbitMQConnection(url="amqp://guest:guest@localhost:5672/")


class TestRabbitMQConnection:
    async def test_connect_declares_exchanges(self, connection):
        """connect() should create channel and declare both exchanges."""
        mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.channel.return_value = mock_channel

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            channel = await connection.connect()

        assert channel is mock_channel
        mock_channel.set_qos.assert_awaited_once_with(prefetch_count=1)
        mock_channel.declare_exchange.assert_any_call(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        mock_channel.declare_exchange.assert_any_call(
            DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )

    async def test_publish_sends_message(self, connection):
        """publish() should publish to the exchange with the given routing key."""
        mock_exchange = AsyncMock(spec=aio_pika.Exchange)
        mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
        mock_channel.get_exchange.return_value = mock_exchange
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.channel.return_value = mock_channel

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await connection.connect()
            await connection.publish("job.results.stt", b'{"job_id":"x"}')

        mock_channel.get_exchange.assert_awaited_once_with(EXCHANGE_NAME)
        mock_exchange.publish.assert_awaited_once()
        args, _ = mock_exchange.publish.await_args
        msg = args[0]
        assert isinstance(msg, aio_pika.Message)
        assert msg.body == b'{"job_id":"x"}'
        assert msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT

    async def test_close_disconnects(self, connection):
        mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
        mock_connection = AsyncMock(spec=aio_pika.RobustConnection)
        mock_connection.channel.return_value = mock_channel

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await connection.connect()
            await connection.close()

        mock_channel.close.assert_awaited_once()
        mock_connection.close.assert_awaited_once()

    async def test_channel_property_raises_when_not_connected(self, connection):
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = connection.channel

    async def test_connection_property_raises_when_not_connected(self, connection):
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = connection.connection
