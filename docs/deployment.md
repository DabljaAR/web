# DabljaAR Deployment Guide

This guide documents backend deployment and runtime configuration for local and production environments.

## Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local non-Docker runs)
- PostgreSQL credentials, RabbitMQ credentials, and object storage credentials (MinIO for dev or external S3/GCS for prod)

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
- `RABBITMQ_URL` and `RABBITMQ_DEFAULT_PASS` (microservices prod)
- External S3: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_MEDIA_BUCKET`, `S3_MODELS_BUCKET`

## Dependency Profiles

Backend dependencies are split by concern:

- Core API/runtime: `uv sync`
- AI workers (STT/NMT/TTS): `uv sync --group ai`
- Dev/test tooling: `uv sync --group dev`

In Docker, the **backend API** uses `INSTALL_AI=false`. AI inference runs in `stt-service`, `nmt-service`, and `tts-service`.

## Production Compose (microservices — recommended)

Start the production microservices stack:

```bash
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d --build
```

This stack includes: `caddy`, `postgres`, `rabbitmq`, `orchestrator`, `stt-service`, `nmt-service`, `tts-service`, `media-service`, `backend`.

The dubbing pipeline runs over **RabbitMQ** (not Celery). Backend publishes `job.created` after media preprocess; the Go orchestrator coordinates STT → NMT → TTS → merge.

Check health:

```bash
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml ps
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml logs backend --tail=100
```

### Legacy production compose (Celery — deprecated)

The Celery-based stack remains for rollback only:

```bash
docker compose --env-file .env.production -f docker-compose.prod.minimal.yml up -d --build
```

This stack keeps: `caddy`, `postgres`, `redis`, `backend`, `celery-worker-ai`, `flower`. It does **not** run the RabbitMQ orchestrator or microservices and cannot complete `fullDubbing` via the new pipeline.

### Standard production compose (MinIO + Celery)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Database Migrations

Apply migrations after deploy:

```bash
docker compose exec backend alembic upgrade head
```

For CI/CD VM deploys (`.github/workflows/deploy-gcp.yml`), migrations run automatically before services start:

```bash
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d postgres rabbitmq
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml run --rm --entrypoint sh backend -lc "alembic upgrade head"
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d --build orchestrator stt-service nmt-service tts-service media-service backend caddy
```

## Common Issues

### PostgreSQL authentication failed

Ensure `DATABASE_URL` credentials and the postgres service credentials match exactly. Confirm `POSTGRES_PASSWORD` is set in the environment file used by compose.

### Backend health check unhealthy

Check:

- Migration errors in backend logs
- API reachability on `/api/health`
- Postgres and RabbitMQ readiness

In GitHub Actions deploys, backend and caddy logs are dumped automatically on health-check failure.

### Pipeline jobs stuck in QUEUED

Verify:

- RabbitMQ healthy (`docker compose ps rabbitmq`)
- Orchestrator running and connected
- Stage workers passing `/readiness` (STT/TTS cold start can take several minutes on first deploy)

Standalone `POST /api/tts/synthesize` proxies to `tts-service` via `TTS_SERVICE_URL` — no Celery worker required.

## Recommended Deployment Flow

1. Build images
2. Start infra (`postgres`, `rabbitmq`)
3. Run migrations
4. Start orchestrator + stage workers + backend + caddy
5. Verify backend health and worker readiness

See also: [microservices_migration.md](microservices_migration.md), [microservices_lld.md](microservices_lld.md).
