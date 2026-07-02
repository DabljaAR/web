# Shared Docker Compose file selection for production microservices stack.
# Source from repo root: source infra/scripts/lib/compose-env.sh
#
# Sets: COMPOSE_CMD, COMPOSE_FILES, COMPOSE
# Requires: ENV_FILE (default .env.production), optional APP_DIR for env path
# Opt-in observability: COMPOSE_PROFILES=observability in .env.production

: "${ENV_FILE:=.env.production}"

COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  fi
fi

COMPOSE_FILES="-f docker-compose.microservices.prod.yml -f docker-compose.observability.yml"
COMPOSE="$COMPOSE_CMD --env-file $ENV_FILE $COMPOSE_FILES"

if ! $COMPOSE_CMD version >/dev/null 2>&1; then
  echo "Neither docker compose nor docker-compose is available" >&2
  exit 1
fi
