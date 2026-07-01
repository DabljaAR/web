#!/usr/bin/env bash
# Idempotent production deploy for single-VM Docker Compose stack.
# Requires: git, docker, flock. Run from repo root or set APP_DIR.
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment)
# ---------------------------------------------------------------------------
TARGET_BRANCH="${TARGET_BRANCH:-main}"
APP_DIR="${APP_DIR:-$HOME/web}"
ENV_FILE="${ENV_FILE:-.env.production}"
BOOTSTRAP_MARKER="${BOOTSTRAP_MARKER:-/var/lib/vm-bootstrap.done}"
REQUIRE_BOOTSTRAP_MARKER="${REQUIRE_BOOTSTRAP_MARKER:-true}"
REPO_URL="${REPO_SSH_URL:-${REPO_FALLBACK:-}}"

# Deploy lock — fall back to APP_DIR if /var/lock isn't writable.
DEPLOY_LOCK="${DEPLOY_LOCK:-/var/lock/dabljaar-deploy.lock}"
if ! mkdir -p "$(dirname "$DEPLOY_LOCK")" 2>/dev/null || ! touch "$DEPLOY_LOCK" 2>/dev/null; then
  DEPLOY_LOCK="$APP_DIR/.deploy.lock"
fi

# Normalise tilde in APP_DIR.
case "$APP_DIR" in
  "~"|"~/"*) APP_DIR="${HOME}${APP_DIR#\~}" ;;
esac

DEPLOY_LOG="$APP_DIR/deploy.log"
mkdir -p "$APP_DIR"

# ---------------------------------------------------------------------------
# Deploy lock (with staleness guard — clears locks older than 3 hours)
# ---------------------------------------------------------------------------
if [ -f "$DEPLOY_LOCK" ]; then
  lock_age=$(( $(date +%s) - $(stat -c %Y "$DEPLOY_LOCK" 2>/dev/null || echo 0) ))
  if [ "$lock_age" -gt 10800 ]; then
    echo "Stale deploy lock detected (${lock_age}s old, >3h). Clearing."
    rm -f "$DEPLOY_LOCK"
  fi
fi

exec 3>"$DEPLOY_LOCK"
if ! flock -n 3; then
  echo "Another deploy is already running (lock: $DEPLOY_LOCK). Exiting."
  exit 1
fi

# ---------------------------------------------------------------------------
# Logging — tee all output to deploy.log
# ---------------------------------------------------------------------------
exec > >(tee -a "$DEPLOY_LOG") 2>&1

phase() { echo ""; echo "━━━ [$(date -Is)] PHASE: $* ━━━"; }
log()   { echo "[$(date -Is)] $*"; }

phase "DEPLOY START  sha=${DEPLOY_SHA:-unknown}  reason=${DEPLOY_REASON:-unknown}"

# ---------------------------------------------------------------------------
# Bootstrap checks
# ---------------------------------------------------------------------------
if [ "${REQUIRE_BOOTSTRAP_MARKER}" = "true" ] && [ ! -f "$BOOTSTRAP_MARKER" ]; then
  log "Required bootstrap marker is missing: $BOOTSTRAP_MARKER"
  exit 1
fi

if [ "${REQUIRE_BOOTSTRAP_MARKER}" != "true" ] && [ ! -f "$BOOTSTRAP_MARKER" ]; then
  log "Warning: bootstrap marker not found ($BOOTSTRAP_MARKER). Continuing because REQUIRE_BOOTSTRAP_MARKER=false."
fi

for cmd in git docker; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "$cmd is not installed on the VM"
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# git: sync repository to the exact commit SHA
# ---------------------------------------------------------------------------
phase "GIT SYNC"

