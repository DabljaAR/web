# Copilot instructions for DabljaAR/web

## Build, test, lint

### Backend (uv)
```bash
cd backend
uv sync --locked --group dev
uv run ruff check app tests
uv run ruff format --check app tests
uv run pytest tests/
uv run pytest --cov=app --cov-report=xml --cov-report=html --cov-report=term-missing -m "not integration and not slow"
uv run pytest tests/test_job_service.py::test_name
```

### Frontend (npm)
```bash
cd frontend
npm ci
npm run lint
npm run build
npm run test -- --run
npm run test:coverage -- --run
npm run test -- --run src/path/to.test.jsx
```

## Architecture (big picture)
- Modular monolith FastAPI backend with feature modules (core, media, jobs, stt/nmt/tts) and shared infra. Requests flow Router → Service → Repository → DB.
- Async processing uses Celery + Redis: API creates Job records in Postgres and dispatches tasks; `worker-media` handles FFmpeg/media jobs and `worker-ai` runs AI pipeline queues (`ai_stt`, `ai_nmt`, `ai_tts`, `pipeline`).
- The dubbing pipeline is a Celery chain (STT → NMT → TTS → merge) with child jobs under a parent job, and the frontend polls job status/progress from the API.
- Media storage is abstracted to local filesystem or S3-compatible object storage (MinIO/AWS) via the backend storage service.
- React + Vite SPA frontend with Zustand store and React Router. All HTTP goes through `frontend/src/services/api.js`, which injects JWTs and refreshes tokens on 401 using the access/refresh token pair.
- Auth is token-pair based (`/api/login` + `/api/refresh`); frontend guards routes with `ProtectedRoute` and stores tokens in localStorage/sessionStorage based on “Remember Me.”

## Key conventions
- Backend layering is strict: routers never touch the DB, services hold business logic, repositories handle data access, and models/schemas stay in their layers.
- Backend imports are absolute from `app.*` (avoid relative imports).
- Use `uv` dependency groups: core `uv sync`, dev/test `uv sync --group dev`, AI extras `uv sync --group ai`.
- Frontend API calls must go through `src/services/api.js` to keep auth/refresh behavior consistent.
