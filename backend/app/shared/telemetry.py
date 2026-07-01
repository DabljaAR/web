"""OpenTelemetry and Prometheus setup for the FastAPI backend."""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)

JOBS_CREATED = Counter(
    "dablja_jobs_created_total",
    "Jobs created by the backend API",
)

_INITIALIZED = False


def setup_observability(app) -> None:
    """Attach metrics middleware and OTLP tracing to the FastAPI app."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/api/health"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        _INITIALIZED = True
        return

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"
    )
    service_name = os.environ.get("OTEL_SERVICE_NAME", "backend")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(root=TraceIdRatioBased(0.2)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry tracing enabled for %s -> %s", service_name, endpoint)
    _INITIALIZED = True
