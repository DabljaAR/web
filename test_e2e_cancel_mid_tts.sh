#!/usr/bin/env bash
# test_e2e_cancel_mid_tts.sh — Cancel a job while TTS is running
#
# Prerequisites:
#   docker compose up -d postgres rabbitmq minio orchestrator stt-service nmt-service tts-service
#
# This test seeds a job with many segments (simulated via pre-filled NMT output)
# and cancels the parent while TTS is processing.

set -euo pipefail
cd "$(dirname "$0")"

TS=$(date +%s)
JOB_ID="e2e-cancel-tts-${TS}"
VIDEO_ID="e2e-video-cancel-${TS}"
TASK_ID="task-${JOB_ID}"
POLL_TIMEOUT=600

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

cleanup() {
    warn "Cleaning up..."
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -q \
        -c "DELETE FROM jobs WHERE id = '$JOB_ID' OR parent_job_id = '$JOB_ID';" \
        -c "DELETE FROM video_tasks WHERE video_id = '$VIDEO_ID';" \
        -c "DELETE FROM videos WHERE id = '$VIDEO_ID';" \
        2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  E2E Test: cancel mid-TTS"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Build 20 segments to give TTS time to run
SEGMENTS_JSON='['
for i in $(seq 0 19); do
    START=$(echo "$i * 2" | bc)
    END=$(echo "($i + 1) * 2" | bc)
    [ "$i" -gt 0 ] && SEGMENTS_JSON+=','
    SEGMENTS_JSON+="{\"start\": $START, \"end\": $END, \"original_text\": \"segment $i\", \"translated_text\": \"مقطع $i\"}"
done
SEGMENTS_JSON+=']'

info "Seeding DB with 20 pre-translated segments"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-cancel-tts', 'COMPLETED', 'test/cancel.mp3', 'test/cancel.mp3', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang, segments, created_at, updated_at)
VALUES ('$TASK_ID', '$VIDEO_ID', 'PROCESSING', 'translationAndTTS', 'arb_Arab',
        '$SEGMENTS_JSON'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

    INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'FULL_DUBBING_PIPELINE'::jobtype, 'PROCESSING'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID", "output_type": "translationAndTTS"}'::jsonb,
        '{}'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
SQL

TTS_JOB_ID="tts-child-${TS}"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO jobs (id, user_id, job_type, status, video_id, parent_job_id, input_data, created_at, updated_at)
VALUES ('$TTS_JOB_ID', 1, 'TTS_SYNTHESIZE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID', '$JOB_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID"}'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
SQL
ok "DB seeded with TTS child job $TTS_JOB_ID"

info "Publishing job.start.tts"
python3 - <<PYEOF
import pika, json
params = pika.URLParameters("amqp://guest:guest@localhost:5672/")
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.exchange_declare("dablja.jobs.exchange", exchange_type="topic", durable=True)
ch.basic_publish(
    exchange="dablja.jobs.exchange",
    routing_key="job.start.tts",
    body=json.dumps({"job_id": "$TTS_JOB_ID"}),
    properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
)
conn.close()
PYEOF

sleep 5

info "Cancelling parent job $JOB_ID"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
UPDATE jobs SET status='CANCELLED', updated_at=NOW()
WHERE id='$JOB_ID' OR id='$TTS_JOB_ID';
SQL
ok "Cancel flag set"

info "Waiting for TTS job to settle (should NOT reach COMPLETED)..."
START=$(date +%s)
while true; do
    TTS_STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$TTS_JOB_ID';" 2>/dev/null | tr -d ' ')

    if [ "$TTS_STATUS" = "COMPLETED" ]; then
        fail "TTS job reached COMPLETED after cancel (expected CANCELLED or unchanged)"
    fi

    if [ "$TTS_STATUS" = "CANCELLED" ] || [ "$TTS_STATUS" = "QUEUED" ] || [ "$TTS_STATUS" = "PROCESSING" ]; then
        ELAPSED=$(( $(date +%s) - START ))
        if [ $ELAPSED -ge 30 ]; then
            ok "TTS job did not complete after cancel (status=$TTS_STATUS)"
            break
        fi
    fi

    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $POLL_TIMEOUT ] && fail "Timed out waiting for cancel behavior"
    sleep 3
done

echo ""
ok "cancel mid-TTS E2E test PASSED"
echo ""
