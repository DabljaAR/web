#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
wait_for_postgres() {
    local max_attempts=30
    local attempt=1
    local wait_seconds=2
    
    echo "Waiting for PostgreSQL to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if pg_isready -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dabljaar}" 2>/dev/null; then
            echo "✓ PostgreSQL is ready!"
            return 0
        fi
        
        echo "  Attempt $attempt/$max_attempts: PostgreSQL not ready yet, retrying in ${wait_seconds}s..."
        sleep $wait_seconds
        attempt=$((attempt + 1))
    done
    
    echo "✗ PostgreSQL failed to become ready after ${max_attempts} attempts (${max_attempts} * ${wait_seconds}s = ~${max_attempts}s)"
    return 1
}

# Wait for postgres before running migrations
wait_for_postgres || {
    echo "ERROR: Could not connect to PostgreSQL. Check:"
    echo "  1. Postgres container is running: docker-compose ps"
    echo "  2. POSTGRES_PASSWORD is set correctly in .env"
    echo "  3. Postgres host is reachable at ${POSTGRES_HOST:-postgres}"
    exit 1
}

run_alembic_upgrade() {
    local output
    local status

    set +e
    output="$(alembic upgrade head 2>&1)"
    status=$?
    set -e

    if [[ $status -eq 0 ]]; then
        echo "$output"
        return 0
    fi

    echo "$output"

    if grep -q "Can't locate revision identified by" <<<"$output"; then
        local missing_rev
        missing_rev="$(sed -n "s/.*Can't locate revision identified by '\([^']*\)'.*/\1/p" <<<"$output")"
        echo "FATAL: Database alembic_version points to revision '${missing_rev:-unknown}',"
        echo "       which is not in this repo. Your Postgres volume has a stale/incompatible schema."
        echo ""
        echo "  Fix (destroys local data — safe for dev):"
        echo "    docker compose down -v && docker compose up -d"
        echo ""
        echo "  Fix (keep data — advanced):"
        echo "    docker compose exec postgres psql -U postgres -d dabljaar -c \"DELETE FROM alembic_version;\""
        echo "    docker compose exec backend alembic upgrade head"
        return 1
    fi

    echo "ERROR: Database migrations failed."
    return 1
}

echo "Running database migrations..."
run_alembic_upgrade || exit 1

echo "Starting application..."
exec "$@"
