#!/bin/bash
# Quick pipeline verification script

echo "=== DabljaAR Pipeline Verification ==="
echo

# Check services
echo "1. Checking Services..."
echo -n "  - Uvicorn (FastAPI): "
curl -s http://localhost:8000/docs > /dev/null && echo "✅ Running" || echo "❌ Not responding"

echo -n "  - Flower (Monitor): "
curl -s http://localhost:5566 > /dev/null && echo "✅ Running" || echo "❌ Not responding"

echo

# Check workers
echo "2. Checking Workers..."
for worker in stt nmt tts pipeline; do
    echo -n "  - $worker worker: "
    if tail -5 logs/worker_$worker.log 2>/dev/null | grep -q "ready"; then
        echo "✅ Ready"
    else
        echo "⚠️  Check logs/worker_$worker.log"
    fi
done

echo

# Check task registration
echo "3. Checking Task Registration..."
echo -n "  - stt_transcribe: "
grep -q "app.jobs.tasks.pipeline.stt_transcribe" logs/worker_stt.log && echo "✅ Registered" || echo "❌ Missing"

echo -n "  - nmt_translate_segment: "
grep -q "app.jobs.tasks.nmt.translate_segment" logs/worker_nmt.log && echo "✅ Registered" || echo "❌ Missing"

echo -n "  - tts_synthesize: "
grep -q "app.jobs.tasks.pipeline.tts_synthesize" logs/worker_tts.log && echo "✅ Registered" || echo "❌ Missing"

echo

# Check TTS reference audio
echo "4. Checking TTS Configuration..."
if [ -f .venv/lib/python3.12/site-packages/habibi_tts/assets/MSA.mp3 ]; then
    size=$(stat -f%z .venv/lib/python3.12/site-packages/habibi_tts/assets/MSA.mp3 2>/dev/null || stat -c%s .venv/lib/python3.12/site-packages/habibi_tts/assets/MSA.mp3 2>/dev/null)
    echo "  - MSA reference audio: ✅ Found ($size bytes)"
else
    echo "  - MSA reference audio: ❌ Not found"
fi

echo

# Check no duplicate tasks
echo "5. Checking for Duplicate Tasks..."
old_task_count=$(grep -c "def transcribe_task" app/stt/models.py 2>/dev/null || echo "0")
if [ "$old_task_count" -eq "0" ]; then
    echo "  - Old STT task: ✅ Removed (no duplicates)"
else
    echo "  - Old STT task: ⚠️  Still exists in app/stt/models.py"
fi

echo
echo "=== Verification Complete ==="
echo
echo "To test the pipeline:"
echo "  1. Upload a video via /api/videos/upload/audio"
echo "  2. POST /api/transcription/transcribe-async?video_id=XXX"
echo "  3. Monitor job: GET /api/jobs/JOB_ID"
echo