sync_repository() {
  if [ ! -d "$APP_DIR/.git" ]; then
    if [ -z "$REPO_URL" ]; then
      log "REPO_SSH_URL or REPO_FALLBACK is required for initial clone"
      exit 1
    fi
    if [ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
      if [ "${DEPLOY_FORCE_CLONE:-false}" = "true" ]; then
        log "DEPLOY_FORCE_CLONE=true: removing non-git contents under $APP_DIR"
        rm -rf "${APP_DIR:?}/"*
      else
        log "APP_DIR exists without .git and is non-empty: $APP_DIR"
        log "Set DEPLOY_FORCE_CLONE=true to re-clone, or remove the directory manually."
        exit 1
      fi
    fi
    git clone -b "$TARGET_BRANCH" "$REPO_URL" "$APP_DIR" || {
      log "Failed to clone repository. Ensure VM has GitHub SSH access for private repo."
      log "Tried URL: $REPO_URL"
      exit 1
    }
  fi

  cd "$APP_DIR"

  if [ -z "${DEPLOY_SHA:-}" ]; then
    log "DEPLOY_SHA is required"
    exit 1
  fi

  if ! git fetch --prune origin "$TARGET_BRANCH"; then
    log "git fetch failed. Remote configuration:"
    git remote -v || true
    exit 1
  fi

  git checkout -B "$TARGET_BRANCH" "$DEPLOY_SHA"
  git reset --hard "$DEPLOY_SHA"
  log "Repository synced to $(git rev-parse --short HEAD)"
}

sync_repository

# ---------------------------------------------------------------------------
# Env file validation
# ---------------------------------------------------------------------------
phase "ENV VALIDATION"

if [ ! -r "$ENV_FILE" ]; then
  log "Required env file is missing or unreadable: $APP_DIR/$ENV_FILE"
  exit 1
fi

require_env() {
  local key="$1"
  if ! grep -Eq "^[[:space:]]*${key}=" "$ENV_FILE"; then
    log "Missing required key in $ENV_FILE: $key"
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
  log "Unable to resolve DOMAIN from $ENV_FILE"
  exit 1
fi
log "Target domain: $DOMAIN_VALUE"

# ---------------------------------------------------------------------------
# Docker Compose selection (shared with ops helper scripts)
# ---------------------------------------------------------------------------
# shellcheck source=lib/compose-env.sh
source "$APP_DIR/infra/scripts/lib/compose-env.sh"
if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  log "Observability overlay enabled (GRAFANA_ADMIN_PASSWORD set)"
fi

CADDY_FILE="$APP_DIR/Caddyfile.production"
OBSERVABILITY_MARKER="${HOME}/.observability-bootstrap.done"

assemble_caddyfile() {
  if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
    { cat "$APP_DIR/Caddyfile.minimal"; echo; cat "$APP_DIR/infra/observability/Caddyfile.grafana"; } > "$CADDY_FILE"
    log "Assembled $CADDY_FILE (app + rabbitmq + grafana)"
  else
    cp "$APP_DIR/Caddyfile.minimal" "$CADDY_FILE"
    log "Assembled $CADDY_FILE (app + rabbitmq only)"
  fi
}

validate_observability_env() {
  if [ "$OBSERVABILITY_ENABLED" != "true" ]; then
    return 0
  fi
  require_env GRAFANA_ADMIN_PASSWORD
  require_env GRAFANA_BASIC_AUTH_HASH
  local hash
  hash="$(grep -E '^[[:space:]]*GRAFANA_BASIC_AUTH_HASH=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
  if [ -z "$hash" ] || [ "$hash" = "replace-with-bcrypt-hash" ]; then
    log "GRAFANA_BASIC_AUTH_HASH is missing or still a placeholder in $ENV_FILE"
    log "Generate with: caddy hash-password --plaintext 'your-password'"
    log "See docs/observability.md"
    exit 1
  fi
  case "$hash" in
    \$2a\$*|\$2b\$*) ;;
    *)
      log "Warning: GRAFANA_BASIC_AUTH_HASH does not look like a bcrypt hash (\$2a\$ / \$2b\$)"
      ;;
  esac
}

validate_observability_env
assemble_caddyfile

# ---------------------------------------------------------------------------
# Diagnostics helper (called by on_exit trap on failure)
# ---------------------------------------------------------------------------
print_diagnostics() {
  echo ""
  echo "=== deploy diagnostics: compose ps -a ==="
  $COMPOSE ps -a || true
  echo "=== deploy diagnostics: recent service logs ==="
  $COMPOSE logs --tail=100 \
    backend caddy orchestrator rabbitmq \
    stt-service nmt-service tts-service media-service 2>/dev/null || true
  if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
    echo "=== deploy diagnostics: observability service logs ==="
    $COMPOSE logs --tail=50 \
      loki grafana promtail victoriametrics tempo otel-collector 2>/dev/null || true
  fi
  echo "=== deploy diagnostics: container health states ==="
  docker ps -aq | xargs -r docker inspect \
    --format '{{.Name}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}} {{.State.Status}}' || true
}

