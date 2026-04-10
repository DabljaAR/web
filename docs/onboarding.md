# DabljaAR — Developer Onboarding Guide

> Everything a new developer needs to go from zero to running the full stack locally.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Python** | 3.12+ | Backend API + workers |
| **Node.js** | 20+ | Frontend build |
| **Docker + Compose** | 24+ / 2+ | Database, Redis, workers |
| **Git** | 2.40+ | — |

---

## 1. Clone & Enter the Repo

```bash
git clone <repo-url> web
cd web
```

## 1.5 Preferred Ubuntu 22.04 Path (Native)

If you are on Ubuntu 22.04, use the project bootstrap script:

```bash
./start.sh setup
./start.sh run
```

Management commands:

```bash
./start.sh status
./start.sh logs backend
./start.sh stop
```

This path installs missing host dependencies, bootstraps env/config files, and starts local services with managed PID/log files.

---

## 2. Backend Setup

### 2.1 Virtual Environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows
uv sync --group dev
```

### 2.2 Environment Variables

```bash
cp .env.example .env
# Edit .env with your local values (DATABASE_URL, SECRET_KEY, etc.)
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar` | Async DB connection string |
| `SECRET_KEY` | (random) | JWT signing key |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker for Celery |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis result backend |

### 2.3 Start Infrastructure

```bash
# From project root (web/)
docker compose up postgres redis -d
```

### 2.4 Run Migrations

```bash
cd backend
alembic upgrade head
```

### 2.5 Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Visit: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### 2.6 Start Celery Workers

In separate terminals:

```bash
# Media worker (FFmpeg tasks)
celery -A app.jobs.celery_app worker --loglevel=info --queues=media --concurrency=2

# Pipeline worker (AI tasks)
celery -A app.jobs.celery_app worker --loglevel=info --queues=pipeline --concurrency=1
```

### 2.7 (Optional) Start Flower

```bash
celery -A app.jobs.celery_app flower --port=5555
```

Visit: [http://localhost:5555](http://localhost:5555) (Flower dashboard)

---

## 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Visit: [http://localhost:5173](http://localhost:5173)

### Environment Variables

```bash
cp .env.example .env
# VITE_API_BASE_URL=http://localhost:8000/api
```

---

## 4. Full Stack via Docker Compose

To run everything in containers (no local Python/Node needed):

```bash
# From project root (web/)
docker compose up --build
```

| Service | Port | URL |
|---------|------|-----|
| Backend API | 8000 | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Frontend | 5173 | [http://localhost:5173](http://localhost:5173) |
| PostgreSQL | 5433 | `localhost:5433` |
| Redis | 6379 | `localhost:6379` |
| Flower | 5555 | [http://localhost:5555](http://localhost:5555) |

---

## 5. Running Tests

### Backend

```bash
cd backend
pytest                        # All tests
pytest tests/test_job_service.py  # Job service only
pytest --cov=app --cov-report=html  # With coverage
```

### Frontend

```bash
cd frontend
npm run test                  # Vitest in watch mode
npm run test -- --run         # Single run
npm run test -- --coverage    # With coverage
```

---

## 6. Project Structure Quick Reference

```
web/
├── docker-compose.yml        # Full-stack orchestration
├── docs/                     # Architecture, API, onboarding docs
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app factory
│   │   ├── config.py         # Pydantic Settings
│   │   ├── core/             # Users, auth, billing
│   │   ├── media/            # Video upload & processing
│   │   ├── jobs/             # Celery app, Job model, tasks
│   │   │   ├── celery_app.py # Celery instance + config
│   │   │   ├── models.py     # Job ORM model
│   │   │   ├── schemas.py    # Pydantic schemas
│   │   │   ├── service.py    # JobService (CRUD)
│   │   │   └── tasks/        # Celery task definitions
│   │   ├── api/              # Router files
│   │   └── shared/           # Middleware, logging, utils
│   ├── alembic/              # DB migrations
│   └── tests/                # pytest tests
└── frontend/
    └── src/
        ├── services/         # api.js, mediaService.js, jobService.js
        ├── pages/            # Route pages (Dashboard, History, etc.)
        ├── features/         # Feature slices (auth, dashboard)
        └── hooks/            # useAuth, useFetch, useTranslation
```

---

## 7. Code Conventions

- **Backend layering:** Router → Service → Repository → Model. Never skip layers.
- **Imports:** Absolute from `app.*`. No relative imports.
- **Linting:** `ruff check . && ruff format .` before committing.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
- **Branches:** `feature/<name>`, `fix/<name>`, `chore/<name>`.

---

## 8. Useful Commands Cheat Sheet

```bash
# Backend
alembic revision --autogenerate -m "describe change"  # New migration
alembic upgrade head                                    # Apply migrations
alembic downgrade -1                                    # Rollback one step
ruff check . --fix                                      # Lint + autofix
pytest -x -v                                            # Stop on first failure

# Frontend
npm run build                   # Production build
npm run preview                 # Preview production build

# Docker
docker compose up -d            # Start all services
docker compose logs -f backend  # Follow backend logs
docker compose down -v          # Stop all + remove volumes
```
