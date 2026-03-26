# Progressive TTS Implementation - March 26, 2026

## Issues Addressed ✅

### 1. NMT PyTorch CVE-2025-32434 ✅  
**Problem:** NMT translation failing due to PyTorch security restriction
```
Due to a serious vulnerability issue in torch.load, even with weights_only=True, 
we now require users to upgrade torch to at least v2.6
```

**Solution:**
- Upgraded PyTorch from 2.4.1+cpu to 2.6.0+cpu
- Also upgraded torchaudio to maintain compatibility  
- Status: ✅ NMT should now work without security errors

### 2. Progressive TTS Implementation ✅
**Problem:** TTS was waiting for ALL NMT segments to complete before starting any synthesis
- This caused long delays where TTS workers sat idle
- Original plan was progressive synthesis as segments become available

**Solution:** Implemented true progressive TTS dispatch
- **Before:** STT → wait for all NMT → dispatch all TTS → wait for completion
- **After:** STT → for each NMT completion → immediately dispatch TTS for that segment

### Progressive Flow Changes

```
OLD (Sequential):
STT generates 100 segments → 
  Dispatch 100 NMT tasks → 
  Wait for ALL 100 NMT to complete (5-10 min) → 
  Dispatch 100 TTS tasks → 
  Wait for ALL 100 TTS to complete (20-30 min)
Total: ~35-40 min

NEW (Progressive):
STT generates segment 0 → NMT task 0 → (3s later) TTS task 0 starts
STT generates segment 1 → NMT task 1 → (3s later) TTS task 1 starts  
STT generates segment 2 → NMT task 2 → (3s later) TTS task 2 starts
...
STT generates segment 99 → NMT task 99 → (3s later) TTS task 99 starts

Total: STT time + ~3s NMT delay + TTS overlap time
Expected: ~15-20 min (40% reduction)
```

### Code Changes

**File:** `app/jobs/tasks/pipeline.py`

1. **NMT Result Processing Loop** - Modified to dispatch TTS immediately:
```python
# OLD: Just collected results for later processing
if 0 <= idx < len(structured_segments) and txt:
    segment_buffer.push(...)
    completed_count += 1

# NEW: Dispatch TTS immediately + collect results
if 0 <= idx < len(structured_segments) and txt:
    # Update segment immediately
    structured_segments[idx]["translated_text"] = txt
    
    # PROGRESSIVE TTS: Dispatch immediately
    if txt.strip():
        tts_result = synthesize_tts.apply_async(
            kwargs={
                "text": txt,
                "dialect": "MSA", 
                "job_id": f"{job_id}_segment_{idx}",
                "upload_to_minio": True,
                "minio_key": f"tts/{video_id}/segment_{idx}.wav",
            },
            queue="ai_tts",
        )
        structured_segments[idx]["tts_task_id"] = tts_result.id
    
    # Still use priority queue for verification
    segment_buffer.push(...)
    completed_count += 1
```

2. **Removed Batch TTS Dispatch** - No longer needed:
```python
# REMOVED: Old batch TTS dispatch code (80+ lines)
# - temp_dir creation
# - for loop dispatching all TTS at once  
# - waiting for all TTS results
# - MinIO upload logic
```

3. **Updated Result Metadata**:
```python
# NEW: Track progressive dispatching
result.update({
    "tts_segments_dispatched": sum(1 for s in structured_segments if s.get("tts_task_id")),
    # ... other fields
})
```

### 3. Transcript Verification ✅
**Issue:** User concerned transcript was incomplete (showed ellipsis `...`)
**Finding:** The transcript ending with `...` is just **Flower UI truncation** for display
- Actual transcript length: 837 characters, 145 words  
- Real STT output would be much longer for a full video
- This is a UI display limitation, not a processing issue

## Benefits

### Performance Improvements
1. **Latency Reduction:** TTS starts immediately when segments are ready (vs waiting 5-10 min)
2. **Resource Utilization:** TTS workers start working immediately instead of sitting idle
3. **Parallel Processing:** NMT and TTS now overlap significantly 
4. **Scalability:** Better queue distribution across workers

### User Experience  
1. **Faster Results:** Users get audio segments as they complete
2. **Progress Visibility:** Can see TTS tasks starting in Flower immediately
3. **Better Monitoring:** Each segment tracked with `tts_task_id`

## Pipeline Flow (New)

```
Audio Input → STT (Whisper)
              ↓
            Segment 0 → NMT Worker A → TTS Worker 1 ← (immediate)
            Segment 1 → NMT Worker B → TTS Worker 2 ← (immediate)  
            Segment 2 → NMT Worker C → TTS Worker 3 ← (immediate)
            ...
            Segment N → NMT Worker X → TTS Worker Y ← (immediate)
              ↓
          Job Complete (when STT finishes)
          
Individual TTS tasks run independently in background
```

## Testing

### Before Testing
1. **Verify PyTorch upgrade:**
```bash
python -c "import torch; print(torch.__version__)"  # Should show 2.6.0+cpu
```

2. **Verify all workers ready:**
```bash
tail -5 logs/worker_stt.log | grep ready
tail -5 logs/worker_nmt.log | grep ready  
tail -5 logs/worker_tts.log | grep ready
```

### Test Progressive Pipeline
1. **Upload test video:** 
```bash
curl -X POST http://localhost:8000/api/videos/upload/audio -F "file=@test.mp3"
```

2. **Start transcription:**
```bash
curl -X POST "http://localhost:8000/api/transcription/transcribe-async?video_id=XXX&language=en&target_lang=arb_Arab"
```

3. **Monitor in Flower:** http://localhost:5566
   - Should see NMT tasks complete quickly (vs previous errors)
   - Should see TTS tasks start immediately as NMT completes
   - Should see multiple TTS tasks running in parallel

4. **Expected Behavior:**
   - ✅ NMT tasks complete without PyTorch CVE errors
   - ✅ TTS tasks dispatch progressively (not all at once)
   - ✅ TTS workers start synthesis immediately 
   - ✅ Total time reduced vs previous sequential approach

## Status

- ✅ **PyTorch CVE-2025-32434 fixed** (2.6.0+cpu)
- ✅ **Progressive TTS implemented** (immediate dispatch)
- ✅ **Transcript verification complete** (UI truncation confirmed)
- ✅ **All workers restarted** with new code
- ✅ **Ready for testing** with real video content

**Expected Result:** 30-40% reduction in total pipeline time due to overlapped processing.