on_exit() {
  local status=$?
  trap - EXIT
  if [ "$status" -ne 0 ]; then
    echo ""
    log "=== DEPLOY FAILED with exit code $status ==="
    print_diagnostics
  else
    log "=== DEPLOY SUCCEEDED ==="
  fi
  exit "$status"
}
trap on_exit EXIT

# ---------------------------------------------------------------------------
# Pre-build disk space guard (Docker builds can fill small VM disks)
# ---------------------------------------------------------------------------
phase "PRE-BUILD CHECKS"

check_disk_space() {
  local min_gb="${1:-5}"
  local available_kb
  available_kb=$(df -k "$APP_DIR" | awk 'NR==2 {print $4}')
  local available_gb=$(( available_kb / 1024 / 1024 ))
  if [ "$available_gb" -lt "$min_gb" ]; then
    log "Insufficient disk space: ${available_gb}GB available, ${min_gb}GB required."
    log "Run: docker system prune -af  to free space, then re-deploy."
    exit 1
  fi
  log "Disk space OK: ${available_gb}GB available on $(df -k "$APP_DIR" | awk 'NR==2 {print $1}')"
}

if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  check_disk_space 10
else
  check_disk_space 5
fi

# ---------------------------------------------------------------------------
# Validate Caddyfile before starting any containers
# ---------------------------------------------------------------------------
log "Validating Caddyfile..."
docker run --rm \
  --env-file "$APP_DIR/$ENV_FILE" \
  -v "$CADDY_FILE:/etc/caddy/Caddyfile:ro" \
  caddy:2.10-alpine \
  caddy validate --config /etc/caddy/Caddyfile
log "Caddyfile is valid."

# ---------------------------------------------------------------------------
# Phase A: Build frontend (atomic swap) — done BEFORE containers start so
# Caddy always mounts a fresh dist/ when it is (re)created.
# ---------------------------------------------------------------------------
phase "FRONTEND BUILD"

fix_frontend_dir_permissions() {
  local dir="$1"
  if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo chown -R "$(id -u):$(id -g)" "$dir"
    else
      log "$dir is not writable and sudo is unavailable; fix ownership manually."
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
    sh -c "npm ci --legacy-peer-deps && npx tsc -b && npx vite build --outDir dist.next"
  frontend_build_end="$(date +%s)"
  frontend_build_seconds="$((frontend_build_end - frontend_build_start))"

  if [ ! -f "$build_dir/index.html" ]; then
    log "Frontend build did not produce frontend/dist.next/index.html"
    exit 1
  fi

  # Atomic swap: dist.next → dist (keep dist.prev as rollback for one cycle)
  if [ -d "$dist_dir" ]; then
    mv "$dist_dir" "$APP_DIR/frontend/dist.prev"
  fi
  mv "$build_dir" "$dist_dir"
  rm -rf "$APP_DIR/frontend/dist.prev"

  if [ ! -f "$dist_dir/index.html" ]; then
    log "Frontend atomic swap failed: $dist_dir/index.html missing"
    exit 1
  fi
  log "Frontend built in ${frontend_build_seconds}s → $dist_dir"
}

build_frontend_atomic

# ---------------------------------------------------------------------------
# Phase B: Infrastructure tier — postgres + rabbitmq
# Start these first and wait for them to be healthy before running migrations.
# ---------------------------------------------------------------------------
phase "INFRA TIER (postgres, rabbitmq)"

infra_up_start="$(date +%s)"
$COMPOSE up -d postgres rabbitmq

log "Waiting for postgres and rabbitmq to become healthy..."
wait_for_infra() {
  local max_attempts=30
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    local pg_healthy rmq_healthy
    pg_healthy=$($COMPOSE ps --format json postgres 2>/dev/null | grep -c '"Health":"healthy"' || true)
    rmq_healthy=$($COMPOSE ps --format json rabbitmq 2>/dev/null | grep -c '"Health":"healthy"' || true)

    # Fallback: try docker inspect if compose ps --format json isn't supported
    if [ "$pg_healthy" -eq 0 ]; then
      pg_healthy=$(docker inspect --format '{{.State.Health.Status}}' dabljaar_postgres 2>/dev/null | grep -c 'healthy' || true)
    fi
    if [ "$rmq_healthy" -eq 0 ]; then
      rmq_healthy=$(docker inspect --format '{{.State.Health.Status}}' dabljaar_rabbitmq 2>/dev/null | grep -c 'healthy' || true)
    fi

    if [ "$pg_healthy" -ge 1 ] && [ "$rmq_healthy" -ge 1 ]; then
      log "postgres and rabbitmq are healthy."
      return 0
    fi
    log "  attempt $attempt/$max_attempts: waiting for infra health..."
    sleep 5
    attempt=$((attempt + 1))
  done
  log "Timed out waiting for postgres/rabbitmq to become healthy."
  return 1
}
wait_for_infra
infra_up_end="$(date +%s)"
log "Infra tier up in $((infra_up_end - infra_up_start))s"

