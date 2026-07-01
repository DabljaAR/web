"""OpenTelemetry setup and AMQP trace propagation for pipeline workers."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, MutableMapping, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from dablja_worker.logging import bind_job_context, clear_job_context

logger = logging.getLogger(__name__)

_TRACER: Optional[trace.Tracer] = None
_INITIALIZED = False


def _headers_to_carrier(headers: Mapping[Any, Any] | None) -> dict[str, str]:
    if not headers:
        return {}
    carrier: dict[str, str] = {}
    for key, value in headers.items():
        if isinstance(key, str) and value is not None:
            if isinstance(value, bytes):
                carrier[key] = value.decode("utf-8", errors="replace")
            else:
                carrier[key] = str(value)
    return carrier


def setup_tracing(service_name: str) -> trace.Tracer:
    """Initialize OTLP tracing once per process."""
    global _TRACER, _INITIALIZED
    if _INITIALIZED:
        return _TRACER or trace.get_tracer(service_name)

    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        _TRACER = trace.get_tracer(service_name)
        _INITIALIZED = True
        return _TRACER

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"
    )
    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", service_name),
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(root=TraceIdRatioBased(0.2)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)
    _INITIALIZED = True
    logger.info("OpenTelemetry tracing enabled for %s -> %s", service_name, endpoint)
    return _TRACER


def inject_trace_headers(headers: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """Inject W3C trace context into AMQP headers."""
    carrier = dict(headers or {})
    inject(carrier)
    return carrier


@contextmanager
def trace_stage(
    service_name: str,
    stage: str,
    job_id: str,
    *,
    carrier: Mapping[Any, Any] | None = None,
) -> Iterator[trace.Span]:
    """Start a consumer span linked to upstream trace context."""
    tracer = setup_tracing(service_name)
    parent_ctx = extract(_headers_to_carrier(carrier))
    span_name = f"stage.{stage}"
    with tracer.start_as_current_span(
        span_name,
        context=parent_ctx,
        attributes={"job_id": job_id, "stage": stage},
    ) as span:
        span_ctx = span.get_span_context()
        trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else None
        span_id = format(span_ctx.span_id, "016x") if span_ctx.is_valid else None
        bind_job_context(job_id=job_id, stage=stage, trace_id=trace_id, span_id=span_id)
        try:
            yield span
        finally:
            clear_job_context()
