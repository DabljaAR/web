"""Structured JSON logging with job and trace correlation for pipeline workers."""
from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

job_id_var: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
parent_job_id_var: ContextVar[Optional[str]] = ContextVar("parent_job_id", default=None)
stage_var: ContextVar[Optional[str]] = ContextVar("stage", default=None)
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


def bind_job_context(
    *,
    job_id: Optional[str] = None,
    parent_job_id: Optional[str] = None,
    stage: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
) -> None:
    if job_id is not None:
        job_id_var.set(job_id)
    if parent_job_id is not None:
        parent_job_id_var.set(parent_job_id)
    if stage is not None:
        stage_var.set(stage)
    if trace_id is not None:
        trace_id_var.set(trace_id)
    if span_id is not None:
        span_id_var.set(span_id)


def clear_job_context() -> None:
    job_id_var.set(None)
    parent_job_id_var.set(None)
    stage_var.set(None)
    trace_id_var.set(None)
    span_id_var.set(None)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for Loki ingestion."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": os.environ.get("SERVICE_NAME", self.service_name),
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key, var in (
            ("job_id", job_id_var),
            ("parent_job_id", parent_job_id_var),
            ("stage", stage_var),
            ("trace_id", trace_id_var),
            ("span_id", span_id_var),
        ):
            value = var.get()
            if value:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(
    service_name: str,
    *,
    level: str | None = None,
    json_format: bool | None = None,
) -> None:
    """Configure root logger for a worker service."""
    os.environ.setdefault("SERVICE_NAME", service_name)

    log_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    use_json = json_format
    if use_json is None:
        use_json = os.environ.get("LOG_JSON_FORMAT", "true").lower() == "true"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if use_json:
        handler.setFormatter(JsonFormatter(service_name))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
        )
    root.addHandler(handler)
