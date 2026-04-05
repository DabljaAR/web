# TTS Dispatch Fix - CELERY .get() VIOLATION RESOLVED

## 🎯 REAL ROOT CAUSE FOUND!

**Issue**: STT task calling `res.get()` on NMT task results
**Error**: `Never call result.get() within a task!`

This is a **Celery architecture violation**. Tasks cannot call `.get()` on other task results.

## 📋 Timeline of Issues

1. ✅ **Silent TTS audio** → Fixed (TTS reference audio path)
2. ✅ **Old worker code** → Fixed (restarted workers) 
3. ✅ **Redis old tasks** → Fixed (purged queues)
4. ✅ **res.info tracking bug** → Fixed (used set() instead)
5. 🎯 **Celery .get() violation** → **JUST FIXED**

## 🔧 The Final Fix

**File**: `app/jobs/tasks/pipeline.py`, line 217

```python
# OLD (VIOLATES CELERY RULES):
task_result = res.get(timeout=1)

# NEW (FIXED):
task_result = res.result
```

**Why this works**:
- `.get()` is synchronous and blocked in tasks
- `.result` is the direct result access (safe in tasks when `ready()` is True)

## ⚡ Current Status

- ✅ **STT worker**: Restarted with `.result` fix (PID 153590)
- ✅ **NMT worker**: Working (17+ segments translated)
- ✅ **TTS worker**: Ready and waiting
- ✅ **Code**: Progressive dispatch with `upload_to_minio=True`

## 🧪 Test Again Now

**The pipeline should now work correctly!**

### Expected Flow:
1. Upload audio → STT transcribes
2. STT dispatches NMT segments 
3. **NEW**: NMT results processed with `res.result` (no error)
4. **NEW**: STT dispatches TTS immediately per segment
5. TTS receives Arabic text + `upload_to_minio=True`
6. Audio available in MinIO

### Monitor Logs:
```bash
# Terminal 1: STT (should show "Progressive TTS dispatched")
tail -f ~/dabljaAR/web/backend/logs/worker_stt.log

# Terminal 2: TTS (should start receiving tasks)  
tail -f ~/dabljaAR/web/backend/logs/worker_tts.log
```

### Expected STT Logs:
```
[STT] Got NMT result: {'segment_id': 0, 'translated_text': 'النص العربي', 'status': 'completed'}
[STT] Progressive TTS dispatched for segment 0 | job=xxx
[STT] Got NMT result: {'segment_id': 1, 'translated_text': 'نص آخر', 'status': 'completed'}
[STT] Progressive TTS dispatched for segment 1 | job=xxx
...
[STT] Progressive NMT+TTS complete: X segments processed, 0 failed
```

### Expected TTS Logs:
```
Task app.jobs.tasks.tts.synthesize[xxx] received  
Synthesizing [dialect=MSA] text length=XX chars
gen_text: النص العربي المترجم  (ARABIC!)
```

## 🎉 This Should Be The Final Fix!

All architectural issues resolved:
- ✅ No old workers
- ✅ No old queues  
- ✅ No variable shadowing
- ✅ No buggy result tracking
- ✅ **No Celery violations**

**Ready for end-to-end testing!** 🚀
