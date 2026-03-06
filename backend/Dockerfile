
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (minimal, only what's needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install dependencies directly to system Python
RUN pip install --upgrade pip setuptools wheel

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Health check - simple HTTP check without database dependency
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1

# Expose port
EXPOSE 8000

# Set entrypoint to migration script
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
