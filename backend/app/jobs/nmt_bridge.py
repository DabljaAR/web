"""RabbitMQ-to-Celery bridge for NMT stage.

Listens on the ``nmt.jobs`` queue (bound to ``dablja.jobs.exchange`` with
routing key ``job.start.nmt``).  For each message it:

1. Creates an ``NMT_TRANSLATE`` child job inheriting from the completed STT job.
2. Dispatches ``nmt_translate.apply_async`` on the ``ai_nmt`` Celery queue.

Run as a host process alongside the Celery worker:
  cd /home/eslam/Desktop/GP/web/backend
  python -m app.jobs.nmt_bridge
"""
import json
import logging
import os
import sys
import time
import uuid

import pika

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NMT-BRIDGE] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

EXCHANGE = "dablja.jobs.exchange"
QUEUE = "nmt.jobs"
ROUTING_KEY = "job.start.nmt"

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/dabljaar",
)


def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(sync_url, poolclass=NullPool)
    return engine, sessionmaker(bind=engine)


def _save_stt_to_video_task(db, stt_job, output_data: dict) -> None:
    """Write STT results into the VideoTask row so nmt_translate can read them."""
    from sqlalchemy import text as sa_text

    task_id = (stt_job.input_data or {}).get("task_id")
    if not task_id:
        logger.warning("STT job %s has no task_id in input_data — cannot update VideoTask", stt_job.id)
        return

    segments = output_data.get("segments") or []
    transcript = output_data.get("transcript") or ""
    metadata = output_data.get("metadata") or {}
    source_lang = metadata.get("language")

    db.execute(
        sa_text("""
            UPDATE video_tasks
               SET stt_segments   = CAST(:segs AS jsonb),
                   transcript     = :tr,
                   stt_metadata   = CAST(:meta AS jsonb),
                   source_lang    = COALESCE(:lang, source_lang),
                   updated_at     = NOW()
             WHERE id = :tid
        """),
        {
            "segs": json.dumps(segments),
            "tr": transcript,
            "meta": json.dumps(metadata),
            "lang": source_lang,
            "tid": task_id,
        },
    )
    db.commit()
    logger.info("Saved %d STT segments to VideoTask %s", len(segments), task_id)


def _handle_nmt_trigger(body: bytes) -> None:
    """Create NMT job and dispatch Celery task for the given STT job ID."""
    payload = json.loads(body)
    stt_job_id = payload.get("job_id")
    if not stt_job_id:
        logger.error("nmt trigger missing job_id: %s", payload)
        return

    logger.info("NMT trigger received for STT job %s", stt_job_id)

    from app.jobs.models import Job, JobStatus, JobType

    engine, SessionLocal = _make_db()
    try:
        with SessionLocal() as db:
            stt_job = db.get(Job, stt_job_id)
            if not stt_job:
                logger.error("STT job %s not found in DB", stt_job_id)
                return

            # Save STT output → VideoTask so NMT can read stt_segments
            output_data = dict(stt_job.output_data or {})
            _save_stt_to_video_task(db, stt_job, output_data)

            nmt_job_id = str(uuid.uuid4())
            nmt_job = Job(
                id=nmt_job_id,
                parent_job_id=stt_job_id,
                job_type=JobType.NMT_TRANSLATE,
                status=JobStatus.QUEUED,
                user_id=stt_job.user_id,
                video_id=stt_job.video_id,
                input_data=dict(stt_job.input_data or {}),
            )
            db.add(nmt_job)
            db.commit()
            logger.info("Created NMT job %s (parent STT %s)", nmt_job_id, stt_job_id)
    finally:
        engine.dispose()

    from app.jobs.celery_app import celery_app
    celery_app.send_task(
        "app.jobs.tasks.nmt.nmt_translate",
        args=[nmt_job_id],
        kwargs={"enqueued_at": time.time()},
        queue="ai_nmt",
    )
    logger.info("Dispatched nmt_translate for job %s", nmt_job_id)


def _on_message(channel, method, properties, body):
    try:
        _handle_nmt_trigger(body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.exception("Error handling nmt trigger: %s", exc)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run():
    while True:
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            params.heartbeat = 60
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
            channel.queue_declare(QUEUE, durable=True)
            channel.queue_bind(exchange=EXCHANGE, queue=QUEUE, routing_key=ROUTING_KEY)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE, on_message_callback=_on_message)

            logger.info("NMT bridge ready — consuming from %s (key=%s)", QUEUE, ROUTING_KEY)
            channel.start_consuming()
        except (pika.exceptions.AMQPConnectionError, Exception) as exc:
            logger.error("RabbitMQ connection lost: %s — reconnecting in 5s", exc)
            time.sleep(5)


if __name__ == "__main__":
    run()
