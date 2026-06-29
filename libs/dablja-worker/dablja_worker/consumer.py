"""Shared RabbitMQ consumer utilities for pipeline workers."""
import logging
import os
import time
from typing import Callable, Literal

import pika
from pika.exceptions import AMQPConnectionError, AMQPError, ChannelWrongStateError, StreamLostError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, InterfaceError
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

_ENGINE_CACHE: dict[str, tuple] = {}


def make_engine(database_url: str) -> tuple:
    """Return a cached (engine, SessionLocal) pair for the given database URL."""
    if database_url not in _ENGINE_CACHE:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _ENGINE_CACHE[database_url] = (engine, sessionmaker(bind=engine))
    return _ENGINE_CACHE[database_url]


def classify_failure(exc: BaseException) -> Literal["transient", "permanent"]:
    """Classify an exception for nack-requeue vs ack-and-fail handling."""
    if isinstance(
        exc,
        (
            AMQPConnectionError,
            AMQPError,
            StreamLostError,
            ChannelWrongStateError,
            OperationalError,
            InterfaceError,
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    ):
        return "transient"
    return "permanent"


def check_cancelled(db, job_id: str) -> bool:
    """Return True when the job row exists and status is CANCELLED."""
    row = db.execute(
        text("SELECT status FROM jobs WHERE id = :jid"),
        {"jid": job_id},
    ).fetchone()
    return row is not None and row[0] == "CANCELLED"


def consume_loop(
    rabbitmq_url: str,
    queue: str,
    binding_key: str,
    exchange: str,
    on_message: Callable,
    service_name: str = "worker",
    dlx_exchange: str = "dablja.jobs.dlx",
    prefetch_count: int = 1,
    initial_backoff_s: float = 1.0,
    max_backoff_s: float = 60.0,
    heartbeat: int | None = None,
) -> None:
    """Blocking consume loop with exponential backoff reconnect on connection loss."""
    if heartbeat is None:
        heartbeat = int(os.environ.get("RABBITMQ_HEARTBEAT", "600"))
    backoff = initial_backoff_s
    while True:
        try:
            from dablja_worker import __version__ as worker_lib_version

            logger.info(
                "[%s] Connecting to RabbitMQ: %s (dablja-worker=%s, heartbeat=%ss)",
                service_name,
                rabbitmq_url,
                worker_lib_version,
                heartbeat,
            )
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = heartbeat
            params.blocked_connection_timeout = 300

            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            channel.exchange_declare(exchange, exchange_type="topic", durable=True)
            channel.exchange_declare(dlx_exchange, exchange_type="direct", durable=True)
            channel.queue_declare(
                queue,
                durable=True,
                arguments={"x-dead-letter-exchange": dlx_exchange},
            )
            channel.queue_bind(queue, exchange, binding_key)
            channel.basic_qos(prefetch_count=prefetch_count)
            channel.basic_consume(queue, on_message)

            logger.info(
                "[%s] Waiting for jobs on '%s' (queue='%s')",
                service_name,
                binding_key,
                queue,
            )
            backoff = initial_backoff_s
            channel.start_consuming()
        except AMQPConnectionError as exc:
            logger.warning(
                "[%s] RabbitMQ connection lost: %s — reconnecting in %.1fs",
                service_name, exc, backoff,
            )
        except Exception as exc:
            if classify_failure(exc) == "transient":
                logger.warning(
                    "[%s] Transient consumer error: %s — reconnecting in %.1fs",
                    service_name, exc, backoff,
                )
            else:
                logger.exception("[%s] Permanent consumer error — stopping", service_name)
                raise
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff_s)
