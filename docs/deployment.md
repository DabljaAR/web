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

RabbitMQ management UI: `https://rabbitmq.$DOMAIN` (Caddy reverse proxy; credentials = `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS`). When Terraform DNS is enabled, `terraform output rabbitmq_fqdn` shows the FQDN.

Check health:

```bash
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml ps
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml logs backend --tail=100
```

Caddy reads [`Caddyfile.production`](Caddyfile.production), generated on each deploy by [`infra/scripts/deploy-production.sh`](infra/scripts/deploy-production.sh). For a manual bring-up without the deploy script:

```bash
cp Caddyfile.minimal Caddyfile.production
```

## Observability overlay (optional)

When `GRAFANA_ADMIN_PASSWORD` is set in `.env.production`, GitHub Actions deploy and [`infra/scripts/deploy-production.sh`](infra/scripts/deploy-production.sh) automatically add `docker-compose.observability.yml` and start the LGTM stack.

**Prerequisites:**

1. DNS: `grafana.app.$ZONE` → VM IP (`terraform output grafana_fqdn` after apply with `dns_include_grafana = true`)
2. Secrets in `.env.production` (upload to Secret Manager `env-production`):

```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<strong>
GRAFANA_BASIC_AUTH_USER=admin
GRAFANA_BASIC_AUTH_HASH=<caddy hash-password output>
```

**Manual start** (same compose selection as deploy):

```bash
source infra/scripts/lib/compose-env.sh
{ cat Caddyfile.minimal; echo; cat infra/observability/Caddyfile.grafana; } > Caddyfile.production
$COMPOSE up -d --build
```

**URLs after deploy:**

| UI | URL |
|----|-----|
| Grafana | `https://grafana.$DOMAIN` |
| RabbitMQ | `https://rabbitmq.$DOMAIN` |

See [observability.md](observability.md) for dashboards, LogQL, and alerting.

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

## GCP VM deploy (GitHub Actions)

Production deploys run via [`.github/workflows/deploy-gcp.yml`](../.github/workflows/deploy-gcp.yml), which SSHs to the VM and invokes [`infra/scripts/deploy-production.sh`](../infra/scripts/deploy-production.sh).

### Deploy flow

1. **Git sync** — `git fetch --prune origin main` then `git checkout -B main $GITHUB_SHA` (VM stays on branch `main`, not detached HEAD)
2. **Lock** — `flock` prevents overlapping deploys (`~/web/.deploy.lock` or `/var/lock/dabljaar-deploy.lock`)
3. **Frontend** — atomic build to `frontend/dist.next`, then swap into `frontend/dist` (Caddy never serves an empty `/srv`)
4. **Validate** — `caddy validate` before touching the running stack
5. **Infra + migrate** — `postgres` + `rabbitmq`, build backend once, run Alembic in a one-off container
6. **Reconcile** — `docker compose up -d --build --remove-orphans --wait`
7. **Edge** — recreate Caddy (`compose up -d caddy`), verify HTTPS API + SPA routes

Deploy logs append to `~/web/deploy.log`. On failure, service logs and `compose ps -a` are printed automatically.

### Manual deploy on the VM

```bash
cd ~/web
export DEPLOY_SHA=<commit-sha>          # required
export REPO_FALLBACK=git@github.com:ORG/REPO.git  # only needed for first clone
bash infra/scripts/deploy-production.sh
```

### One-time fix: detached HEAD

If the VM was deployed before this change and shows `(HEAD detached at …)`:

```bash
cd ~/web
git fetch --prune origin main
git checkout -B main "$(git rev-parse HEAD)"
```

### Verification checklist

After deploy:

```bash
cd ~/web
git branch --show-current    # expect: main
git rev-parse HEAD           # expect: matches GITHUB_SHA

docker compose --env-file .env.production -f docker-compose.microservices.prod.yml ps
# caddy + backend should be healthy even while tts-service is still starting

curl -fsS "https://$(grep ^DOMAIN= .env.production | cut -d= -f2)/api/health"
curl -fsSI "https://$(grep ^DOMAIN= .env.production | cut -d= -f2)/" | grep -i strict-transport-security
```

Re-run the deploy script without code changes to confirm idempotency — the second run should succeed without downtime.

### Compose startup order (edge vs pipeline)

The website (`caddy` → `backend` → SPA) starts as soon as **backend** is healthy. AI workers (`stt`, `nmt`, `tts`, `media`) and the orchestrator can still be warming up — dubbing jobs queue in RabbitMQ until workers pass `/readiness`. Caddy no longer depends on RabbitMQ health.

## Common Issues

### Site returns 404 or blank page (no security headers)

If `GET /` returns **404** with only `Server: Caddy` and **no** `Strict-Transport-Security` header, Caddy is not applying the `{$DOMAIN}` site block from `Caddyfile.minimal` (DNS is usually fine).

On the VM (`cd ~/web`):

```bash
# Broken: no Strict-Transport-Security. Working: header present.
curl -sI https://app.dabljaar.tech/ | head -20

docker compose --env-file .env.production -f docker-compose.microservices.prod.yml ps -a
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml exec caddy env | grep -E 'DOMAIN|ACME'
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml exec caddy test -f /srv/index.html && echo OK || echo MISSING
ls -la frontend/dist/index.html
tail -200 ~/web/deploy.log
```

**Recovery:**

```bash
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d --build --remove-orphans
docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d caddy
curl -sI https://app.dabljaar.tech/ | grep -i strict
```

Or re-run the full deploy script:

```bash
cd ~/web && DEPLOY_SHA=$(git rev-parse HEAD) bash infra/scripts/deploy-production.sh
```

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

### Pipeline stuck after STT (~25% progress)

Symptoms: STT child job is `COMPLETED`, parent stays at ~25%, NMT never starts. Orchestrator logs may show `Duplicate terminal result — ignoring` (fixed in orchestrator — redeploy orchestrator first).

**Recover a stuck job** after orchestrator fix is deployed:

```bash
# From repo root on prod VM
chmod +x infra/scripts/recover-pipeline-after-stt.sh
./infra/scripts/recover-pipeline-after-stt.sh <stt_child_job_id>
```

Or redeploy orchestrator only:

```bash
docker compose --env-file .env.production \
  -f docker-compose.microservices.prod.yml \
  up -d --build orchestrator
```

### Whisper model not loading from S3

STT logs may show `No objects found at s3://...` or `missing model.bin/config.json`. Verify bucket layout:

```bash
chmod +x infra/scripts/verify-whisper-s3-model.sh
./infra/scripts/verify-whisper-s3-model.sh
```

Required keys under `STT_MODEL_KEY` (default `whisper-medium/`):

- `model.bin`
- `config.json`

Align `S3_MODELS_BUCKET` with `terraform output storage_bucket_name`. Set `STT_ALLOW_HF_FALLBACK=false` once S3 cache is valid.

## Recommended Deployment Flow

1. Sync git to target commit (`git checkout -B main <sha>`)
2. Run `infra/scripts/deploy-production.sh` (handles frontend build, migrations, compose reconcile, health gates)
3. Verify worker `/readiness` for pipeline jobs (site can be up before workers finish cold start)

See also: [microservices_migration.md](microservices_migration.md), [microservices_lld.md](microservices_lld.md).
