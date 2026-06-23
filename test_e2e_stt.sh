#!/usr/bin/env bash
# test_e2e_stt.sh — End-to-end test: orchestrator → STT microservice
#
# Flow tested:
#   [this script]   → publishes  job.created        → RabbitMQ
#   [orchestrator]  → receives   job.created        → marks PROCESSING, publishes job.start.stt
#   [stt-service]   → receives   job.start.stt      → downloads audio from MinIO, transcribes
#   [stt-service]   → publishes  job.results.stt    → RabbitMQ
#   [orchestrator]  → receives   job.results.stt    → marks COMPLETED, advances pipeline
#
# Prerequisites (already running):
#   docker compose up -d postgres rabbitmq minio orchestrator
# This script starts stt-service automatically if not running.

set -euo pipefail
cd "$(dirname "$0")"

# ── Config ────────────────────────────────────────────────────────────────────
TEST_VIDEO_FILE="PHP in 100 Seconds [a7_WFUlFS94].mp4"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-stt-${TS}"
VIDEO_ID="e2e-video-${TS}"
MINIO_KEY="test-e2e/${TS}.mp4"
POLL_TIMEOUT=180  # seconds — STT on CPU can be slow

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Cleanup ───────────────────────────────────────────────────────────────────
cleanup() {
    echo ""
    warn "Cleaning up test data..."
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -q \
        -c "DELETE FROM jobs   WHERE id    = '$JOB_ID';" \
        -c "DELETE FROM videos WHERE id    = '$VIDEO_ID';" \
        -c "DELETE FROM users  WHERE email = 'e2e_stt@test.com';" 2>/dev/null || true
    docker exec dabljaar_minio mc rm "local/$BUCKET/$MINIO_KEY" --quiet 2>/dev/null || true
    ok "Done."
}
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║   E2E Test: Orchestrator → STT Microservice   ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Check prerequisites ───────────────────────────────────────────────
info "Checking required containers..."
for svc in dabljaar_postgres dabljaar_rabbitmq dabljaar_minio dabljaar_orchestrator; do
    running=$(docker inspect --format '{{.State.Running}}' "$svc" 2>/dev/null || echo "false")
    [[ "$running" == "true" ]] || fail "$svc is not running. Start it with: docker compose up -d"
done
ok "postgres, rabbitmq, minio, orchestrator — all running"

# Start stt-service if not up
running=$(docker inspect --format '{{.State.Running}}' dabljaar_stt_service 2>/dev/null || echo "false")
if [[ "$running" != "true" ]]; then
    warn "stt-service not running — starting it..."
    docker compose up -d stt-service
    warn "Waiting 15s for STT service to initialize..."
    sleep 15
fi
ok "stt-service — running"
echo ""

# ── Step 2: Upload test audio to MinIO ────────────────────────────────────────
info "Uploading test audio to MinIO..."

[[ -f "$TEST_VIDEO_FILE" ]] || fail "Test file not found: $TEST_VIDEO_FILE"

# Configure mc local alias (MinIO container already has 'local' pre-wired but sometimes needs creds)
docker exec dabljaar_minio mc alias set local http://localhost:9000 minioadmin minioadmin --quiet 2>/dev/null || true

# Create bucket if needed
docker exec dabljaar_minio mc mb "local/$BUCKET" --ignore-existing --quiet 2>/dev/null || true

# Copy file into container, then upload via mc
docker cp "$TEST_VIDEO_FILE" dabljaar_minio:/tmp/e2e_test_audio.mp4
docker exec dabljaar_minio mc cp /tmp/e2e_test_audio.mp4 "local/$BUCKET/$MINIO_KEY" --quiet

ok "Uploaded → $BUCKET/$MINIO_KEY"
echo ""

# ── Step 3: Seed PostgreSQL ───────────────────────────────────────────────────
info "Seeding test data in PostgreSQL..."

USER_ID=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq -c "
    INSERT INTO users (
        username, email, password, is_active,
        created_at, updated_at, last_login,
        preferred_language, default_domain, translation_style, default_voice,
        notif_completed, notif_credits, notif_marketing
    ) VALUES (
        'e2e_stt_user', 'e2e_stt@test.com', 'noop', true,
        now(), now(), now(), 'en', 'com', 'formal', 'default',
        false, false, false
    )
    ON CONFLICT (email) DO UPDATE SET username = 'e2e_stt_user'
    RETURNING user_id;
" 2>/dev/null | tr -d ' \n')
[[ -n "$USER_ID" ]] || fail "Failed to create test user"
ok "User created (user_id=$USER_ID)"

docker exec dabljaar_postgres psql -U postgres -d dabljaar -q -c "
    INSERT INTO videos (
        id, user_id, title, original_filename, file_path, status, media_type, created_at, updated_at
    ) VALUES (
        '$VIDEO_ID', $USER_ID,
        'E2E STT Test Video', 'php_100s.mp4', '$MINIO_KEY',
        'COMPLETED', 'VIDEO', now(), now()
    )
    ON CONFLICT (id) DO NOTHING;
