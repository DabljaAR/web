"""Lightweight RabbitMQ publisher used by the FastAPI backend.

Only used for fire-and-forget publishes (job.created events).
A new connection is opened per call to avoid managing a persistent connection
inside the async FastAPI process.
"""
import json
import logging

import pika

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"


def _get_rabbitmq_url() -> str:
    from app.config import settings
    return getattr(settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def publish_job_created(job_id: str) -> bool:
    """Publish a ``job.created`` event so the orchestrator can start the pipeline."""
    try:
        params = pika.URLParameters(_get_rabbitmq_url())
        params.socket_timeout = 5
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)

        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key="job.created",
            body=json.dumps({"job_id": job_id}),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistent
            ),
        )
        connection.close()
        logger.info("[RabbitMQ] Published job.created for job %s", job_id)
        return True
    except Exception as exc:
        logger.error("[RabbitMQ] Failed to publish job.created for %s: %s", job_id, exc)
        return False


def publish_tts_result(job_id: str, status: str, output_data: dict, error: str | None = None) -> bool:
    """Publish job.results.tts after the bridged TTS combine (includes merge) finishes."""
    try:
        payload: dict = {
            "job_id": job_id,
            "job_type": "TTS_SYNTHESIZE",
            "status": status,
            "output_data": output_data or {},
        }
        if error:
            payload["error"] = error

        params = pika.URLParameters(_get_rabbitmq_url())
        params.socket_timeout = 5
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key="job.results.tts",
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
        logger.info("[RabbitMQ] Published job.results.tts for job %s", job_id)
        return True
    except Exception as exc:
        logger.error("[RabbitMQ] Failed to publish job.results.tts for %s: %s", job_id, exc)
        return False
