# Worker Cleanup Complete - March 26, 2026 @ 19:59

## ✅ Issues Resolved

### Problem 1: Old Worker Code Running
- **Symptom:** TTS receiving English text instead of Arabic
- **Cause:** Old workers from 16:03 still running with outdated code
- **Solution:** Killed old workers, restarted with fresh code

### Problem 2: Multiple Duplicate Workers
- **Symptom:** 3 TTS workers + multiple pipeline workers running simultaneously
- **Cause:** Multiple `start_dev.sh` calls without proper cleanup
- **Solution:** Proper `./stop_dev.sh` before each restart

### Problem 3: Old Tasks in Redis Queue
- **Symptom:** Fresh worker immediately picked up old English-text tasks
- **Cause:** 40+ old TTS tasks queued in Redis from previous runs
- **Solution:** Manually cleared queue with `redis-cli del ai_tts`

## 🎯 Current Status (19:59)

### Workers Running (Exactly 4)
```
moustafa  133xxx  STT worker  (ai_stt queue)    ✅
moustafa  133xxx  NMT worker  (ai_nmt queue)    ✅  
moustafa  133xxx  TTS worker  (ai_tts queue)    ✅
moustafa  133xxx  Pipeline    (media,pipeline)  ✅
```

### Queue Status
```bash
$ redis-cli llen ai_tts
(integer) 0  # ✅ Empty, no old tasks
```

### TTS Worker Log
```
[2026-03-26 19:59:24,085: INFO/MainProcess] tts@%HP-Pavilion ready.
```
✅ Clean start, no old tasks being processed

## 🧪 Ready for Testing

All prerequisites met:
- ✅ Workers running fresh code (started 19:59)
- ✅ No duplicate workers
- ✅ Redis queues cleared
- ✅ NMT translation verified working ("Hello world" → "مرحبا بالعالم")
- ✅ Code has progressive TTS dispatch with `upload_to_minio=True`

## 📋 Test Instructions

1. **Upload new audio file**
```bash
curl -X POST http://localhost:8000/api/videos/upload/audio \
  -F "file=@test.mp3" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

2. **Start transcription**
```bash
curl -X POST "http://localhost:8000/api/transcription/transcribe-async?video_id=VIDEO_ID&language=en&target_lang=arb_Arab" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

3. **Monitor in Flower:** http://localhost:5566

### Expected Results
- **NMT tasks:** `translated_text` in ARABIC ✅
- **TTS tasks:** 
  - kwargs: `"upload_to_minio": true` ✅
  - kwargs: `"text"` in ARABIC ✅
  - result: `"minio_key": "tts/VIDEO_ID/segment_X.wav"` ✅
  - result: `"audio_url": "http://localhost:9000/..."` ✅

4. **Access audio:**
```
http://localhost:9000/dablaja-videos/tts/{VIDEO_ID}/segment_0.wav
```

## 🛠️ Maintenance Commands

### Proper Restart Procedure
```bash
cd ~/dabljaAR/web/backend
./stop_dev.sh         # Always stop first!
sleep 3
./start_dev.sh        # Then start
```

### Clear Redis Queues (if needed)
```bash
redis-cli del ai_stt
redis-cli del ai_nmt  
redis-cli del ai_tts
redis-cli del media
redis-cli del pipeline
```

### Verify Clean State
```bash
# Should show exactly 4 workers
ps aux | grep "celery.*worker" | grep -v grep | wc -l

# Should all show 0
redis-cli llen ai_stt
redis-cli llen ai_nmt
redis-cli llen ai_tts
```

## 🎉 Summary

All cleanup complete. The pipeline is now:
- ✅ Running with FRESH code
- ✅ NO old tasks in queues
- ✅ NO duplicate workers
- ✅ Ready for real testing

**Previous test results are now INVALID.** Please test again with fresh upload!
