#!/usr/bin/env bash
# Integration test for the orchestrator.
# Starts the orchestrator, seeds a fake job, publishes a job.created message,
# then watches the DB to confirm the orchestrator updated the job status.

set -euo pipefail

export PATH=$HOME/go-install/go/bin:$HOME/go/bin:$PATH

RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
DATABASE_URL="postgres://postgres:postgres@localhost:5433/dabljaar"
JOB_ID="test-job-$(date +%s)"
HEALTH_PORT=8082  # avoid conflict if 8081 is taken

cleanup() {
  echo ""
  echo "--- Cleanup ---"
  # Kill orchestrator if running
  [[ -n "${ORCH_PID:-}" ]] && kill "$ORCH_PID" 2>/dev/null && echo "Orchestrator stopped"

  # Remove seeded test data
  docker exec dabljaar_postgres psql -U postgres -d dabljaar \
    -c "DELETE FROM jobs WHERE id = '$JOB_ID';" \
    -c "DELETE FROM videos WHERE id = 'test-video-$JOB_ID';" \
    -c "DELETE FROM users WHERE email = 'testorchestrator@test.com';" 2>/dev/null || true

  echo "Test data cleaned up."
}
trap cleanup EXIT

echo "=== Orchestrator Integration Test ==="
echo ""

# ── 1. Seed test data ──────────────────────────────────────────────────────────
echo "[1/4] Seeding test user, video, and job into PostgreSQL..."

docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "INSERT INTO users (username, email, password, is_active, created_at, updated_at, last_login, preferred_language, default_domain, translation_style, default_voice, notif_completed, notif_credits, notif_marketing) VALUES ('test_orchestrator', 'testorchestrator@test.com', 'noop', true, now(), now(), now(), 'en', 'com', 'formal', 'default', false, false, false) ON CONFLICT (email) DO UPDATE SET username='test_orchestrator';" \
  -c "INSERT INTO videos (id, user_id, title, original_filename, file_path, status, created_at, updated_at) VALUES ('test-video-$JOB_ID', (SELECT user_id FROM users WHERE email='testorchestrator@test.com'), 'Test Video', 'test.mp4', '/tmp/test.mp4', 'PENDING', now(), now()) ON CONFLICT (id) DO NOTHING;" \
  -c "INSERT INTO jobs (id, video_id, user_id, job_type, status, progress, retry_count, max_retries, created_at, updated_at) VALUES ('$JOB_ID', 'test-video-$JOB_ID', (SELECT user_id FROM users WHERE email='testorchestrator@test.com'), 'FULL_DUBBING_PIPELINE', 'QUEUED', 0.0, 0, 3, now(), now());" 2>&1

echo "   Job '$JOB_ID' inserted with status=QUEUED"
echo ""

# ── 2. Build & start orchestrator ─────────────────────────────────────────────
echo "[2/4] Building orchestrator..."
cd "$(dirname "$0")"
go build -o /tmp/orchestrator_bin ./cmd/server/
echo "   Build OK"
echo ""

echo "   Starting orchestrator (logs → /tmp/orchestrator.log)..."
RABBITMQ_URL="$RABBITMQ_URL" \
DATABASE_URL="$DATABASE_URL" \
HEALTH_PORT="$HEALTH_PORT" \
WORKER_POOL_SIZE=4 \
  /tmp/orchestrator_bin > /tmp/orchestrator.log 2>&1 &
ORCH_PID=$!

# Wait for it to be ready (health endpoint)
echo "   Waiting for health endpoint on :$HEALTH_PORT ..."
for i in $(seq 1 15); do
  if curl -sf "http://localhost:$HEALTH_PORT/health" >/dev/null 2>&1; then
    echo "   Orchestrator is up (pid=$ORCH_PID)"
    break
  fi
  sleep 1
  if [[ $i -eq 15 ]]; then
    echo "   ERROR: orchestrator did not start in time. Logs:"
    cat /tmp/orchestrator.log
    exit 1
  fi
done
echo ""

# ── 3. Publish job.created message via RabbitMQ management API ────────────────
echo "[3/4] Publishing 'job.created' message to RabbitMQ..."
PAYLOAD=$(printf '{"job_id":"%s"}' "$JOB_ID")
PAYLOAD_B64=$(echo -n "$PAYLOAD" | base64 -w0)

curl -sf -u guest:guest \
  -H "Content-Type: application/json" \
  -d "{
    \"routing_key\": \"job.created\",
    \"payload\": \"$PAYLOAD_B64\",
    \"payload_encoding\": \"base64\",
    \"properties\": {\"delivery_mode\": 2, \"content_type\": \"application/json\"}
  }" \
  "http://localhost:15672/api/exchanges/%2F/dablja.jobs.exchange/publish" | python3 -c "import sys,json; r=json.load(sys.stdin); print('   Published:', r)"

echo ""

# ── 4. Poll DB for status change ───────────────────────────────────────────────
echo "[4/4] Waiting for orchestrator to update job status..."
for i in $(seq 1 20); do
  STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -t -c \
    "SELECT status FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null | tr -d ' \n')
  echo "   attempt $i: status = $STATUS"
  if [[ "$STATUS" == "PROCESSING" || "$STATUS" == "COMPLETED" || "$STATUS" == "FAILED" ]]; then
    echo ""
    echo "=== PASS: Orchestrator reacted! Job '$JOB_ID' is now '$STATUS' ==="
    echo ""
    echo "--- Orchestrator logs ---"
    cat /tmp/orchestrator.log
    exit 0
  fi
  sleep 2
done

echo ""
echo "=== FAIL: Job status never changed from QUEUED within 40s ==="
echo ""
echo "--- Orchestrator logs ---"
cat /tmp/orchestrator.log
exit 1
