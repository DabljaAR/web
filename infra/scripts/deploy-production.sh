#!/usr/bin/env bash
# Idempotent production deploy for single-VM Docker Compose stack.
# Requires: git, docker, flock. Run from repo root or set APP_DIR.
set -euo pipefail

TARGET_BRANCH="${TARGET_BRANCH:-main}"
APP_DIR="${APP_DIR:-$HOME/web}"
ENV_FILE="${ENV_FILE:-.env.production}"
BOOTSTRAP_MARKER="${BOOTSTRAP_MARKER:-/var/lib/vm-bootstrap.done}"
REQUIRE_BOOTSTRAP_MARKER="${REQUIRE_BOOTSTRAP_MARKER:-true}"
DEPLOY_LOCK="${DEPLOY_LOCK:-/var/lock/dabljaar-deploy.lock}"
if ! mkdir -p "$(dirname "$DEPLOY_LOCK")" 2>/dev/null || ! touch "$DEPLOY_LOCK" 2>/dev/null; then
  DEPLOY_LOCK="$APP_DIR/.deploy.lock"
fi
REPO_URL="${REPO_SSH_URL:-${REPO_FALLBACK:-}}"

case "$APP_DIR" in
  "~"|"~/"*) APP_DIR="${HOME}${APP_DIR#\~}" ;;
esac

DEPLOY_LOG="$APP_DIR/deploy.log"
mkdir -p "$APP_DIR"

exec 3>"$DEPLOY_LOCK"
if ! flock -n 3; then
  echo "Another deploy is already running (lock: $DEPLOY_LOCK)"
  exit 1
fi

exec > >(tee -a "$DEPLOY_LOG") 2>&1
echo "=== deploy started at $(date -Is) sha=${DEPLOY_SHA:-unknown} reason=${DEPLOY_REASON:-unknown} ==="

if [ "${REQUIRE_BOOTSTRAP_MARKER}" = "true" ] && [ ! -f "$BOOTSTRAP_MARKER" ]; then
  echo "Required bootstrap marker is missing: $BOOTSTRAP_MARKER"
  exit 1
fi

if [ "${REQUIRE_BOOTSTRAP_MARKER}" != "true" ] && [ ! -f "$BOOTSTRAP_MARKER" ]; then
  echo "Warning: bootstrap marker not found ($BOOTSTRAP_MARKER). Continuing because REQUIRE_BOOTSTRAP_MARKER=false."
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed on VM"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed on VM"
  exit 1
fi

