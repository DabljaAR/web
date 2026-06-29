"""Safe AMQP ack/nack and shared job completion orchestration for pipeline workers."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from sqlalchemy import text

from dablja_worker.heartbeat import run_with_heartbeat
from dablja_worker.job_state import is_completed, mark_failed
from dablja_worker.results import publish_result_reliable

logger = logging.getLogger(__name__)


def safe_ack(channel, delivery_tag: int) -> bool:
    """Ack the delivery tag when the consumer channel is still open."""
    try:
        if channel is not None and channel.is_open:
            channel.basic_ack(delivery_tag=delivery_tag)
            return True
    except Exception as exc:
        logger.warning("safe_ack failed for delivery_tag=%s: %s", delivery_tag, exc)
    return False


def _load_completed_output(session_factory, job_id: str) -> dict:
    with session_factory() as db:
        row = db.execute(
            text("SELECT output_data FROM jobs WHERE id = :jid"),
            {"jid": job_id},
        ).fetchone()
    if not row or not row[0]:
        return {}
    return dict(row[0])


def finish_job_message(
    *,
    channel,
    delivery_tag: int,
    rabbitmq_url: str,
    result_routing_key: str,
    job_id: str,
    job_type: str,
    session_factory,
    process_fn: Callable[[], dict],
    mark_failure_fn: Optional[Callable[[str, Exception], None]] = None,
    is_cancelled_error: Optional[Callable[[Exception], bool]] = None,
    service_name: str = "worker",
) -> None:
    """Run a pipeline job, publish WorkerResultPayload reliably, and ack safely."""
    connection = channel.connection
    summary: Optional[dict] = None
    processing_error: Optional[Exception] = None

    try:
        summary = run_with_heartbeat(connection, process_fn)
    except Exception as exc:
        processing_error = exc
        if is_cancelled_error and is_cancelled_error(exc):
            logger.info("[%s] Job %s cancelled — acking without result publish", service_name, job_id)
            safe_ack(channel, delivery_tag)
            return

    if processing_error is not None:
        with session_factory() as db:
            already_done = is_completed(db, job_id)
        if already_done:
            summary = _load_completed_output(session_factory, job_id)
            logger.info(
                "[%s] Job %s already COMPLETED after processing error — publishing result only",
                service_name,
                job_id,
            )
        else:
            if mark_failure_fn is not None:
                mark_failure_fn(job_id, processing_error)
            else:
                with session_factory() as db:
                    mark_failed(db, job_id, str(processing_error))
            publish_result_reliable(
                rabbitmq_url,
                result_routing_key,
                job_id,
                job_type,
                "FAILED",
                error=str(processing_error),
            )
            safe_ack(channel, delivery_tag)
            return

    try:
        publish_result_reliable(
            rabbitmq_url,
            result_routing_key,
            job_id,
            job_type,
            "COMPLETED",
            output_data=summary or {},
        )
    except Exception as pub_exc:
        with session_factory() as db:
            already_done = is_completed(db, job_id)
        if already_done:
            logger.error(
                "[%s] Job %s COMPLETED but result publish failed: %s — leaving message unacked for redelivery",
                service_name,
                job_id,
                pub_exc,
            )
            return
        raise

    if not safe_ack(channel, delivery_tag):
        logger.warning(
            "[%s] Job %s finished but consumer channel closed before ack — message will redeliver for idempotent retry",
            service_name,
            job_id,
        )