# ---------------------------------------------------------------------------
# Phase B2: Observability data plane (optional)
# ---------------------------------------------------------------------------
observability_data_start=0
observability_data_end=0
observability_agents_start=0
observability_agents_end=0

wait_for_container_running() {
  local name="$1"
  local max_attempts="${2:-30}"
  local sleep_s="${3:-5}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null | grep -q true; then
      log "Container $name is running (attempt $attempt)"
      return 0
    fi
    log "  waiting for $name: attempt $attempt/$max_attempts..."
    sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
  log "FAIL: container $name did not reach running state"
  return 1
}

wait_for_grafana_health() {
  local max_attempts="${1:-30}"
  local sleep_s="${2:-5}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if $COMPOSE exec -T grafana wget --spider -q http://127.0.0.1:3000/api/health 2>/dev/null; then
      log "grafana health check passed (attempt $attempt)"
      return 0
    fi
    log "  grafana: attempt $attempt/$max_attempts, retrying in ${sleep_s}s..."
    sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
  log "FAIL: grafana health check timed out"
  return 1
}

if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  phase "OBSERVABILITY DATA PLANE (loki, victoriametrics, tempo, otel-collector)"

  if [ ! -f "$OBSERVABILITY_MARKER" ]; then
    log "First observability deploy — recreating rabbitmq for prometheus plugin"
    $COMPOSE up -d --force-recreate rabbitmq
    wait_for_infra
    touch "$OBSERVABILITY_MARKER"
  fi

  observability_data_start="$(date +%s)"
  $COMPOSE up -d loki victoriametrics tempo otel-collector
  wait_for_container_running dabljaar_loki 24 5
  wait_for_container_running dabljaar_victoriametrics 24 5
  wait_for_container_running dabljaar_tempo 24 5
  wait_for_container_running dabljaar_otel_collector 24 5
  observability_data_end="$(date +%s)"
  log "Observability data plane up in $((observability_data_end - observability_data_start))s"
fi

# ---------------------------------------------------------------------------
# Phase C: Database migrations
# Run in a one-off backend container with --no-deps (infra already running).
# ---------------------------------------------------------------------------
phase "DATABASE MIGRATIONS"

run_migrations() {
  local migrate_cmd='alembic upgrade head'
  local migrate_name="dabljaar_migrate_$(date +%s)"
  log "Building backend image for migrations at ${DEPLOY_SHA}"
  $COMPOSE build backend
  log "Running migrations via one-off backend container ($migrate_name)"
  if command -v timeout >/dev/null 2>&1; then
    timeout 600 $COMPOSE run --rm --no-deps --name "$migrate_name" \
      --entrypoint sh backend -lc "$migrate_cmd"
  else
    $COMPOSE run --rm --no-deps --name "$migrate_name" \
      --entrypoint sh backend -lc "$migrate_cmd"
  fi
}
run_migrations
log "Migrations complete."

# ---------------------------------------------------------------------------
# Phase D: AI services tier — stt, nmt, tts, media, orchestrator
# Start these in the background while backend builds. They self-warm models.
# ---------------------------------------------------------------------------
phase "AI SERVICES TIER (stt, nmt, tts, media, orchestrator)"

ai_up_start="$(date +%s)"
$COMPOSE up -d --build \
  stt-service nmt-service tts-service media-service orchestrator
log "AI services started (model pre-warming in background)."
ai_up_end="$(date +%s)"
log "AI services tier issued in $((ai_up_end - ai_up_start))s"

# ---------------------------------------------------------------------------
# Phase E: Backend
# ---------------------------------------------------------------------------
phase "BACKEND"

app_up_start="$(date +%s)"
$COMPOSE up -d --build backend
log "Backend container started."

