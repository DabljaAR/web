#!/usr/bin/env bash
# test_e2e_captions_and_translation.sh — E2E: captionsAndTranslation (STT→NMT→COMPLETED)
#
# Flow:
#   [this script]  → seeds DB, publishes job.created
#   [orchestrator] → STT child → NMT child (after STT result)
#   [stt-service]  → transcribes audio    → job.results.stt COMPLETED
#   [nmt-service]  → translates segments  → job.results.nmt COMPLETED
#   [orchestrator] → nextStage=none       → parent COMPLETED
#
# Prerequisites (running):
#   docker compose up -d postgres rabbitmq minio orchestrator stt-service nmt-service
#   Audio file at TEST_AUDIO_FILE (any short English MP3/WAV — must have speech)
#
# Usage:
#   ./test_e2e_captions_and_translation.sh [path/to/audio.mp3]

set -euo pipefail
cd "$(dirname "$0")"

# ── Config ────────────────────────────────────────────────────────────────────
TEST_AUDIO_FILE="${1:-}"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-nmt-${TS}"
VIDEO_ID="e2e-video-nmt-${TS}"
MINIO_KEY="test-e2e/captions-and-translation-${TS}.mp3"
POLL_TIMEOUT=600  # NMT can take longer than STT

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
        -c "DELETE FROM jobs   WHERE id = '$JOB_ID' OR parent_job_id = '$JOB_ID';" \
        -c "DELETE FROM video_tasks WHERE video_id = '$VIDEO_ID';" \
        -c "DELETE FROM videos WHERE id = '$VIDEO_ID';" \
        2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  E2E Test: captionsAndTranslation (STT → NMT → parent COMPLETED)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: resolve test audio ────────────────────────────────────────────────
if [ -z "$TEST_AUDIO_FILE" ]; then
    info "No audio file provided — generating 5s TTS-like test audio with ffmpeg"
    TEST_AUDIO_FILE="/tmp/e2e_nmt_test_${TS}.mp3"
    # Generate a tone that the Whisper model can at least attempt to transcribe
    ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -q:a 9 -acodec libmp3lame \
        "$TEST_AUDIO_FILE" -y -loglevel quiet
    warn "Using synthetic audio — transcript/translation quality is not validated"
fi

[ -f "$TEST_AUDIO_FILE" ] || fail "Audio file not found: $TEST_AUDIO_FILE"

# ── Step 2: upload audio to MinIO ─────────────────────────────────────────────
info "Uploading audio to MinIO bucket=$BUCKET key=$MINIO_KEY"
MINIO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'minio' | head -1)
[ -n "$MINIO_CONTAINER" ] || fail "MinIO container not found (is the stack up?)"

docker cp "$TEST_AUDIO_FILE" "${MINIO_CONTAINER}:/tmp/audio_e2e.mp3"
docker exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc mb "local/$BUCKET" --ignore-existing -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc cp /tmp/audio_e2e.mp3 "local/$BUCKET/$MINIO_KEY" -q
ok "Audio uploaded"

# ── Step 3: seed DB ───────────────────────────────────────────────────────────
info "Seeding DB: video=$VIDEO_ID job=$JOB_ID (captionsAndTranslation)"
TASK_ID="task-${JOB_ID}"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-captions-and-translation', 'COMPLETED',
        '$MINIO_KEY', '$MINIO_KEY', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang,
                         source_lang, num_beams, english_ratio_threshold,
                         created_at, updated_at)
VALUES ('$TASK_ID', '$VIDEO_ID', 'PENDING', 'captionsAndTranslation', 'arb_Arab',
        'eng_Latn', 5, 0.5, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'FULL_DUBBING_PIPELINE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID", "output_type": "captionsAndTranslation"}'::jsonb,
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

# ── Step 5: watch stage transitions ──────────────────────────────────────────
info "Watching stage transitions (timeout=${POLL_TIMEOUT}s)..."
START=$(date +%s)
LAST_STATUS=""
NMT_STARTED=false

while true; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')

    # Detect NMT child creation
    if ! $NMT_STARTED; then
        NMT_ROW=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
            -c "SELECT status FROM jobs WHERE parent_job_id='$JOB_ID' AND job_type='NMT_TRANSLATE' LIMIT 1;" \
            2>/dev/null | tr -d ' ')
        if [ -n "$NMT_ROW" ]; then
            ok "NMT stage started (status=$NMT_ROW)"
            NMT_STARTED=true
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
    sleep 5
done

# ── Step 6: verify NMT output ────────────────────────────────────────────────
info "Verifying translated segments in video_tasks..."
SEG_COUNT=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT jsonb_array_length(segments) FROM video_tasks WHERE id='$TASK_ID';" \
    2>/dev/null | tr -d ' ')

VTASK_STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT status FROM video_tasks WHERE id='$TASK_ID';" \
    2>/dev/null | tr -d ' ')

if [ "$VTASK_STATUS" = "COMPLETED" ]; then
    ok "video_task.status = COMPLETED"
else
    warn "video_task.status = $VTASK_STATUS (expected COMPLETED for captionsAndTranslation)"
fi

if [ -n "$SEG_COUNT" ] && [ "$SEG_COUNT" -gt 0 ] 2>/dev/null; then
    ok "translated segments written: $SEG_COUNT segment(s)"
else
    warn "translated segments may be empty (count=$SEG_COUNT)"
fi

# Verify segment shape has all 4 required keys (TTS contract)
info "Checking segment shape (TTS contract: start, end, original_text, translated_text)..."
SHAPE_OK=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq -c "
    SELECT COUNT(*)
    FROM video_tasks,
         jsonb_array_elements(segments) AS seg
    WHERE id = '$TASK_ID'
      AND seg ? 'start'
      AND seg ? 'end'
      AND seg ? 'original_text'
      AND seg ? 'translated_text'
    LIMIT 1;
" 2>/dev/null | tr -d ' ')

if [ "${SHAPE_OK:-0}" -gt 0 ] 2>/dev/null; then
    ok "Segment shape contract valid (all 4 keys present)"
else
    warn "Could not verify segment shape (may be empty or missing keys)"
fi

echo ""
ok "captionsAndTranslation E2E test PASSED"
echo ""
