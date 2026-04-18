# Dubbing Pipeline

This document describes the async dubbing pipeline and how to validate it end-to-end.

## Pipeline Stages

```text
Audio/Video Input
  -> STT (Whisper)
  -> NMT (Arabic translation)
  -> TTS (Arabic synthesis)
  -> Merge/Output assets
```

Queues used:

- `ai_stt`
- `ai_nmt`
- `ai_tts`
- `pipeline`

## Progressive TTS Design

The pipeline dispatches TTS progressively as each translated segment is ready, instead of waiting for all NMT segments to finish.

Behavior:

- Before: STT -> all NMT -> all TTS
- Now: STT -> NMT segment N -> immediate TTS segment N

Benefits:

- Lower total wall-clock time
- Better worker utilization
- Faster first audio availability

## NMT Fallback Mode

NMT quality fallback depth is controlled by `NMT_FALLBACK_MODE`:

- `stage2_only`: run stage-1 and stage-2 retry, then stop
- `stage3_updated`: continue to stage-3 word-by-word only when updated quality score is high

The updated stage-3 quality score combines:

- Arabic script ratio: Arabic letters / all alphabetic letters
- Mixed-token penalty: penalizes mixed-script tokens like `multi-النموذج`

## Validation Checklist

1. Start stack and workers with fresh code
2. Upload sample media
3. Trigger async transcription/translation
4. Monitor Flower and job APIs

Expected:

- NMT outputs Arabic `translated_text`
- TTS jobs are created per segment as NMT completes
- TTS kwargs include MinIO upload parameters
- TTS output contains non-null storage key/URL
- Final combine preserves segment timing gaps/offsets
- For video inputs, final output is a dubbed video artifact (original video stream + replaced speech track)

## Smoke Test Commands

Upload:

```bash
curl -X POST http://localhost:8000/api/videos/upload/audio \
  -F "file=@sample.mp3" \
  -H "Authorization: Bearer <token>"
```

Run pipeline:

```bash
curl -X POST "http://localhost:8000/api/transcription/transcribe-async?video_id=<video_id>&language=en&target_lang=arb_Arab" \
  -H "Authorization: Bearer <token>"
```

Inspect workers:

```bash
celery -A app.jobs.celery_app inspect active
celery -A app.jobs.celery_app inspect registered
```

## Troubleshooting

- Old workers still running: restart all worker processes and purge stale queue items if needed.
- Missing Arabic synthesis: verify NMT results are Arabic and task payload to TTS uses translated text.
- Missing output files: verify MinIO env vars and bucket access.
