#!/usr/bin/env bash
# test_e2e_merge_only.sh — Smoke: merge stage only (pre-seeded combined_audio_key + video)
#
# Prerequisites:
#   docker compose up -d postgres rabbitmq minio media-service
#
# Usage:
#   ./test_e2e_merge_only.sh [path/to/video.mp4]

set -euo pipefail
cd "$(dirname "$0")"

TEST_VIDEO_FILE="${1:-}"
BUCKET="dablaja-videos"
TS=$(date +%s)
JOB_ID="e2e-merge-${TS}"
VIDEO_ID="e2e-video-merge-${TS}"
TASK_ID="task-${JOB_ID}"
MINIO_KEY="test-e2e/merge-only-${TS}.mp4"
COMBINED_KEY="tts/${VIDEO_ID}/combined_seed_${TS}.wav"
POLL_TIMEOUT=300

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

cleanup() {
    warn "Cleaning up test data..."
    docker exec dabljaar_postgres psql -U postgres -d dabljaar -q \
        -c "DELETE FROM jobs WHERE id = '$JOB_ID';" \
        -c "DELETE FROM video_tasks WHERE id = '$TASK_ID';" \
        -c "DELETE FROM videos WHERE id = '$VIDEO_ID';" \
        2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  E2E Smoke: merge-only (pre-seeded combined_audio_key)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ -z "$TEST_VIDEO_FILE" ]; then
    info "No video provided — generating 3s test video with ffmpeg"
    TEST_VIDEO_FILE="/tmp/e2e_merge_test_${TS}.mp4"
    ffmpeg -f lavfi -i "testsrc=duration=3:size=320x240:rate=24" \
        -f lavfi -i "sine=frequency=440:duration=3" \
        -c:v libx264 -c:a aac -shortest "$TEST_VIDEO_FILE" -y -loglevel quiet
fi
[ -f "$TEST_VIDEO_FILE" ] || fail "Video file not found: $TEST_VIDEO_FILE"

info "Uploading video + dummy combined WAV to MinIO"
MINIO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'minio' | head -1)
[ -n "$MINIO_CONTAINER" ] || fail "MinIO container not found"

docker cp "$TEST_VIDEO_FILE" "${MINIO_CONTAINER}:/tmp/video_merge.mp4"
# Minimal valid WAV header (44 bytes silence placeholder — ffmpeg mux reads duration from video)
python3 - <<PYWAV
import struct, sys
rate, channels, bits = 16000, 1, 16
data_size = rate * 2  # ~0.5s silence
with open("/tmp/combined_seed.wav", "wb") as f:
    f.write(b"RIFF")
    f.write(struct.pack("<I", 36 + data_size))
    f.write(b"WAVEfmt ")
    f.write(struct.pack("<IHHIIHH", 16, 1, channels, rate, rate*channels*bits//8, channels*bits//8, bits))
    f.write(b"data")
    f.write(struct.pack("<I", data_size))
    f.write(b"\x00" * data_size)
PYWAV
docker cp /tmp/combined_seed.wav "${MINIO_CONTAINER}:/tmp/combined_seed.wav"

docker exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc mb "local/$BUCKET" --ignore-existing -q 2>/dev/null || true
docker exec "$MINIO_CONTAINER" mc cp /tmp/video_merge.mp4 "local/$BUCKET/$MINIO_KEY" -q
docker exec "$MINIO_CONTAINER" mc cp /tmp/combined_seed.wav "local/$BUCKET/$COMBINED_KEY" -q
ok "Assets uploaded"

info "Seeding DB: video=$VIDEO_ID merge job=$JOB_ID"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q <<SQL
INSERT INTO videos (id, user_id, title, status, file_path, audio_path, media_type, created_at, updated_at)
VALUES ('$VIDEO_ID', 1, 'e2e-merge-only', 'COMPLETED',
        '$MINIO_KEY', '$MINIO_KEY', 'VIDEO', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO video_tasks (id, video_id, status, output_type, target_lang,
                         source_lang, combined_audio_key, progress,
                         created_at, updated_at)
VALUES ('$TASK_ID', '$VIDEO_ID', 'PROCESSING', 'fullDubbing', 'arb_Arab',
        'eng_Latn', '$COMBINED_KEY', 75.0, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (id, user_id, job_type, status, video_id, input_data, output_data, created_at, updated_at)
VALUES ('$JOB_ID', 1, 'DUBBING_MERGE'::jobtype, 'QUEUED'::jobstatus, '$VIDEO_ID',
        '{"video_id": "$VIDEO_ID", "task_id": "$TASK_ID", "output_type": "fullDubbing"}'::jsonb,
        '{}'::jsonb, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
SQL
ok "DB seeded"

info "Publishing job.start.merge"
python3 - <<PYEOF
import pika, json
params = pika.URLParameters("amqp://guest:guest@localhost:5672/")
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.exchange_declare("dablja.jobs.exchange", exchange_type="topic", durable=True)
ch.basic_publish(
    exchange="dablja.jobs.exchange",
    routing_key="job.start.merge",
    body=json.dumps({"job_id": "$JOB_ID"}),
    properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
)
conn.close()
PYEOF
ok "job.start.merge published"

info "Polling merge job (timeout=${POLL_TIMEOUT}s)..."
START=$(date +%s)
while true; do
    STATUS=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
        -c "SELECT status FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')
    case "$STATUS" in
        COMPLETED) ok "Merge job COMPLETED"; break ;;
        FAILED)
            ERR=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
                -c "SELECT error_message FROM jobs WHERE id='$JOB_ID';" 2>/dev/null | tr -d ' ')
            fail "Merge job FAILED: $ERR"
            ;;
    esac
    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $POLL_TIMEOUT ] && fail "Timed out. Last status: $STATUS"
    sleep 5
done

DUBBED_PATH=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq \
    -c "SELECT dubbed_video_path FROM videos WHERE id='$VIDEO_ID';" 2>/dev/null | tr -d ' ')
[ -n "$DUBBED_PATH" ] && ok "videos.dubbed_video_path: $DUBBED_PATH" || fail "videos.dubbed_video_path empty"

echo ""
ok "merge-only smoke test PASSED"
echo ""
