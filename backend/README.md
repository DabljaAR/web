# DabljaAR Backend

FastAPI backend for authentication, media processing, and AI dubbing orchestration.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy + Alembic + asyncpg
- Celery + Redis
- MinIO/S3-compatible object storage
- STT/NMT/TTS modules under `app/stt`, `app/nmt`, `app/tts`

## Project Layout

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── core/
│   ├── api/
│   ├── jobs/
│   ├── media/
│   ├── stt/
│   ├── nmt/
│   ├── tts/
│   └── shared/
├── alembic/
├── tests/
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── Dockerfile.prod
```

## Dependency Groups (uv)

Dependencies are split to avoid installing heavy AI packages for auth/core-only work:

- Core runtime: `uv sync`
- AI extras: `uv sync --group ai`
- Dev/test tools: `uv sync --group dev`

## Local Development

From repo root:

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

## Manual Backend Run

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Workers

Media worker:

```bash
uv run celery -A app.jobs.celery_app worker -E --loglevel=info -Q media --concurrency=2 --hostname=worker-media@%h
```

AI worker:

```bash
uv sync --group ai
uv run celery -A app.jobs.celery_app worker -E --loglevel=info -Q ai_stt,pipeline,ai_nmt,ai_tts --concurrency=1 --hostname=worker-ai@%h
```

Flower:

```bash
uv sync --group dev
uv run celery -A app.jobs.celery_app flower --port=5555
```

## Tests

```bash
cd backend
uv sync --group dev
uv run pytest tests/
```

## Docs

See root `docs/` for architecture, deployment, runbook, API, and pipeline details.
