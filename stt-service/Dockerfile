FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared worker library (provided via additional_contexts in compose)
COPY --from=shared . /tmp/dablja-worker
RUN pip install --no-cache-dir /tmp/dablja-worker

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=600 -r requirements.txt

COPY . .
# Remove the vendored copy now that the package is installed
RUN rm -f app/dablja_worker.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001

CMD ["python", "-m", "app.main"]
