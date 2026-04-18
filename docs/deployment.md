# DabljaAR Deployment Guide

This guide documents backend deployment and runtime configuration for local and production environments.

## Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local non-Docker runs)
- PostgreSQL and Redis credentials, plus object storage credentials (MinIO or external S3/GCS)

## Environment Setup

Use the production template from the repo root:

```bash
cp .env.production.example .env.production
```

Set at least:

- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `DOMAIN`
- `ACME_EMAIL`

For standard production compose, also set MinIO credentials:

- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`

For minimal production compose, set external S3/GCS credentials instead:

- `S3_ENDPOINT_URL`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_MEDIA_BUCKET`
- `S3_MODELS_BUCKET`

## Dependency Profiles

Backend dependencies are split by concern:

- Core API/runtime: `uv sync`
- AI workers (STT/NMT/TTS): `uv sync --group ai`
- Dev/test tooling: `uv sync --group dev`

In Docker, AI dependencies are controlled via build arg:

```yaml
build:
  context: ./backend
  dockerfile: Dockerfile.prod
  args:
    INSTALL_AI: "true"
```

## Production Compose

Start the production stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Minimal production compose (AI-only + external object storage)

Use this mode when you want production deployment without local MinIO and without the media worker:

```bash
docker compose --env-file .env.production -f docker-compose.prod.minimal.yml up -d --build
```

This stack keeps: `caddy`, `postgres`, `redis`, `backend`, `celery-worker-ai`, `flower`.
This stack removes: `minio`, `celery-worker-media`.

Required object-storage env vars for this mode:

- `STORAGE_BACKEND=s3`
- `S3_ENDPOINT_URL=https://storage.googleapis.com`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_REGION=us-east-1`
- `S3_MEDIA_BUCKET`
- `S3_MODELS_BUCKET`

Check health:

```bash
docker compose ps
docker compose logs backend --tail=100
```

## Database Migrations

Apply migrations after deploy:

```bash
docker compose exec backend alembic upgrade head
```

For CI/CD VM deploys (`.github/workflows/deploy-gcp.yml`), migrations are run automatically before backend/workers are started:

```bash
docker compose ... up -d postgres redis minio
docker compose ... run --rm --entrypoint sh backend -lc "alembic upgrade head"
docker compose ... up -d --build backend celery-worker-media celery-worker-ai flower caddy
```

For minimal production compose:

```bash
docker compose --env-file .env.production -f docker-compose.prod.minimal.yml up -d postgres redis
docker compose --env-file .env.production -f docker-compose.prod.minimal.yml run --rm --entrypoint sh backend -lc "alembic upgrade head"
docker compose --env-file .env.production -f docker-compose.prod.minimal.yml up -d --build backend celery-worker-ai flower caddy
```

## Common Issues

### PostgreSQL authentication failed

Ensure `DATABASE_URL` credentials and the postgres service credentials match exactly. Confirm `POSTGRES_PASSWORD` is set in the environment file used by compose.

### Backend health check unhealthy

Check:

- Migration errors in backend logs
- API reachability on `/api/health`
- Postgres readiness (service health + startup ordering)

In GitHub Actions deploys, backend and caddy logs are dumped automatically on health-check failure to speed up diagnosis.

### Worker queue not processing

Verify:

- Redis healthy
- Worker online in Flower
- Queue names in worker command match task routes

## Recommended Deployment Flow

1. Build images
2. Start infra services (postgres/redis/minio)
3. Run migrations
4. Start backend + workers
5. Verify health and queue processing

Minimal flow variant:

1. Start infra services (postgres/redis)
2. Run migrations
3. Start backend + AI worker (+ Flower/Caddy)
4. Verify health and queue processing
