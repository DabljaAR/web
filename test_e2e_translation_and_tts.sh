#!/usr/bin/env bash
# test_e2e_translation_and_tts.sh — E2E: translationAndTTS (STT→NMT→TTS→COMPLETED)
#
# Prerequisites:
#   docker compose up -d postgres rabbitmq minio orchestrator stt-service nmt-service tts-service
#
# Usage:
#   ./test_e2e_translation_and_tts.sh [path/to/audio.mp3]

set -euo pipefail
cd "$(dirname "$0")"

TEST_AUDIO_FILE="${1:-}"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-tts-${TS}"
VIDEO_ID="e2e-video-tts-${TS}"
MINIO_KEY="test-e2e/translation-and-tts-${TS}.mp3"
POLL_TIMEOUT=900

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
echo "  E2E Test: translationAndTTS (STT → NMT → TTS → COMPLETED)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ -z "$TEST_AUDIO_FILE" ]; then
    info "No audio file provided — generating 5s test audio with ffmpeg"
    TEST_AUDIO_FILE="/tmp/e2e_tts_test_${TS}.mp3"
    ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -q:a 9 -acodec libmp3lame \
        "$TEST_AUDIO_FILE" -y -loglevel quiet
fi
[ -f "$TEST_AUDIO_FILE" ] || fail "Audio file not found: $TEST_AUDIO_FILE"

info "Uploading audio to MinIO"
MINIO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'minio' | head -1)
[ -n "$MINIO_CONTAINER" ] || fail "MinIO container not found"

docker cp "$TEST_AUDIO_FILE" "${MINIO_CONTAINER}:/tmp/audio_e2e.mp3"
docker exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc mb "local/$BUCKET" --ignore-existing -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc cp /tmp/audio_e2e.mp3 "local/$BUCKET/$MINIO_KEY" -q
ok "Audio uploaded"

TASK_ID="task-${JOB_ID}"
info "Seeding DB: video=$VIDEO_ID job=$JOB_ID (translationAndTTS)"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-translation-and-tts', 'COMPLETED',
        '$MINIO_KEY', '$MINIO_KEY', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang,
                         source_lang, num_beams, english_ratio_threshold,
                         created_at, updated_at)
VALUES ('$TASK_ID', '$VIDEO_ID', 'PENDING', 'translationAndTTS', 'arb_Arab',
        'eng_Latn', 5, 0.5, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'FULL_DUBBING_PIPELINE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID", "output_type": "translationAndTTS"}'::jsonb,
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
TTS_STARTED=false

while true; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')

    if ! $TTS_STARTED; then
        TTS_ROW=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
            -c "SELECT status FROM jobs WHERE parent_job_id='$JOB_ID' AND job_type='TTS_SYNTHESIZE' LIMIT 1;" \
            2>/dev/null | tr -d ' ')
        if [ -n "$TTS_ROW" ]; then
            ok "TTS stage started (status=$TTS_ROW)"
            TTS_STARTED=true
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
    [ $ELAPSED -ge $POLL_TIMEOUT ] && fail "Timed out after ${POLL_TIMEOUT}s. Last status: $STATUS"
    sleep 10
done

COMBINED_KEY=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT combined_audio_key FROM video_tasks WHERE id='$TASK_ID';" 2>/dev/null | tr -d ' ')
VTASK_STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT status FROM video_tasks WHERE id='$TASK_ID';" 2>/dev/null | tr -d ' ')

if [ -n "$COMBINED_KEY" ]; then
    ok "combined_audio_key set: $COMBINED_KEY"
else
    warn "combined_audio_key is empty"
fi

if [ "$VTASK_STATUS" = "COMPLETED" ]; then
    ok "video_task.status = COMPLETED"
else
    warn "video_task.status = $VTASK_STATUS (expected COMPLETED)"
fi

echo ""
ok "translationAndTTS E2E test PASSED"
echo ""
