# web
The main web platform for the DabljaAR website.

## Structure
- `backend/`: FastAPI backend — auth, media, AI pipeline workers.
- `frontend/`: React + Vite SPA.
- `docs/`: Technical documentation.
- `infra/`: Terraform infrastructure (GCP).

## Documentation

Detailed technical docs live in [`docs/`](docs/):

- [`docs/architecture.md`](docs/architecture.md) — system design and module overview
- [`docs/api.md`](docs/api.md) — API endpoint reference
- [`docs/onboarding.md`](docs/onboarding.md) — new developer setup guide
- [`docs/runbook.md`](docs/runbook.md) — operations and troubleshooting
- [`docs/deployment.md`](docs/deployment.md) — deployment guide and environment config
- [`docs/pipeline.md`](docs/pipeline.md) — AI dubbing pipeline details
- [`docs/media.md`](docs/media.md) — media processing and storage
- [`docs/docker_setup.md`](docs/docker_setup.md) — Docker Compose setup

## Quick Start (Ubuntu 22.04 Native Dev)

Use the root `start.sh` script to bootstrap and run the local stack natively:

```bash
# From project root
./start.sh setup
./start.sh run
```

Useful commands:

```bash
./start.sh status
./start.sh logs backend
./start.sh logs all
./start.sh stop
```

Optional flags:

```bash
./start.sh setup --skip-migrations
./start.sh run --no-frontend --no-flower
```

Note: Flower is an optional monitoring UI. To enable it in native mode, install backend dev extras:

```bash
cd backend
uv sync --group dev
```

The script is idempotent and manages local runtime files under `.runtime/`.

## Technologies Used
- Backend: Python, FastAPI, SQLAlchemy, Alembic, Celery, PostgreSQL, Redis — managed with uv
- Frontend: TypeScript, React, Vite, Tailwind CSS

## Quick Start (with docker-compose)

1. Ensure you have Docker and Docker Compose installed on your machine.
2. Navigate to the `web/` directory.
3. Run the following command to start both the backend and frontend services:
   ```bash
   docker compose up --build
   ```
4. Access the frontend at `http://localhost:5173` and the backend API at `http://localhost:8000`.

## Production (Docker Compose + Caddy)

```bash
cp .env.production.example .env.production
# Edit .env.production and set DOMAIN and secrets

docker compose --env-file .env.production \
   -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Optional GPU overlay for AI worker:

```bash
docker compose --env-file .env.production \
   -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build
```

## CI/CD with GitHub Actions

Two CI workflows are configured in `.github/workflows/`:

- `backend-tests.yml`: Runs backend lint + tests + coverage artifact upload.
- `frontend-tests.yml`: Runs frontend lint + tests + coverage artifact upload.
- `deploy-gcp.yml`: Deploys to the production GCP VM over SSH.

Both workflows trigger on `push` and `pull_request` to `main` and use path filters so only relevant changes run each pipeline.

### Backend Workflow Details

- Uses Python 3.12.
- Installs dependencies with `uv sync --locked --group dev`.
- Runs `ruff check` and `ruff format --check` against `app` and `tests`.
- Runs `pytest` with coverage and uploads `coverage.xml` and `htmlcov/`.

### Frontend Workflow Details

- Uses Node.js 24.
- Installs dependencies with `npm ci`.
- Runs `npm run lint`.
- Runs `npm run test:coverage -- --run`.
- Uploads the `frontend/coverage/` artifact.

### Deployment Workflow Details

- Triggers automatically on push to `main` for app/deploy-related paths.
- Supports manual runs using `workflow_dispatch`.
- Connects to the VM via SSH and deploys from `~/web`.
- Updates code with `git fetch` + `git pull --ff-only origin main`.
- Rebuilds and restarts production containers using:
   - `docker-compose.yml`
   - `docker-compose.prod.yml`
- Verifies deployment by checking container status and backend health endpoint.

### Manual GitHub Setup Required

After pushing workflows, configure branch protection for `main` in GitHub:

1. Go to Settings -> Branches -> Add branch protection rule for `main`.
2. Enable "Require a pull request before merging".
3. Enable "Require status checks to pass before merging".
4. Select these required checks:
   - `Backend Tests / backend-tests`
   - `Frontend Tests / frontend-tests`
5. Optional: enable "Require branches to be up to date before merging".

No production secrets are required for these two CI test workflows.

Deployment workflow requires these repository secrets:

- `GCP_VM_HOST`: Public VM IP or hostname.
- `GCP_VM_USER`: SSH user on the VM.
- `GCP_VM_SSH_KEY`: Private SSH key content for that user.
- `GCP_VM_PORT`: SSH port (optional, defaults to `22` if empty).
- `GIT_REPO_SSH_URL`: Optional private repo SSH URL for first-time clone (example: `git@github.com:owner/repo.git`). If omitted, workflow falls back to `git@github.com:<current-repo>.git`.

One-time VM prerequisites for deployment:

1. Repository is cloned at `~/web`.
2. `.env.production` exists at `~/web/.env.production`.
3. Docker and Docker Compose are installed and usable by the SSH user.
4. The VM has network access to pull latest git changes.
5. DNS and ports 80/443 are configured for production traffic.

The deployment workflow can bootstrap first deploy automatically: if `~/web/.git` is missing, it clones the repository on the VM before running `docker compose`.

### Local Reproduction

Backend:

```bash
cd backend
uv sync --locked --group dev
uv run ruff check app tests
uv run ruff format --check app tests
uv run pytest --cov=app --cov-report=xml --cov-report=html --cov-report=term-missing -m "not integration and not slow"
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run test:coverage -- --run
```
