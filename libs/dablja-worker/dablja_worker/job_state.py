"""Raw SQL helpers for job lifecycle state transitions.

These are transport-agnostic: they work in any service that has a sync
SQLAlchemy session pointing at the shared PostgreSQL instance.

Usage:
    from dablja_worker.job_state import mark_processing, mark_completed, mark_failed

All functions operate inside an already-opened DB session and call db.commit().
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_completed(db, job_id: str) -> bool:
    """Return True if the job's current status is COMPLETED (idempotency check)."""
    row = db.execute(
        text("SELECT status FROM jobs WHERE id = :jid"),
        {"jid": job_id},
    ).fetchone()
    return row is not None and row[0] == "COMPLETED"


def mark_processing(db, job_id: str) -> None:
    """Transition job to PROCESSING, recording started_at."""
    db.execute(
        text(
            "UPDATE jobs SET status='PROCESSING', started_at=:now, updated_at=:now"
            " WHERE id=:jid"
        ),
        {"now": _utcnow(), "jid": job_id},
    )
    db.commit()


def mark_completed(
    db,
    job_id: str,
    output_data: Optional[dict] = None,
    progress: float = 100.0,
) -> None:
    """Transition job to COMPLETED with a lean output_data summary."""
    db.execute(
        text("""
            UPDATE jobs
               SET status='COMPLETED',
                   output_data = CAST(:output AS jsonb),
                   progress    = :progress,
                   completed_at = :now,
                   updated_at   = :now
             WHERE id = :jid
        """),
        {
            "output": json.dumps(output_data or {}),
            "progress": progress,
            "now": _utcnow(),
            "jid": job_id,
        },
    )
    db.commit()


def mark_failed(db, job_id: str, error: str) -> bool:
    """Transition job to FAILED unless it is already COMPLETED.

    Returns True when the row was updated, False when skipped (already COMPLETED).
    """
    result = db.execute(
        text("""
            UPDATE jobs
               SET status='FAILED',
                   error_message = :error,
                   completed_at  = :now,
                   updated_at    = :now
             WHERE id = :jid AND status != 'COMPLETED'
        """),
        {"error": error, "now": _utcnow(), "jid": job_id},
    )
    db.commit()
    updated = result.rowcount > 0
    if not updated:
        logger.info(
            "mark_failed skipped for job %s — already COMPLETED",
            job_id,
        )
    return updated
