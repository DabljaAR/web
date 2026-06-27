#!/usr/bin/env bash
# test_services.sh — Comprehensive test of STT, NMT, Media, and TTS services
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $*"; PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); }
info() { echo -e "${CYAN}[→]${NC} $*"; }
section() { echo ""; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo -e "${YELLOW}$*${NC}"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

POSTGRES="docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAq"
MINIO_MC="docker exec dabljaar_minio mc"

# ─────────────────────────────────────────────────────────────────────────────
section "1. INFRASTRUCTURE HEALTH CHECKS"
# ─────────────────────────────────────────────────────────────────────────────

for svc in dabljaar_postgres dabljaar_rabbitmq dabljaar_minio dabljaar_redis; do
    status=$(docker inspect --format '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [[ "$status" == "healthy" ]]; then
        pass "$svc is healthy"
    else
        fail "$svc status=$status"
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
section "2. STT SERVICE (Speech-to-Text)"
# ─────────────────────────────────────────────────────────────────────────────

info "2.1 Health & Readiness"
HEALTH=$(curl -sf http://localhost:8001/health 2>/dev/null || echo '{"status":"error"}')
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='healthy'" 2>/dev/null; then
    pass "STT /health returns healthy"
else
    fail "STT /health failed"
fi

READY=$(curl -sf http://localhost:8001/readiness 2>/dev/null || echo '{"status":"error"}')
if echo "$READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ready'" 2>/dev/null; then
    pass "STT /readiness returns ready (consumer alive)"
else
    fail "STT /readiness failed"
fi

info "2.2 Model Status"
MODEL=$(curl -sf http://localhost:8001/health/model 2>/dev/null || echo '{}')
echo "$MODEL" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d.get('model_size')=='small', 'model_size mismatch'
assert d.get('device') in ('cpu','cuda'), 'device unknown'
print(f'  Model: size={d[\"model_size\"]}, device={d[\"device\"]}, compute={d[\"compute_type\"]}, loaded={d[\"model_loaded\"]}')
" 2>/dev/null && pass "STT /health/model reports valid config" || fail "STT /health/model failed"

info "2.3 Transcription (sine wave test audio)"
if [[ ! -f /tmp/test_audio.wav ]]; then
    ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -acodec pcm_s16le -ar 16000 -ac 1 /tmp/test_audio.wav -y 2>/dev/null
fi
RESULT=$(curl -sf -X POST http://localhost:8001/transcribe -F "file=@/tmp/test_audio.wav" 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert 'transcript' in d, 'missing transcript'
assert 'segments' in d, 'missing segments'
assert 'metadata' in d, 'missing metadata'
assert d['metadata']['duration'] > 0, 'invalid duration'
print(f'  Transcript: \"{d[\"transcript\"]}\", segments={d[\"metadata\"][\"segment_count\"]}, time={d[\"metadata\"][\"processing_time\"]}s')
" 2>/dev/null && pass "STT /transcribe processed audio successfully" || fail "STT /transcribe failed"

info "2.4 Transcription validation (empty file → 400)"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null -X POST http://localhost:8001/transcribe -F "file=@/dev/null" 2>/dev/null)
[[ "$HTTP" == "400" ]] && pass "STT empty file returns 400" || fail "STT empty file returned $HTTP"

info "2.5 Transcription validation (bad format → 400)"
echo "not-an-audio" > /tmp/bad_file.txt
HTTP=$(curl -s -w "%{http_code}" -o /dev/null -X POST http://localhost:8001/transcribe -F "file=@/tmp/bad_file.txt" 2>/dev/null)
[[ "$HTTP" == "400" ]] && pass "STT bad format (.txt) returns 400" || fail "STT bad format returned $HTTP"
rm -f /tmp/bad_file.txt

# ─────────────────────────────────────────────────────────────────────────────
section "3. NMT SERVICE (Neural Machine Translation)"
# ─────────────────────────────────────────────────────────────────────────────

info "3.1 Health & Readiness"
HEALTH=$(curl -sf http://localhost:8002/health 2>/dev/null || echo '{"status":"error"}')
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='healthy'" 2>/dev/null && pass "NMT /health returns healthy" || fail "NMT /health failed"

READY=$(curl -sf http://localhost:8002/readiness 2>/dev/null || echo '{"status":"error"}')
echo "$READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ready'" 2>/dev/null && pass "NMT /readiness returns ready" || fail "NMT /readiness failed"

info "3.2 Model Status"
MODEL=$(curl -sf http://localhost:8002/health/model 2>/dev/null || echo '{}')
echo "$MODEL" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'device' in d, 'missing device'" 2>/dev/null && pass "NMT /health/model reports valid config" || fail "NMT /health/model failed"

info "3.3 Translation (EN → AR)"
RESULT=$(curl -sf -X POST http://localhost:8002/translate -H "Content-Type: application/json" -d '{"text":"Hello world", "target_lang":"arb_Arab"}' 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert 'translated_text' in d, 'missing translated_text'
assert len(d['translated_text']) > 0, 'empty translation'
print(f'  \"Hello world\" → \"{d[\"translated_text\"]}\"')
" 2>/dev/null && pass "NMT /translate EN→AR succeeded" || fail "NMT /translate EN→AR failed"

info "3.4 Translation validation (empty text → 400)"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null -X POST http://localhost:8002/translate -H "Content-Type: application/json" -d '{"text":"", "target_lang":"arb_Arab"}' 2>/dev/null)
[[ "$HTTP" == "400" ]] && pass "NMT empty text returns 400" || fail "NMT empty text returned $HTTP"

info "3.5 Translation (Arabic text AR→EN)"
RESULT=$(curl -sf -X POST http://localhost:8002/translate -H "Content-Type: application/json" -d '{"text":"مرحباً بالعالم", "source_lang":"arb_Arab", "target_lang":"eng_Latn"}' 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert 'translated_text' in d, 'missing translated_text'
assert len(d['translated_text']) > 0, 'empty translation'
print(f'  \"مرحباً بالعالم\" → \"{d[\"translated_text\"]}\"')
" 2>/dev/null && pass "NMT /translate AR→EN succeeded" || fail "NMT /translate AR→EN failed"

# ─────────────────────────────────────────────────────────────────────────────
section "4. MEDIA SERVICE (Preprocessing, FFmpeg, Storage)"
# ─────────────────────────────────────────────────────────────────────────────

info "4.1 Health"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8003/health 2>/dev/null)
[[ "$HTTP" == "200" ]] && pass "Media /health returns 200" || fail "Media /health returned $HTTP"

info "4.2 FFmpeg Metadata (existing file)"
RESULT=$(curl -sf "http://localhost:8003/ffmpeg/metadata?path=media-test/video.mp4" 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d.get('duration', 0) > 0, 'invalid duration'
assert d.get('width', 0) > 0, 'invalid width'
assert d.get('height', 0) > 0, 'invalid height'
print(f'  Duration={d[\"duration\"]:.1f}s, {d[\"width\"]}x{d[\"height\"]}, codec={d[\"codec\"]}, audio={d[\"audio_present\"]}')
" 2>/dev/null && pass "Media /ffmpeg/metadata returned valid metadata" || fail "Media /ffmpeg/metadata failed"

info "4.3 FFmpeg Metadata (missing file → 404)"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null "http://localhost:8003/ffmpeg/metadata?path=nonexistent.mp4" 2>/dev/null)
[[ "$HTTP" == "404" ]] && pass "Media metadata missing file returns 404" || fail "Media metadata missing file returned $HTTP"

info "4.4 FFmpeg Extract Audio"
KEY="media-test/audio-$(date +%s).mp3"
RESULT=$(curl -sf -X POST http://localhost:8003/ffmpeg/extract-audio -H "Content-Type: application/json" -d "{\"input_key\":\"media-test/video.mp4\",\"output_key\":\"$KEY\"}" 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status']=='ok'
assert len(d['key'])>0
" 2>/dev/null && pass "Media /ffmpeg/extract-audio succeeded" || fail "Media /ffmpeg/extract-audio failed"

info "4.5 FFmpeg Thumbnail"
KEY="media-test/thumb-$(date +%s).jpg"
RESULT=$(curl -sf -X POST http://localhost:8003/ffmpeg/thumbnail -H "Content-Type: application/json" -d "{\"input_key\":\"media-test/video.mp4\",\"output_key\":\"$KEY\"}" 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status']=='ok'
assert len(d['key'])>0
" 2>/dev/null && pass "Media /ffmpeg/thumbnail succeeded" || fail "Media /ffmpeg/thumbnail failed"

info "4.6 Storage Presign URL"
RESULT=$(curl -sf -X POST http://localhost:8003/storage/presign -H "Content-Type: application/json" -d '{"key":"media-test/video.mp4", "expires_secs":60}' 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d.get('url','').startswith('http'), 'invalid URL'
print(f'  Presigned URL generated (length={len(d[\"url\"])})')
" 2>/dev/null && pass "Media /storage/presign succeeded" || fail "Media /storage/presign failed"

info "4.7 Video CRUD (GET non-existent → 404)"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8003/videos/nonexistent 2>/dev/null)
[[ "$HTTP" == "404" ]] && pass "Media /videos/{id} missing returns 404" || fail "Media /videos/{id} missing returned $HTTP"

info "4.8 Video CRUD (GET existing)"
RESULT=$(curl -sf http://localhost:8003/videos/media-test-001 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d.get('id')=='media-test-001', 'wrong video id'
assert d.get('status') in ('COMPLETED','PENDING','PROCESSING'), f'invalid status: {d.get(\"status\")}'
print(f'  Video: id={d[\"id\"]}, status={d[\"status\"]}, audio={d.get(\"audio_path\",\"none\")}')
" 2>/dev/null && pass "Media /videos/{id} returned video" || fail "Media /videos/{id} failed"

info "4.9 Full Preprocess Pipeline"
docker exec dabljaar_postgres psql -U postgres -d dabljaar -q -c "UPDATE videos SET status='PENDING' WHERE id='media-test-001';" 2>/dev/null
RESULT=$(curl -sf -X POST http://localhost:8003/preprocess -H "Content-Type: application/json" -d '{"video_id":"media-test-001","file_key":"media-test/video.mp4","user_id":4}' 2>/dev/null || echo '{}')
echo "$RESULT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status']=='COMPLETED', f'status={d[\"status\"]}'
assert d.get('audio_key'), 'missing audio_key'
assert d.get('thumbnail_key'), 'missing thumbnail_key'
assert d['metadata'].get('duration',0) > 0, 'missing metadata'
print(f'  Audio: {d[\"audio_key\"]}, Thumb: {d[\"thumbnail_key\"]}, Duration: {d[\"metadata\"][\"duration\"]:.1f}s')
" 2>/dev/null && pass "Media /preprocess full pipeline succeeded" || fail "Media /preprocess full pipeline failed"

info "4.10 FFmpeg Extract Audio (missing input → 404)"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null -X POST http://localhost:8003/ffmpeg/extract-audio -H "Content-Type: application/json" -d '{"input_key":"nonexistent","output_key":"out.mp3"}' 2>/dev/null)
[[ "$HTTP" == "404" ]] && pass "Media extract-audio missing file returns 404" || fail "Media extract-audio missing file returned $HTTP"

# ─────────────────────────────────────────────────────────────────────────────
section "5. TTS SERVICE (RabbitMQ Consumer Check)"
# ─────────────────────────────────────────────────────────────────────────────

info "5.1 Worker-tts Container"
CONTAINER=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -i tts || echo "")
if [[ -n "$CONTAINER" ]]; then
    pass "TTS worker container running: $CONTAINER"
else
    warn="TTS worker-tts container not running (requires heavy AI models build)"
    echo -e "  ${YELLOW}[SKIP]${NC} $warn"
fi

info "5.2 Orchestrator Pipeline Readiness"
ORCH=$(docker inspect --format '{{.State.Status}}' dabljaar_orchestrator 2>/dev/null || echo "missing")
if [[ "$ORCH" == "running" ]]; then
    pass "Orchestrator is running (pipeline coordination ready)"
else
    fail "Orchestrator is not running"
fi

info "5.3 RabbitMQ Exchanges & Queues"
EXCHANGES=$(docker exec dabljaar_rabbitmq rabbitmqctl list_exchanges name type -s 2>/dev/null | grep dablja || echo "")
if echo "$EXCHANGES" | grep -q "dablja.jobs.exchange"; then
    pass "RabbitMQ dablja.jobs.exchange exists"
else
    fail "RabbitMQ exchange missing"
fi

QUEUES=$(docker exec dabljaar_rabbitmq rabbitmqctl list_queues name -s 2>/dev/null | grep stage || echo "")
STAGES=$(echo "$QUEUES" | grep -c "stage\." || true)
if [[ $STAGES -ge 2 ]]; then
    pass "RabbitMQ pipeline queues present ($STAGES stage queues)"
else
    echo -e "  ${YELLOW}[WARN]${NC} Only $STAGES stage queues found (expected ≥2: stt, nmt, tts, merge)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "6. ORCHESTRATOR INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

info "6.1 Orchestrator Health"
ORCH_LOG=$(docker logs dabljaar_orchestrator --tail 5 2>/dev/null || echo "")
if echo "$ORCH_LOG" | grep -q "Consumer ready"; then
    pass "Orchestrator consumers ready"
else
    fail "Orchestrator consumers not ready"
fi

info "6.2 Database Connection"
DB_OK=$($POSTGRES -c "SELECT 1;" 2>/dev/null || echo "")
if [[ "$DB_OK" == "1" ]]; then
    pass "PostgreSQL connection OK"
else
    fail "PostgreSQL connection failed"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "7. BACKEND API"
# ─────────────────────────────────────────────────────────────────────────────

info "7.1 Backend Root"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8000/api 2>/dev/null)
[[ "$HTTP" == "200" ]] && pass "Backend /api returns 200" || fail "Backend /api returned $HTTP"

info "7.2 Backend Docs"
HTTP=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8000/api/docs 2>/dev/null)
[[ "$HTTP" == "200" ]] && pass "Backend /api/docs returns 200" || fail "Backend /api/docs returned $HTTP"

# ─────────────────────────────────────────────────────────────────────────────
section "SUMMARY"
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "╔════════════════════════════════════════════════╗"
if [[ $FAIL -eq 0 ]]; then
    echo -e "║  ${GREEN}ALL TESTS PASSED${NC} — $PASS/$TOTAL tests successful        ║"
else
    echo -e "║  ${RED}$FAIL TEST(S) FAILED${NC} — $PASS passed, $FAIL failed / $TOTAL total  ║"
fi
echo "╚════════════════════════════════════════════════╝"
echo ""

exit $FAIL