# ---------------------------------------------------------------------------
# Phase E2: Observability agents + Grafana (optional, before Caddy)
# ---------------------------------------------------------------------------
if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  phase "OBSERVABILITY AGENTS (promtail, exporters, grafana)"
  observability_agents_start="$(date +%s)"
  $COMPOSE up -d promtail node_exporter cadvisor postgres_exporter grafana
  wait_for_grafana_health 36 5
  observability_agents_end="$(date +%s)"
  log "Observability agents up in $((observability_agents_end - observability_agents_start))s"
fi

# ---------------------------------------------------------------------------
# Phase E3: Caddy — force-recreate picks up fresh frontend/dist bind mount
# ---------------------------------------------------------------------------
phase "CADDY"

$COMPOSE up -d --force-recreate caddy
log "Caddy container force-recreated (picks up fresh frontend/dist and Caddyfile.production)."
app_up_end="$(date +%s)"
log "Backend + observability + Caddy tier up in $((app_up_end - app_up_start))s"

# ---------------------------------------------------------------------------
# Readiness gates — wait for each service to confirm it's accepting requests
# ---------------------------------------------------------------------------
phase "READINESS GATES"

wait_for_readiness() {
  local service="$1"
  local url="$2"
  local label="$3"
  local max_attempts="${4:-60}"
  local sleep_s="${5:-10}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if $COMPOSE exec -T "$service" curl -fsS "$url" >/dev/null 2>&1; then
      log "$label readiness check passed (attempt $attempt)"
      return 0
    fi
    log "  $label: attempt $attempt/$max_attempts, retrying in ${sleep_s}s..."
    sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
  log "FAIL: $label ($service) readiness check timed out after $((max_attempts * sleep_s))s"
  return 1
}

wait_for_backend_health() {
  local max_attempts="${1:-40}"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if $COMPOSE exec -T backend python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" \
        >/dev/null 2>&1; then
      log "backend health check passed (attempt $attempt)"
      return 0
    fi
    log "  backend: attempt $attempt/$max_attempts, retrying in 5s..."
    sleep 5
    attempt=$((attempt + 1))
  done
  log "FAIL: backend health check timed out"
  return 1
}

readiness_start="$(date +%s)"

wait_for_backend_health 40
wait_for_readiness orchestrator http://localhost:8081/readiness orchestrator 12 5
wait_for_readiness media-service http://localhost:8003/readiness media 12 10

# AI services: longer wait (model loading). These are non-blocking for
# user traffic — backend + caddy are already serving requests above.
wait_for_readiness stt-service http://localhost:8001/readiness stt 60 10
wait_for_readiness nmt-service http://localhost:8002/readiness nmt 60 10
wait_for_readiness tts-service http://localhost:8005/readiness tts 90 10

readiness_end="$(date +%s)"
log "All readiness gates passed in $((readiness_end - readiness_start))s"

# Validate Caddy config inside the live container as a final sanity check.
$COMPOSE exec -T caddy caddy validate --config /etc/caddy/Caddyfile
log "Live Caddy config validated."

# ---------------------------------------------------------------------------
# Phase F: External health checks
# ---------------------------------------------------------------------------
phase "EXTERNAL HEALTH CHECKS"

health_checks_start="$(date +%s)"

# Edge API check — use the backend container directly to avoid the
# HTTP→HTTPS redirect that Caddy applies to plain-HTTP requests.
# (curl -f fails on 3xx, and Caddy redirects port-80 requests to HTTPS.)
edge_api_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  # Primary: check via backend container (bypasses Caddy redirect)
  if $COMPOSE exec -T backend python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" \
      >/dev/null 2>&1; then
    edge_api_healthy=true
    break
  fi
  # Secondary: HTTPS external (follows redirects, verifies TLS)
  if curl -fsS --max-time 10 "https://${DOMAIN_VALUE}/api/health" >/dev/null 2>&1; then
    edge_api_healthy=true
    break
  fi
  sleep 5
done

if [ "$edge_api_healthy" != "true" ]; then
  log "FAIL: API health check failed (both backend-direct and https://${DOMAIN_VALUE}/api/health)"
  exit 1
fi
log "Edge API health check passed."

# External HTTPS API check.
external_api_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  if curl -fsS --max-time 15 "https://${DOMAIN_VALUE}/api/health" >/dev/null 2>&1; then
    external_api_healthy=true
    break
  fi
  sleep 5
done

if [ "$external_api_healthy" != "true" ]; then
  log "FAIL: public API health check failed on https://${DOMAIN_VALUE}/api/health"
  exit 1
fi
log "External HTTPS API check passed."

