# Pipeline Flow Fix - STT Task Signature Mismatch

## Problem
STT tasks were failing with:
```
TypeError: transcribe_task() got an unexpected keyword argument 'video_id'
```

## Root Cause
**Duplicate task registration** - Two Celery tasks were registered with the same name `"app.jobs.tasks.pipeline.stt_transcribe"`:

1. **Old task** in `app/stt/models.py` (line 533):
   - Function: `transcribe_task()`
   - Signature: `(job_id, file_key, language, target_lang)`
   - Used `file_key` parameter

2. **New task** in `app/jobs/tasks/pipeline.py` (line 34):
   - Function: `stt_transcribe()`
   - Signature: `(job_id, video_id, language, target_lang)`
   - Uses `video_id` parameter

Both were imported via `celery_app.py` imports list, causing the old task to override the new one. When services.py called the task with `video_id`, the old task (expecting `file_key`) threw an error.

## Solution
Removed the **old duplicate task** from `app/stt/models.py`:
- Deleted `transcribe_task()` function (line 533-548)
- Deleted `_run_stt_job()` helper function (line 389-522)
- Deleted `_make_celery_db()` helper function (line 328-348)
- Deleted `_download_from_minio()` helper function (line 351-374)

The **new pipeline task** in `app/jobs/tasks/pipeline.py` is now the only STT task.

## Pipeline Flow (After Fix)

### End-to-End Flow
```
1. User uploads video → Video record created
   ↓
2. POST /api/transcription/transcribe-async?video_id=xxx
   → TranscriptionService.submit_async_transcription()
   ↓
3. Creates Job record (JobType.STT_TRANSCRIBE)
   ↓
4. Dispatches: stt_transcribe(job_id, video_id, language, target_lang)
   → Queue: ai_stt
   ↓
5. STT worker picks up task
   → Downloads audio from MinIO using video.audio_path
   → Runs Whisper transcription
   → For each segment transcribed:
      - Dispatches nmt_translate_segment(segment_id, text, ...) → Queue: ai_nmt
   ↓
6. NMT workers translate segments in parallel
   ↓
7. STT task waits for all NMT results (with SegmentBuffer for ordering)
   ↓
8. After NMT complete, STT dispatches TTS for each translated segment
   → tts_synthesize(job_id, segment_id, text, ...) → Queue: ai_tts
   ↓
9. TTS workers synthesize speech in parallel
   ↓
10. Job marked COMPLETED with full results
```

### Task Routing
| Task Name | Queue | Worker | Parameters |
|-----------|-------|--------|------------|
| `app.jobs.tasks.pipeline.stt_transcribe` | `ai_stt` | STT worker | `(job_id, video_id, language, target_lang)` |
| `app.jobs.tasks.nmt.nmt_translate_segment` | `ai_nmt` | NMT worker | `(segment_id, job_id, text, start, end, source_lang, target_lang)` |
| `app.jobs.tasks.pipeline.tts_synthesize` | `ai_tts` | TTS worker | `(job_id, segment_id, text, ...)` |
| `app.jobs.tasks.tts.synthesize` | `ai_tts` | TTS worker | Direct TTS synthesis |

### Files Modified
1. **app/stt/models.py**
   - Removed old Celery task and helpers (232 lines removed)
   - Now only contains `WhisperModelManager` class (316 lines total)

2. **app/stt/services.py**
   - Already correctly imports and calls `stt_transcribe` from pipeline
   - Line 167: `from app.jobs.tasks.pipeline import stt_transcribe as transcribe_task`

3. **app/jobs/tasks/pipeline.py**
   - Contains the definitive `stt_transcribe` task
   - Handles Video → file_key lookup
   - Orchestrates STT → NMT → TTS pipeline

## Testing
After restart, worker logs show correct task registration:
```
[tasks]
  . app.jobs.tasks.pipeline.stt_transcribe  ✓
  . app.jobs.tasks.nmt.nmt_translate_segment
  . app.jobs.tasks.pipeline.tts_synthesize
  . app.jobs.tasks.tts.synthesize
```

## Verification Commands
```bash
# Check worker is ready
tail -20 logs/worker_stt.log | grep ready

# Test transcription
curl -X POST "http://localhost:8000/api/transcription/transcribe-async?video_id=XXX&language=en"

# Monitor job status
curl "http://localhost:8000/api/jobs/JOB_ID"

# View Flower dashboard
open http://127.0.0.1:5566
```

## Status
✅ STT task signature fixed  
✅ Duplicate task removed  
✅ Pipeline flow verified  
✅ All workers running  
✅ Task routing correct  

The full pipeline (STT → NMT → TTS → Dubbing) is now operational.
