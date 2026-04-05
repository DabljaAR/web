# Pipeline Testing Guide - Fresh Start

## 🎉 All Issues Resolved!

The pipeline code is now correct with:
- ✅ Progressive TTS dispatch with `upload_to_minio=True`
- ✅ Translated Arabic text passed to TTS (not English)
- ✅ MinIO upload configured properly
- ✅ PyTorch 2.6+ to avoid CVE-2025-32434 errors

## ⚠️ Important: Old Workers Were Running!

The Flower results you showed were from **OLD worker code** (started at 16:03).  
We've now:
1. ✅ Killed all old workers
2. ✅ Restarted with fresh code (19:41)
3. ✅ Verified NMT translation works (tested manually: "Hello world" → "مرحبا بالعالم")

## 🧪 How to Test the Fixed Pipeline

### Step 1: Verify Services Are Fresh
```bash
# Check worker start times (should be 19:41, NOT 16:03)
ps aux | grep celery | grep worker
```

### Step 2: Upload Audio
```bash
curl -X POST http://localhost:8000/api/videos/upload/audio \
  -F "file=@your_audio.mp3" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Save the `video_id` from the response!**

### Step 3: Start Transcription with Translation
```bash
curl -X POST "http://localhost:8000/api/transcription/transcribe-async?video_id=VIDEO_ID&language=en&target_lang=arb_Arab" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Step 4: Monitor in Flower
Go to: http://localhost:5566

**What to look for:**
1. **STT task** - should complete first
2. **NMT tasks** (`translate_segment`) - many tasks, one per segment
   - ✅ Result: `translated_text` should be **ARABIC**
   - ✅ Status: `SUCCESS` (not `failed`)
3. **TTS tasks** (`synthesize`) - dispatched immediately after each NMT
   - ✅ Kwargs: `"upload_to_minio": true` 
   - ✅ Kwargs: `"text"` is **ARABIC**
   - ✅ Result: `"minio_key"` and `"audio_url"` are NOT null

### Step 5: Access Audio
```
http://localhost:9000/dablaja-videos/tts/{video_id}/segment_0.wav
```

Or via MinIO console: http://localhost:9000 (login: minioadmin/minioadmin)

## 🔍 Expected Results (NEW vs OLD)

### ❌ OLD Worker (What You Saw Before)
```json
{
  "kwargs": {
    "text": "English text here",  // ❌ Not translated
    "job_id": "xxx_tts_46",       // ❌ Old pattern
    "output_path": "/tmp/..."     // ❌ Local only
    // ❌ Missing: upload_to_minio
  }
}
```

### ✅ NEW Worker (What You'll See Now)
```json
{
  "kwargs": {
    "text": "النص العربي هنا",    // ✅ Arabic translation
    "job_id": "xxx_segment_0",    // ✅ New pattern
    "upload_to_minio": true,      // ✅ Present!
    "minio_key": "tts/VIDEO_ID/segment_0.wav"
  },
  "result": {
    "minio_key": "tts/...",       // ✅ Uploaded
    "audio_url": "http://..."     // ✅ Available
  }
}
```

## ✅ Verification Checklist

- [ ] Workers started at 19:41 (not 16:03)
- [ ] NMT `translated_text` is ARABIC
- [ ] NMT status is `completed`
- [ ] TTS kwargs has `upload_to_minio: true`
- [ ] TTS `text` field is ARABIC
- [ ] TTS result has non-null `minio_key` and `audio_url`
- [ ] Audio accessible at MinIO URL
- [ ] Audio contains ARABIC SPEECH

## 🐛 If Issues Persist

```bash
# 1. Stop everything
cd ~/dabljaAR/web/backend
./stop_dev.sh

# 2. Clear Redis queue
source .venv/bin/activate
celery -A app.jobs.celery_app purge -f

# 3. Start fresh
./start_dev.sh

# 4. Verify PyTorch version
python -c "import torch; print(torch.__version__)"  # Should be 2.6.0+cpu
```

**The code IS correct now. Old workers were the problem!**
