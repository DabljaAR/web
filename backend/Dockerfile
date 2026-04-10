
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

# Install uv from a pinned image tag (pin to a digest for stricter reproducibility)
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/

# Install system dependencies (minimal, only what's needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    postgresql-client \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Configure uv for Docker builds and install into system Python for bind-mounted /app compatibility
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

ARG INSTALL_AI=false

# Copy lock and project metadata first for dependency-layer caching
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_AI" = "true" ]; then \
      uv sync --locked --no-install-project --group ai; \
    else \
      uv sync --locked --no-install-project; \
    fi

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Copy entrypoint script with proper permissions
COPY --chown=appuser:appuser --chmod=755 entrypoint.sh /app/entrypoint.sh

USER appuser

# Set Python environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random

# Health check - simple HTTP check without database dependency
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1

# Expose port
EXPOSE 8000

# Set entrypoint to migration script
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
