"""FastAPI helpers for worker observability endpoints."""
from __future__ import annotations

from prometheus_client import make_asgi_app


def mount_metrics(app) -> None:
    """Expose Prometheus metrics at GET /metrics."""
    app.mount("/metrics", make_asgi_app())
