# Shared Docker Compose file selection for production microservices stack.
# Source from repo root: source infra/scripts/lib/compose-env.sh
#
# Sets: COMPOSE_CMD, COMPOSE_FILES, COMPOSE, OBSERVABILITY_ENABLED
# Requires: ENV_FILE (default .env.production), optional APP_DIR for env path

: "${ENV_FILE:=.env.production}"

_obs_env_path="$ENV_FILE"
if [ -n "${APP_DIR:-}" ] && [ "${ENV_FILE#/}" = "$ENV_FILE" ]; then
  _obs_env_path="$APP_DIR/$ENV_FILE"
fi

observability_enabled() {
  grep -q '^GRAFANA_ADMIN_PASSWORD=.' "$_obs_env_path" 2>/dev/null
}

OBSERVABILITY_ENABLED=false
if observability_enabled; then
  OBSERVABILITY_ENABLED=true
fi

COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  fi
fi

COMPOSE_FILES="-f docker-compose.microservices.prod.yml"
if [ "$OBSERVABILITY_ENABLED" = "true" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.observability.yml"
fi

COMPOSE="$COMPOSE_CMD --env-file $ENV_FILE $COMPOSE_FILES"

if ! $COMPOSE_CMD version >/dev/null 2>&1; then
  echo "Neither docker compose nor docker-compose is available" >&2
  exit 1
fi