# SPA root check — use --insecure only for the initial ACME cert provisioning
# window; normal deploys will have a valid cert.
spa_root_healthy=false
spa_headers_healthy=false
for _ in 1 2 3 4 5 6 7 8; do
  spa_headers="$(curl -fsS --max-time 15 --insecure -I "https://${DOMAIN_VALUE}/" 2>/dev/null || true)"
  if echo "$spa_headers" | grep -Eqi 'strict-transport-security'; then
    spa_headers_healthy=true
  fi
  if curl -fsS --max-time 15 --insecure "https://${DOMAIN_VALUE}/" | grep -Eqi '<!doctype html|<html'; then
    spa_root_healthy=true
  fi
  if [ "$spa_root_healthy" = "true" ] && [ "$spa_headers_healthy" = "true" ]; then
    break
  fi
  sleep 5
done

if [ "$spa_headers_healthy" != "true" ]; then
  log "FAIL: GET / missing Strict-Transport-Security — Caddy {$DOMAIN} site block not routing"
  exit 1
fi

if [ "$spa_root_healthy" != "true" ]; then
  log "FAIL: public SPA root check failed on https://${DOMAIN_VALUE}/"
  exit 1
fi
log "SPA root and security headers check passed."

if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  grafana_external_healthy=false
  GRAFANA_BASIC_AUTH_USER="$(grep -E '^[[:space:]]*GRAFANA_BASIC_AUTH_USER=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
  GRAFANA_BASIC_AUTH_USER="${GRAFANA_BASIC_AUTH_USER:-admin}"
  GRAFANA_ADMIN_PASSWORD="$(grep -E '^[[:space:]]*GRAFANA_ADMIN_PASSWORD=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
  for _ in 1 2 3 4 5 6 7 8; do
    if curl -fsS --max-time 15 -u "${GRAFANA_BASIC_AUTH_USER}:${GRAFANA_ADMIN_PASSWORD}" \
        "https://grafana.${DOMAIN_VALUE}/api/health" >/dev/null 2>&1; then
      grafana_external_healthy=true
      break
    fi
    sleep 5
  done
  if [ "$grafana_external_healthy" != "true" ]; then
    log "FAIL: Grafana external health check failed on https://grafana.${DOMAIN_VALUE}/api/health"
    exit 1
  fi
  log "Grafana external health check passed (https://grafana.${DOMAIN_VALUE})."
fi

health_checks_end="$(date +%s)"
log "All external health checks passed in $((health_checks_end - health_checks_start))s"

# ---------------------------------------------------------------------------
# Post-deploy: prune old Docker images to reclaim disk space
# ---------------------------------------------------------------------------
phase "POST-DEPLOY CLEANUP"

log "Pruning dangling images and stopped containers..."
docker image prune -f >/dev/null 2>&1 || true
docker container prune -f >/dev/null 2>&1 || true
log "Cleanup done."

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
phase "DEPLOY COMPLETE"

DEPLOYED_SHA="$(git rev-parse --short HEAD)"
compose_up_seconds=$(( (app_up_end - infra_up_start) ))
total_seconds=$(( (health_checks_end - frontend_build_start) ))

echo ""
echo "deployment timing:"
echo "  frontend_build   = ${frontend_build_seconds}s"
echo "  infra_tier       = $((infra_up_end - infra_up_start))s"
echo "  ai_tier          = $((ai_up_end - ai_up_start))s (async — still warming)"
echo "  backend_caddy    = $((app_up_end - app_up_start))s"
echo "  readiness_gates  = $((readiness_end - readiness_start))s"
echo "  health_checks    = $((health_checks_end - health_checks_start))s"
if [ "$OBSERVABILITY_ENABLED" = "true" ] && [ "$observability_data_end" -gt 0 ]; then
  echo "  obs_data_plane   = $((observability_data_end - observability_data_start))s"
fi
if [ "$OBSERVABILITY_ENABLED" = "true" ] && [ "$observability_agents_end" -gt 0 ]; then
  echo "  obs_agents       = $((observability_agents_end - observability_agents_start))s"
fi
echo "  ─────────────────────────────────────"
echo "  total            = ${total_seconds}s"
echo ""
echo "deployed $DEPLOYED_SHA on branch $(git branch --show-current) → https://${DOMAIN_VALUE}/"
if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  echo "observability: https://grafana.${DOMAIN_VALUE}/"
fi
$COMPOSE ps
