"""Publish WorkerResultPayload — the shared contract between Python workers and the Go orchestrator.

Matches the Go struct in orchestrator/internal/pipeline/manager.go (WorkerResultPayload).
Golden fixtures in orchestrator/internal/pipeline/testdata/worker_result_payload.json.
"""
import json
import logging
import time
from typing import Optional

import pika
from pika.exceptions import AMQPConnectionError, AMQPError, ChannelWrongStateError, StreamLostError

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
_DEFAULT_HEARTBEAT = 600


def publish_result(
    channel,
    routing_key: str,
    job_id: str,
    job_type: str,
    status: str,
    output_data: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Publish a WorkerResultPayload to the pipeline exchange.

    Args:
        channel:      open pika BlockingChannel
        routing_key:  e.g. "job.results.stt"
        job_id:       child stage job UUID
        job_type:     e.g. "STT_TRANSCRIBE" — matches Go JobType enum
        status:       "COMPLETED" or "FAILED"
        output_data:  lean summary dict (no large payloads — Claim Check pattern)
        error:        error message, present only when status="FAILED"
    """
    payload: dict = {
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "output_data": output_data or {},
    }
    if error:
        payload["error"] = error

    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,  # persistent
        ),
    )
    logger.info("[worker] Published %s for job %s to %s", status, job_id, routing_key)


def publish_result_reliable(
    rabbitmq_url: str,
    routing_key: str,
    job_id: str,
    job_type: str,
    status: str,
    *,
    output_data: Optional[dict] = None,
    error: Optional[str] = None,
    max_attempts: int = 3,
    exchange: str = EXCHANGE,
    heartbeat: int = _DEFAULT_HEARTBEAT,
) -> None:
    """Publish a result on a fresh connection with retries (decoupled from consumer channel)."""
    last_exc: Optional[Exception] = None
    logger.info(
        "[worker] Publishing %s for job %s via fresh connection (attempts=%d)",
        status,
        job_id,
        max_attempts,
    )

    for attempt in range(1, max_attempts + 1):
        connection = None
        try:
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = heartbeat
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.exchange_declare(exchange, exchange_type="topic", durable=True)
            publish_result(
                channel,
                routing_key,
                job_id,
                job_type,
                status,
                output_data=output_data,
                error=error,
            )
            return
        except (
            AMQPConnectionError,
            AMQPError,
            StreamLostError,
            ChannelWrongStateError,
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:
            last_exc = exc
            logger.warning(
                "[worker] Result publish attempt %d/%d failed for job %s: %s",
                attempt,
                max_attempts,
                job_id,
                exc,
            )
            if attempt < max_attempts:
                time.sleep(min(2**attempt, 10))
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass

    assert last_exc is not None
    raise last_exc
