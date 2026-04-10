# DabljaAR Deployment Guide

This guide documents backend deployment and runtime configuration for local and production environments.

## Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local non-Docker runs)
- PostgreSQL, Redis, and MinIO credentials

## Environment Setup

Use the production template from the repo root:

```bash
cp .env.production.example .env.production
```

Set at least:

- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `DOMAIN`
- `ACME_EMAIL`

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

## Common Issues

### PostgreSQL authentication failed

Ensure `DATABASE_URL` credentials and the postgres service credentials match exactly. Confirm `POSTGRES_PASSWORD` is set in the environment file used by compose.

### Backend health check unhealthy

Check:

- Migration errors in backend logs
- API reachability on `/api/health`
- Postgres readiness (service health + startup ordering)

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
