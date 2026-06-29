#!/usr/bin/env bash
# test_e2e_full_dubbing.sh — E2E: fullDubbing (STT→NMT→TTS→merge→COMPLETED)
#
# Prerequisites:
#   docker compose up -d postgres rabbitmq minio orchestrator \
#     stt-service nmt-service tts-service media-service
#
# Usage:
#   ./test_e2e_full_dubbing.sh [path/to/video.mp4]

set -euo pipefail
cd "$(dirname "$0")"

TEST_VIDEO_FILE="${1:-}"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-dub-${TS}"
VIDEO_ID="e2e-video-dub-${TS}"
MINIO_KEY="test-e2e/full-dubbing-${TS}.mp4"
POLL_TIMEOUT=1200

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

cleanup() {
    warn "Cleaning up test data..."
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -q \
        -c "DELETE FROM jobs WHERE id = '$JOB_ID' OR parent_job_id = '$JOB_ID';" \
        -c "DELETE FROM video_tasks WHERE video_id = '$VIDEO_ID';" \
        -c "DELETE FROM videos WHERE id = '$VIDEO_ID';" \
        2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  E2E Test: fullDubbing (STT → NMT → TTS → merge → COMPLETED)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ -z "$TEST_VIDEO_FILE" ]; then
    info "No video provided — generating 5s test video with ffmpeg"
    TEST_VIDEO_FILE="/tmp/e2e_dub_test_${TS}.mp4"
    ffmpeg -f lavfi -i "testsrc=duration=5:size=320x240:rate=24" \
        -f lavfi -i "sine=frequency=440:duration=5" \
        -c:v libx264 -c:a aac -shortest "$TEST_VIDEO_FILE" -y -loglevel quiet
fi
[ -f "$TEST_VIDEO_FILE" ] || fail "Video file not found: $TEST_VIDEO_FILE"

info "Uploading video to MinIO"
MINIO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'minio' | head -1)
[ -n "$MINIO_CONTAINER" ] || fail "MinIO container not found"

docker cp "$TEST_VIDEO_FILE" "${MINIO_CONTAINER}:/tmp/video_e2e.mp4"
docker exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc mb "local/$BUCKET" --ignore-existing -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc cp /tmp/video_e2e.mp4 "local/$BUCKET/$MINIO_KEY" -q
ok "Video uploaded"

TASK_ID="task-${JOB_ID}"
info "Seeding DB: video=$VIDEO_ID job=$JOB_ID (fullDubbing)"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, media_type, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-full-dubbing', 'COMPLETED',
        '$MINIO_KEY', '$MINIO_KEY', 'VIDEO', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang,
                         source_lang, num_beams, english_ratio_threshold,
                         created_at, updated_at)
VALUES ('$TASK_ID', '$VIDEO_ID', 'PENDING', 'fullDubbing', 'arb_Arab',
        'eng_Latn', 5, 0.5, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'FULL_DUBBING_PIPELINE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID", "output_type": "fullDubbing"}'::jsonb,
        '{}'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
SQL
ok "DB seeded"

info "Publishing job.created"
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
PYEOF
ok "job.created published"

info "Watching pipeline (timeout=${POLL_TIMEOUT}s)..."
START=$(date +%s)
LAST_STATUS=""
MERGE_STARTED=false

while true; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')

    if ! $MERGE_STARTED; then
        MERGE_ROW=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
            -c "SELECT status FROM jobs WHERE parent_job_id='$JOB_ID' AND job_type='DUBBING_MERGE' LIMIT 1;" \
            2>/dev/null | tr -d ' ')
        if [ -n "$MERGE_ROW" ]; then
            ok "Merge stage started (status=$MERGE_ROW)"
            MERGE_STARTED=true
        fi
    fi

    if [ "$STATUS" != "$LAST_STATUS" ]; then
        info "Parent status: $LAST_STATUS → $STATUS"
        LAST_STATUS="$STATUS"
    fi

    case "$STATUS" in
        COMPLETED)
            ELAPSED=$(( $(date +%s) - START ))
            ok "Parent job COMPLETED in ${ELAPSED}s"
            break
            ;;
        FAILED) fail "Parent job FAILED" ;;
        CANCELLED) fail "Parent job CANCELLED unexpectedly" ;;
    esac

    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $POLL_TIMEOUT ] && fail "Timed out. Last status: $STATUS"
    sleep 10
done

COMBINED_KEY=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT combined_audio_key FROM video_tasks WHERE id='$TASK_ID';" 2>/dev/null | tr -d ' ')
DUBBED_PATH=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT dubbed_video_path FROM video_tasks WHERE id='$TASK_ID';" 2>/dev/null | tr -d ' ')

[ -n "$COMBINED_KEY" ] && ok "combined_audio_key: $COMBINED_KEY" || warn "combined_audio_key empty"
[ -n "$DUBBED_PATH" ] && ok "dubbed_video_path: $DUBBED_PATH" || warn "dubbed_video_path empty (merge may still write to videos table)"

echo ""
ok "fullDubbing E2E test PASSED"
echo ""
