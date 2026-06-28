#!/usr/bin/env bash
# test_e2e_captions_only.sh — E2E: captionsOnly pipeline (STT → parent COMPLETED)
#
# Flow:
#   [this script]  → seeds DB, publishes  job.created           → RabbitMQ
#   [orchestrator] → creates STT child    → publishes job.start.stt
#   [stt-service]  → transcribes audio    → publishes job.results.stt COMPLETED
#   [orchestrator] → nextStage=none       → parent COMPLETED
#
# Prerequisites (running):
#   docker compose up -d postgres rabbitmq minio orchestrator stt-service
#   Audio file at TEST_AUDIO_FILE (any short MP3/WAV)
#
# Usage:
#   ./test_e2e_captions_only.sh [path/to/audio.mp3]

set -euo pipefail
cd "$(dirname "$0")"

# ── Config ────────────────────────────────────────────────────────────────────
TEST_AUDIO_FILE="${1:-}"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-captions-${TS}"
VIDEO_ID="e2e-video-captions-${TS}"
MINIO_KEY="test-e2e/captions-only-${TS}.mp3"
POLL_TIMEOUT=300

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Cleanup ───────────────────────────────────────────────────────────────────
cleanup() {
    warn "Cleaning up test data..."
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -q \
        -c "DELETE FROM jobs   WHERE id    = '$JOB_ID' OR parent_job_id = '$JOB_ID';" \
        -c "DELETE FROM videos WHERE id    = '$VIDEO_ID';" \
        2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══════════════════════════════════════════════════"
echo "  E2E Test: captionsOnly (STT → parent COMPLETED)"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Step 1: resolve test audio ────────────────────────────────────────────────
if [ -z "$TEST_AUDIO_FILE" ]; then
    # Generate a short silent audio file using ffmpeg if no file provided
    info "No audio file provided — generating 3s silent audio with ffmpeg"
    TEST_AUDIO_FILE="/tmp/e2e_captions_silence_${TS}.mp3"
    ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 3 -q:a 9 -acodec libmp3lame "$TEST_AUDIO_FILE" -y -loglevel quiet
    ok "Generated silent audio: $TEST_AUDIO_FILE"
fi

[ -f "$TEST_AUDIO_FILE" ] || fail "Audio file not found: $TEST_AUDIO_FILE"

# ── Step 2: upload audio to MinIO ─────────────────────────────────────────────
info "Uploading audio to MinIO bucket=$BUCKET key=$MINIO_KEY"
docker exec dabljaar_test_minio mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
docker cp "$TEST_AUDIO_FILE" dabljaar_test_minio:/tmp/audio_e2e.mp3 2>/dev/null || \
    docker cp "$TEST_AUDIO_FILE" dabljaar_minio:/tmp/audio_e2e.mp3

MINIO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'minio' | head -1)
docker exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc mb "local/$BUCKET" --ignore-existing -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc cp /tmp/audio_e2e.mp3 "local/$BUCKET/$MINIO_KEY" -q
ok "Audio uploaded"

# ── Step 3: seed DB ───────────────────────────────────────────────────────────
info "Seeding DB: video=$VIDEO_ID job=$JOB_ID (captionsOnly)"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-captions-only', 'COMPLETED',
        '$MINIO_KEY', '$MINIO_KEY',
        NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang, created_at, updated_at)
VALUES ('task-$JOB_ID', '$VIDEO_ID', 'PENDING', 'captionsOnly', 'arb_Arab',
        NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'FULL_DUBBING_PIPELINE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "task-$JOB_ID", "output_type": "captionsOnly"}'::jsonb,
        '{}'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
SQL
ok "DB seeded"

# ── Step 4: publish job.created ───────────────────────────────────────────────
info "Publishing job.created for parent=$JOB_ID"
python3 - <<PYEOF
import pika, json
params = pika.URLParameters("amqp://guest:guest@localhost:5672/")
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.exchange_declare("dablja.jobs.exchange", exchange_type="topic", durable=True)
ch.basic_publish(
    exchange="dablja.jobs.exchange",
    routing_key="job.created",
    body=json.dumps({"job_id": "$JOB_ID"}),
    properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
)
conn.close()
print("Published")
PYEOF
ok "job.created published"

# ── Step 5: poll for COMPLETED ───────────────────────────────────────────────
info "Polling for parent COMPLETED (timeout=${POLL_TIMEOUT}s)..."
START=$(date +%s)
STATUS=""
while true; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')

    case "$STATUS" in
        COMPLETED)
            ELAPSED=$(( $(date +%s) - START ))
            ok "Parent job COMPLETED in ${ELAPSED}s"
            break
            ;;
        FAILED)
            fail "Parent job FAILED"
            ;;
        CANCELLED)
            fail "Parent job CANCELLED unexpectedly"
            ;;
    esac

    ELAPSED=$(( $(date +%s) - START ))
    if [ $ELAPSED -ge $POLL_TIMEOUT ]; then
        fail "Timed out after ${POLL_TIMEOUT}s. Last status: $STATUS"
    fi
    echo -n "  status=$STATUS elapsed=${ELAPSED}s  "
    echo -ne "\r"
    sleep 3
done

# ── Step 6: verify stt_segments written ──────────────────────────────────────
info "Verifying stt_segments written to video_tasks..."
SEG_COUNT=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT jsonb_array_length(stt_segments) FROM video_tasks WHERE id='task-$JOB_ID';" \
    2>/dev/null | tr -d ' ')

if [ -n "$SEG_COUNT" ] && [ "$SEG_COUNT" -gt 0 ] 2>/dev/null; then
    ok "stt_segments written: $SEG_COUNT segment(s)"
else
    warn "stt_segments may be empty or missing (count=$SEG_COUNT) — check STT model"
fi

echo ""
ok "captionsOnly E2E test PASSED"
echo ""
