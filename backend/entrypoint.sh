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

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
