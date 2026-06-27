#!/usr/bin/env bash
# ─── Integration Test Runner ────────────────────────────────────────────────
# Starts the test infrastructure, runs integration tests, and cleans up.
#
# Usage:
#   ./run_integration_tests.sh            # full run
#   ./run_integration_tests.sh --skip-build  # reuse existing images
#   ./run_integration_tests.sh --orchestrator-only  # only orchestrator tests
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")"

COMPOSE_FILE="../docker-compose.test.yml"
PYTEST_ARGS=(
    "-v"
    "--run-integration"
    "--tb=long"
    "-ra"
)
SKIP_BUILD=""
TEST_PATH="tests/integration/"

# ─── Parse args ────────────────────────────────────────────────────────────

for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD="--no-build" ;;
        --orchestrator-only) TEST_PATH="tests/integration/test_orchestrator.py" ;;
        *)
            echo "Usage: $0 [--skip-build] [--orchestrator-only]"
            exit 1
            ;;
    esac
done

# ─── Prerequisites ─────────────────────────────────────────────────────────

echo "🔍 Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "❌ docker not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 not found"; exit 1; }

# Check venv has required packages
python3 -c "import psycopg2, aio_pika" 2>/dev/null || {
    echo "📦 Installing integration test dependencies..."
    pip install psycopg2-binary aio-pika
}

# ─── Start infrastructure ──────────────────────────────────────────────────

echo ""
echo "🚀 Starting test infrastructure..."
echo "    Compose file: $COMPOSE_FILE"
echo ""

docker compose -f "$COMPOSE_FILE" up -d $SKIP_BUILD postgres rabbitmq minio redis orchestrator backend

echo ""
echo "⏳ Waiting for infrastructure to be healthy..."
echo ""

# Wait for orchestrator health endpoint
ORCHESTRATOR_HEALTHY=false
for i in $(seq 1 30); do
    if curl -s http://localhost:8082/health 2>/dev/null | grep -q '"status":"ok"'; then
        ORCHESTRATOR_HEALTHY=true
        echo "✅ Orchestrator healthy (attempt $i)"
        break
    fi
    echo "   Waiting for orchestrator... ($i/30)"
    sleep 2
done

if [ "$ORCHESTRATOR_HEALTHY" = false ]; then
    echo ""
    echo "❌ Orchestrator did not become healthy within 60s"
    echo "   Container logs:"
    docker compose -f "$COMPOSE_FILE" logs orchestrator --tail 30
    echo ""
    echo "   Run 'docker compose -f $COMPOSE_FILE down -v' to clean up"
    exit 1
fi

# Quick DB connection check
echo -n "   Checking PostgreSQL connectivity... "
python3 -c "
import psycopg2
conn = psycopg2.connect('host=localhost port=5433 dbname=dabljaar user=postgres password=postgres')
conn.close()
print('✅')
" 2>&1 || {
    echo "❌"
    echo "PostgreSQL connection failed"
    docker compose -f "$COMPOSE_FILE" logs postgres --tail 20
    exit 1
}

# Quick RabbitMQ connectivity check
echo -n "   Checking RabbitMQ connectivity... "
python3 -c "
import asyncio, aio_pika
async def check():
    conn = await aio_pika.connect_robust('amqp://guest:guest@localhost:5673/')
    await conn.close()
asyncio.run(check())
print('✅')
" 2>&1 || {
    echo "❌"
    echo "RabbitMQ connection failed"
    docker compose -f "$COMPOSE_FILE" logs rabbitmq --tail 20
    exit 1
}

echo ""
echo "✅ All infrastructure is healthy"
echo ""

# ─── Run tests ─────────────────────────────────────────────────────────────

echo "🧪 Running integration tests..."
echo "    Path: $TEST_PATH"
echo ""

cd backend

python3 -m pytest "$TEST_PATH" "${PYTEST_ARGS[@]}"

EXIT_CODE=$?

cd ..

# ─── Summary ───────────────────────────────────────────────────────────────

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All integration tests passed!"
else
    echo "❌ Some integration tests failed (exit code: $EXIT_CODE)"
    echo ""
    echo "   Infrastructure is still running. Inspect logs with:"
    echo "   docker compose -f $COMPOSE_FILE logs orchestrator --tail 50"
    echo ""
    echo "   When done: docker compose -f $COMPOSE_FILE down -v"
fi

echo ""
echo "   Keep infrastructure running? [Y/n]: "
read -r KEEP
if [[ "$KEEP" =~ ^[Nn] ]]; then
    echo "   Stopping and cleaning up..."
    docker compose -f "$COMPOSE_FILE" down -v
    echo "✅ Done"
else
    echo "   Infrastructure kept running. To stop:"
    echo "   docker compose -f $COMPOSE_FILE down -v"
fi

exit $EXIT_CODE