" 2>/dev/null
ok "Video created (video_id=$VIDEO_ID, file_path=$MINIO_KEY)"

docker exec dabljaar_postgres psql -U postgres -d dabljaar -q -c "
    INSERT INTO jobs (
        id, video_id, user_id, job_type, status,
        progress, retry_count, max_retries, input_data, created_at, updated_at
    ) VALUES (
        '$JOB_ID', '$VIDEO_ID', $USER_ID,
        'STT_TRANSCRIBE', 'QUEUED',
        0.0, 0, 3,
        '{\"video_id\": \"$VIDEO_ID\", \"language\": \"en\", \"target_lang\": \"arb_Arab\"}'::jsonb,
        now(), now()
    );
" 2>/dev/null
ok "Job created (job_id=$JOB_ID, type=STT_TRANSCRIBE, status=QUEUED)"
echo ""

# ── Step 4: Publish job.created → RabbitMQ ───────────────────────────────────
info "Publishing job.created to RabbitMQ..."

PAYLOAD="{\"job_id\":\"$JOB_ID\"}"

# rabbitmqadmin is bundled with the management image
docker exec dabljaar_rabbitmq rabbitmqadmin publish \
    exchange=dablja.jobs.exchange \
    routing_key=job.created \
    payload="$PAYLOAD" \
    properties='{"delivery_mode":2,"content_type":"application/json"}' \
    2>/dev/null

ok "job.created published for $JOB_ID"
echo ""

# ── Step 5: Poll for status transitions ──────────────────────────────────────
echo "─────────────────────────────────────────────────"
info "Watching pipeline (timeout: ${POLL_TIMEOUT}s)..."
echo "─────────────────────────────────────────────────"

LAST_STATUS=""
ELAPSED=0
START_TIME=$SECONDS

while [[ $ELAPSED -lt $POLL_TIMEOUT ]]; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null | tr -d ' \n')

    if [[ "$STATUS" != "$LAST_STATUS" ]]; then
        TS_NOW=$(date '+%H:%M:%S')
        case "$STATUS" in
            QUEUED)     echo "  [$TS_NOW] ⏳ QUEUED     — waiting for orchestrator" ;;
            PROCESSING) echo "  [$TS_NOW] 🔄 PROCESSING — orchestrator dispatched to STT service" ;;
            COMPLETED)  echo -e "  [$TS_NOW] ${GREEN}✅ COMPLETED${NC}  — STT finished!" ;;
            FAILED)     echo -e "  [$TS_NOW] ${RED}❌ FAILED${NC}" ;;
            *)          echo "  [$TS_NOW] ? $STATUS" ;;
        esac
        LAST_STATUS="$STATUS"
    fi

    [[ "$STATUS" == "COMPLETED" || "$STATUS" == "FAILED" ]] && break

    sleep 2
    ELAPSED=$(( SECONDS - START_TIME ))
done

ELAPSED=$(( SECONDS - START_TIME ))
echo ""

# ── Step 6: Results ───────────────────────────────────────────────────────────
if [[ "$LAST_STATUS" == "COMPLETED" ]]; then
    echo "╔════════════════════════════════════════════════╗"
    echo -e "║  ${GREEN}PASS${NC} — Full pipeline completed in ${ELAPSED}s          ║"
    echo "╚════════════════════════════════════════════════╝"
    echo ""

    echo "── Transcript ───────────────────────────────────"
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT output_data->>'transcript' FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null
    echo ""

    echo "── Metadata ─────────────────────────────────────"
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT jsonb_pretty((output_data->'metadata')::jsonb) FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null
    echo ""

    echo "── Segments (first 3) ───────────────────────────"
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT jsonb_pretty(output_data->'segments'->0), jsonb_pretty(output_data->'segments'->1), jsonb_pretty(output_data->'segments'->2) FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null
    echo ""

elif [[ "$LAST_STATUS" == "FAILED" ]]; then
    echo "╔════════════════════════════════════════════════╗"
    echo -e "║  ${RED}FAIL${NC} — STT job failed                          ║"
    echo "╚════════════════════════════════════════════════╝"
    echo ""
    echo "── Error message ────────────────────────────────"
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT error_message FROM jobs WHERE id = '$JOB_ID';" 2>/dev/null
    echo ""
    echo "── STT service logs (last 40 lines) ─────────────"
    docker logs dabljaar_stt_service --tail 40 2>/dev/null || true
    exit 1

else
    echo "╔════════════════════════════════════════════════╗"
    echo -e "║  ${RED}TIMEOUT${NC} — Status still '$LAST_STATUS' after ${POLL_TIMEOUT}s ║"
    echo "╚════════════════════════════════════════════════╝"
    echo ""
    echo "── Orchestrator logs (last 20 lines) ────────────"
    docker logs dabljaar_orchestrator --tail 20 2>/dev/null || true
    echo ""
    echo "── STT service logs (last 30 lines) ─────────────"
    docker logs dabljaar_stt_service --tail 30 2>/dev/null || true
    exit 1
fi