sync_repository() {
  if [ -z "$REPO_URL" ]; then
    echo "REPO_SSH_URL or REPO_FALLBACK is required for initial clone"
    exit 1
  fi

  if [ ! -d "$APP_DIR/.git" ]; then
    if [ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
      if [ "${DEPLOY_FORCE_CLONE:-false}" = "true" ]; then
        echo "DEPLOY_FORCE_CLONE=true: removing non-git contents under $APP_DIR"
        rm -rf "${APP_DIR:?}/"*
      else
        echo "APP_DIR exists without .git and is non-empty: $APP_DIR"
        echo "Set DEPLOY_FORCE_CLONE=true to re-clone, or remove the directory manually."
        exit 1
      fi
    fi
    git clone -b "$TARGET_BRANCH" "$REPO_URL" "$APP_DIR" || {
      echo "Failed to clone repository. Ensure VM has GitHub SSH access for private repo."
      echo "Tried URL: $REPO_URL"
      exit 1
    }
  fi

  cd "$APP_DIR"

  if [ -z "${DEPLOY_SHA:-}" ]; then
    echo "DEPLOY_SHA is required"
    exit 1
  fi

  if ! git fetch --prune origin "$TARGET_BRANCH"; then
    echo "git fetch failed. Remote configuration:"
    git remote -v || true
    exit 1
  fi

  git checkout -B "$TARGET_BRANCH" "$DEPLOY_SHA"
  git reset --hard "$DEPLOY_SHA"
}

sync_repository

if [ ! -r "$ENV_FILE" ]; then
  echo "Required env file is missing or unreadable: $APP_DIR/$ENV_FILE"
  exit 1
fi

require_env() {
  local key="$1"
  if ! grep -Eq "^[[:space:]]*${key}=" "$ENV_FILE"; then
    echo "Missing required key in $ENV_FILE: $key"
    exit 1
  fi
}

require_env DOMAIN
require_env ACME_EMAIL
require_env SECRET_KEY
require_env POSTGRES_PASSWORD
require_env RABBITMQ_URL
require_env RABBITMQ_DEFAULT_PASS
require_env S3_ENDPOINT_URL
require_env S3_ACCESS_KEY_ID
require_env S3_SECRET_ACCESS_KEY
require_env S3_MEDIA_BUCKET
require_env S3_MODELS_BUCKET

DOMAIN_VALUE="$(grep -E '^[[:space:]]*DOMAIN=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
if [ -z "$DOMAIN_VALUE" ]; then
  echo "Unable to resolve DOMAIN from $ENV_FILE"
  exit 1
fi

COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    echo "Neither docker compose nor docker-compose is available on VM"
    exit 1
  fi
fi

COMPOSE_FILES="-f docker-compose.microservices.prod.yml"
COMPOSE="$COMPOSE_CMD --env-file $ENV_FILE $COMPOSE_FILES"

print_diagnostics() {
  echo "=== deploy diagnostics: compose ps -a ==="
  $COMPOSE ps -a || true
  echo "=== deploy diagnostics: service logs ==="
  $COMPOSE logs --tail=200 \
    backend caddy orchestrator rabbitmq \
    stt-service nmt-service tts-service media-service || true
  echo "=== deploy diagnostics: container health states ==="
  docker ps -aq | xargs -r docker inspect --format '{{.Name}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}} {{.State.Status}}' || true
}

on_exit() {
  local status=$?
  trap - EXIT
  if [ "$status" -ne 0 ]; then
    echo "=== deploy failed with exit code $status at $(date -Is) ==="
    print_diagnostics
  else
    echo "=== deploy succeeded at $(date -Is) ==="
  fi
  exit "$status"
}
trap on_exit EXIT

fix_frontend_dir_permissions() {
  local dir="$1"
  if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo chown -R "$(id -u):$(id -g)" "$dir"
    else
      echo "$dir is not writable and sudo is unavailable; fix ownership manually."
      exit 1
    fi
  fi
}

build_frontend_atomic() {
  local build_dir="$APP_DIR/frontend/dist.next"
  local dist_dir="$APP_DIR/frontend/dist"

  fix_frontend_dir_permissions "$APP_DIR/frontend/node_modules"
  rm -rf "$APP_DIR/frontend/node_modules"

  fix_frontend_dir_permissions "$build_dir"
  rm -rf "$build_dir"

  frontend_build_start="$(date +%s)"
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$APP_DIR/frontend:/frontend" \
    -w /frontend \
    -e HOME=/tmp \
    -e npm_config_cache=/tmp/.npm \
    -e VITE_API_BASE_URL=/api \
    -e VITE_BUILD_OUTDIR=dist.next \
    node:24-alpine \
    sh -c "npm ci --legacy-peer-deps && npm run build"
  frontend_build_end="$(date +%s)"
  frontend_build_seconds="$((frontend_build_end - frontend_build_start))"

  if [ ! -f "$build_dir/index.html" ]; then
    echo "Frontend build did not produce frontend/dist.next/index.html"
    exit 1
  fi

  if [ -d "$dist_dir" ]; then
    mv "$dist_dir" "$APP_DIR/frontend/dist.prev"
  fi
  mv "$build_dir" "$dist_dir"
  rm -rf "$APP_DIR/frontend/dist.prev"

  if [ ! -f "$dist_dir/index.html" ]; then
    echo "Frontend atomic swap failed: $dist_dir/index.html missing"
    exit 1
  fi
}

build_frontend_atomic

docker run --rm \
  --env-file "$APP_DIR/$ENV_FILE" \
  -v "$APP_DIR/Caddyfile.minimal:/etc/caddy/Caddyfile:ro" \
  caddy:2.10-alpine \
  caddy validate --config /etc/caddy/Caddyfile

$COMPOSE up -d postgres rabbitmq

run_migrations() {
  local migrate_cmd='alembic upgrade head'
  local migrate_name="dabljaar_migrate_$(date +%s)"
  echo "Building backend image for migrations at ${DEPLOY_SHA}"
  $COMPOSE build backend
  echo "Running migrations via one-off backend container ($migrate_name)"
  if command -v timeout >/dev/null 2>&1; then
    timeout 600 $COMPOSE run --rm --no-deps --name "$migrate_name" \
      --entrypoint sh backend -lc "$migrate_cmd"
  else
    $COMPOSE run --rm --no-deps --name "$migrate_name" \
      --entrypoint sh backend -lc "$migrate_cmd"
  fi
}
run_migrations

compose_up_start="$(date +%s)"
if $COMPOSE up -d --help 2>&1 | grep -q '\-\-wait'; then
  $COMPOSE up -d --build --remove-orphans --wait
else
  echo "docker compose --wait not supported; falling back to up without --wait"
  $COMPOSE up -d --build --remove-orphans
fi
compose_up_end="$(date +%s)"
compose_up_seconds="$((compose_up_end - compose_up_start))"
$COMPOSE ps

wait_for_readiness() {
  local service="$1"
  local url="$2"
  local label="$3"
  local max_attempts="${4:-60}"
  local sleep_s="${5:-10}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if $COMPOSE exec -T "$service" curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label readiness check passed"
      return 0
    fi
    sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
  echo "internal-${label}-fail: ${service} readiness check failed after deploy"
  return 1
}

wait_for_backend_health() {
  local max_attempts="${1:-40}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if $COMPOSE exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" >/dev/null 2>&1; then
      echo "backend health check passed"
      return 0
    fi
    sleep 5
    attempt=$((attempt + 1))
  done
  echo "internal-backend-fail: backend health check failed after deploy"
  return 1
}

wait_for_readiness orchestrator http://localhost:8081/readiness orchestrator 12 5
wait_for_readiness media-service http://localhost:8003/readiness media 12 10
wait_for_readiness stt-service http://localhost:8001/readiness stt 60 10
wait_for_readiness nmt-service http://localhost:8002/readiness nmt 60 10
wait_for_readiness tts-service http://localhost:8005/readiness tts 90 10
wait_for_backend_health 40

$COMPOSE exec -T caddy caddy validate --config /etc/caddy/Caddyfile
$COMPOSE up -d caddy

health_checks_start="$(date +%s)"

edge_api_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  if curl -fsS -H "Host: $DOMAIN_VALUE" http://127.0.0.1/api/health >/dev/null; then
    edge_api_healthy=true
    break
  fi
  sleep 5
done

if [ "$edge_api_healthy" != "true" ]; then
  echo "internal-edge-fail: caddy API route not healthy on localhost with host header"
  exit 1
fi

external_api_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  if curl -fsS --max-time 15 "https://${DOMAIN_VALUE}/api/health" >/dev/null; then
    external_api_healthy=true
    break
  fi
  sleep 5
done

if [ "$external_api_healthy" != "true" ]; then
  echo "external-edge-fail: public API health check failed on https://${DOMAIN_VALUE}/api/health"
  exit 1
fi

spa_root_healthy=false
spa_headers_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  spa_headers="$(curl -fsS --max-time 15 -I "https://${DOMAIN_VALUE}/" 2>/dev/null || true)"
  if echo "$spa_headers" | grep -Eqi 'strict-transport-security'; then
    spa_headers_healthy=true
  fi
  if curl -fsS --max-time 15 "https://${DOMAIN_VALUE}/" | grep -Eqi '<!doctype html|<html'; then
    spa_root_healthy=true
  fi
  if [ "$spa_root_healthy" = "true" ] && [ "$spa_headers_healthy" = "true" ]; then
    break
  fi
  sleep 5
done

if [ "$spa_headers_healthy" != "true" ]; then
  echo "spa-headers-fail: GET / missing Strict-Transport-Security (Caddy not routing {$DOMAIN} site block)"
  exit 1
fi

if [ "$spa_root_healthy" != "true" ]; then
  echo "spa-static-fail: public SPA root check failed on https://${DOMAIN_VALUE}/"
  exit 1
fi

health_checks_end="$(date +%s)"
health_checks_seconds="$((health_checks_end - health_checks_start))"

DEPLOYED_SHA="$(git rev-parse --short HEAD)"
echo "deployment timing: frontend_build=${frontend_build_seconds}s compose_up=${compose_up_seconds}s health_gates=${health_checks_seconds}s"
echo "deployed ${DEPLOYED_SHA} on branch $(git branch --show-current)"
$COMPOSE ps
