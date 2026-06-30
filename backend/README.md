# DabljaAR Backend

FastAPI API gateway for authentication, media processing, job management, and pipeline kickoff. The backend does **not** run AI inference — STT, NMT, TTS, and merge stages execute in separate microservices coordinated by the Go orchestrator over RabbitMQ.

For full system architecture, see the [root README](../README.md).

## Role

| Responsibility | Details |
|---|---|
| Authentication & authorization | JWT (access + refresh), bcrypt passwords, rate limiting |
| User & subscription management | Profiles, plans, payments |
| Media upload & preprocess | Video/audio/text upload, FFmpeg audio extraction, thumbnails |
| Job creation & status | Creates pipeline jobs in PostgreSQL, publishes `job.created` to RabbitMQ |
| Status polling API | Frontend polls job/task progress endpoints |

After media preprocessing completes, the backend publishes a `job.created` message. The **orchestrator** takes over and drives STT → NMT → TTS → merge through RabbitMQ.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy + Alembic + asyncpg
- PostgreSQL 16
- RabbitMQ (pipeline event publishing)
- S3-compatible object storage (MinIO locally)
- Managed with **uv**

> **Note:** Celery + Redis were used in the legacy monolith pipeline and are deprecated. Production runs the RabbitMQ microservices stack. Legacy Celery paths may remain in code behind feature flags but are not the primary execution path.

## Project Layout

```text
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings (DB, RabbitMQ, S3, JWT)
│   ├── dependencies.py      # Auth and DB session dependencies
│   ├── core/                # Auth, users, billing, subscriptions
│   ├── api/                 # Route registration
│   ├── jobs/                # Job models, creation, RabbitMQ publish
│   ├── media/               # Upload, preprocess (FFmpeg), storage
│   ├── stt/                 # Legacy in-process STT (superseded by stt-service/)
│   ├── nmt/                 # Legacy in-process NMT (superseded by nmt-service/)
│   ├── tts/                 # Legacy in-process TTS (superseded by tts-service/)
│   └── shared/              # Middleware, logging, rate limiter, DB session
├── alembic/                 # Database migrations
├── tests/
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── Dockerfile.prod
```

AI inference for the dubbing pipeline lives in sibling directories: `stt-service/`, `nmt-service/`, `tts-service/`, and `media-service/`.

## Dependency Groups (uv)

Dependencies are split to avoid installing heavy AI packages for auth/core-only work:

- Core runtime: `uv sync`
- AI extras (legacy/local): `uv sync --group ai`
- Dev/test tools: `uv sync --group dev`

## Local Development

Preferred — from repo root:

```bash
./start.sh setup
./start.sh run
```

Useful commands:

```bash
./start.sh status
./start.sh logs backend
./start.sh stop
```

### Manual Backend Run

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Requires PostgreSQL, RabbitMQ, and MinIO running (start via `docker compose up postgres rabbitmq minio -d` from repo root).

## Pipeline Workers

AI pipeline workers run as **separate services**, not as Celery processes inside the backend. Start the full stack from the repo root:

```bash
docker compose up --build
# or
./start.sh run
```

See [`docker-compose.yml`](../docker-compose.yml) for service definitions and [`docs/microservices_lld.md`](../docs/microservices_lld.md) for worker specs.

## Tests

```bash
cd backend
uv sync --group dev
uv run pytest tests/
```

CI-equivalent:

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run pytest -m "not integration and not slow" --cov=app
```

## Docs

- [Root README](../README.md) — product overview and architecture
- [`docs/microservices_lld.md`](../docs/microservices_lld.md) — service specs, queues, contracts
- [`docs/api.md`](../docs/api.md) — API endpoint reference
- [`docs/onboarding.md`](../docs/onboarding.md) — developer setup
- [`docs/deployment.md`](../docs/deployment.md) — production deployment
