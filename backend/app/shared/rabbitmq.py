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


def publish_merge_result(job_id: str, status: str, output_data: dict, error: str | None = None) -> bool:
    """Publish job.results.merge so the orchestrator marks the pipeline complete."""
    return _publish_result("job.results.merge", job_id, "DUBBING_MERGE", status, output_data, error)


def publish_job_result(routing_key: str, job_id: str, job_type: str, status: str, output_data: dict, error: str | None = None) -> bool:
    """Publish a generic job result to the given routing key."""
    return _publish_result(routing_key, job_id, job_type, status, output_data, error)


def _publish_result(routing_key: str, job_id: str, job_type: str, status: str, output_data: dict, error: str | None = None) -> bool:
    """Core publisher — open a short-lived connection and fire one message."""
    try:
        payload: dict = {
            "job_id": job_id,
            "job_type": job_type,
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
            routing_key=routing_key,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
        logger.info("[RabbitMQ] Published %s for job %s to %s", status, job_id, routing_key)
        return True
    except Exception as exc:
        logger.error("[RabbitMQ] Failed to publish to %s for %s: %s", routing_key, job_id, exc)
        return False
