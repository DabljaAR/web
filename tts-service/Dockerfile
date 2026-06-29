# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=shared . /tmp/dablja-worker
RUN pip install --no-cache-dir /tmp/dablja-worker

COPY requirements-base.txt .
RUN pip install --default-timeout=600 --retries=3 -r requirements-base.txt

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8003

CMD ["python", "-m", "app.main"]
