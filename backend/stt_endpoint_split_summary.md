# STT Endpoint Split - Summary

## Changes Made

### 1. Created New STT-Only Task
**File:** `app/jobs/tasks/pipeline.py`

Created a new Celery task `stt_transcribe_only` that:
- **Only performs transcription** (Whisper inference)
- **Does NOT dispatch NMT** (translation) tasks
- **Does NOT dispatch TTS** (synthesis) tasks
- **Does NOT use SegmentBuffer** (progressive pipeline logic)

**Task name:** `app.jobs.tasks.pipeline.stt_transcribe_only`
**Queue:** `ai_stt`
**Returns:** Simple transcript + segments (no NMT/TTS metadata)

### 2. Updated STT Service
**File:** `app/stt/services.py`

Changed the async transcription method to use the new task:
```python
# Before:
from app.jobs.tasks.pipeline import stt_transcribe as transcribe_task

# After:
from app.jobs.tasks.pipeline import stt_transcribe_only as transcribe_task
```

### 3. Preserved Full Pipeline Task
**File:** `app/jobs/tasks/pipeline.py`

The original `stt_transcribe` task remains **unchanged** and still:
- Dispatches NMT translation for each segment progressively
- Dispatches TTS synthesis for each translated segment
- Uses SegmentBuffer for ordering
- Returns full pipeline metadata

## API Behavior After Changes

### `/api/transcription/transcribe-async`
**Before:** Triggered full pipeline (STT → NMT → TTS)
**After:** Only transcribes (STT only)

### Full Pipeline Endpoint (Future)
The original `stt_transcribe` task can be used by a future `/api/dubbing/full-pipeline` endpoint.

## Verification

✓ Both tasks exist in pipeline.py:
  - `stt_transcribe_only` (line 34) - no NMT/TTS
  - `stt_transcribe` (line 200) - full pipeline

✓ Service imports correct task:
  - `app/stt/services.py` uses `stt_transcribe_only`

✓ Python syntax valid for both files

## Worker Impact

No worker changes needed - both tasks run on the same `ai_stt` queue.
The worker will automatically pick up both task types.

## Testing Recommendation

After restarting the workers:
```bash
# Restart STT worker to pick up new task
celery -A app.jobs.celery_app worker -Q ai_stt --pool=solo -E -n stt@%h
```

Test the endpoint:
```bash
POST /api/transcription/transcribe-async?video_id=xxx&language=en
```

Expected: Job completes with transcript + segments only (no NMT/TTS dispatch).
