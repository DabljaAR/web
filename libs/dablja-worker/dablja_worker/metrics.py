"""Prometheus metrics shared by pipeline workers."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

STAGE_DURATION = Histogram(
    "dablja_stage_duration_seconds",
    "Wall-clock time to process a pipeline stage job",
    ["stage"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200),
)

JOBS_COMPLETED = Counter(
    "dablja_jobs_completed_total",
    "Pipeline jobs completed by stage and terminal status",
    ["stage", "status"],
)

DLQ_MESSAGES = Counter(
    "dablja_dlq_messages_total",
    "Poison messages observed on the orchestrator DLQ",
)
