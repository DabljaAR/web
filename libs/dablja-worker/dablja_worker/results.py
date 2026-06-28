"""Publish WorkerResultPayload — the shared contract between Python workers and the Go orchestrator.

Matches the Go struct in orchestrator/internal/pipeline/manager.go (WorkerResultPayload).
Golden fixtures in orchestrator/internal/pipeline/testdata/worker_result_payload.json.
"""
import json
import logging
from typing import Optional

import pika

logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"


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
