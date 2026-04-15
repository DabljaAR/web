# SILMA-TTS Integration - Changes Summary

**Date**: 2026-04-06  
**Status**: ✅ Complete  
**Migration**: Habibi-TTS → SILMA-TTS

---

## Overview

Successfully migrated the DabljaAR backend from Habibi-TTS to SILMA-TTS, a more advanced and flexible Arabic text-to-speech system that supports voice cloning with reference audio.

---

## Files Modified

### 1. **requirements.txt**
```diff
- habibi-tts>=0.1.1
+ silma-tts>=0.1.0
```

### 2. **app/config.py**
- Removed all `HABIBI_*` settings
- Added new SILMA-TTS configuration:
  ```python
  SILMA_DEVICE: str                    # "auto", "cpu", "cuda"
  SILMA_REFERENCE_AUDIO: str           # Path to reference audio
  SILMA_REFERENCE_TEXT: str            # Reference audio transcript
  TTS_DEFAULT_SPEED: float             # 1.0 (changed from 0.8)
  TTS_DEFAULT_CFG_STRENGTH: float      # 1.0 (changed from 3.0)
  TTS_DEFAULT_NFE_STEP: int            # 32 (new)
  TTS_DEFAULT_SWAY_COEF: float         # -1.0 (new)
  TTS_DEFAULT_TARGET_RMS: float        # 0.12 (new)
  ```

### 3. **app/tts/models.py** (Complete Rewrite)
- Replaced `HabibiTTSModelManager` with `SilmaTTSModelManager`
- Simplified architecture (no dialect-specific configs)
- Updated to use SILMA-TTS API:
  ```python
  from silma_tts.api import SilmaTTS
  
  model.infer(
      ref_file=ref_audio,
      ref_text=ref_text,
      gen_text=text,
      file_wave=output_path,
      speed=1.0,
      cfg_strength=1.0,
      nfe_step=32,
      sway_sampling_coef=-1.0,
      target_rms=0.12,
      seed=None
  )
  ```

### 4. **app/tts/services.py**
- Removed `dialect` parameter from `submit_tts()`
- Added new SILMA-specific parameters:
  - `nfe_step`
  - `sway_sampling_coef`
  - `target_rms`
  - `seed`
- Updated health check to reference `SilmaTTSModelManager`

### 5. **app/tts/schema.py**
- Removed `ArabicDialect` enum
- Removed `dialect` field from all request/response models
- Added new fields to `TTSRequest`:
  ```python
  nfe_step: Optional[int]
  sway_sampling_coef: Optional[float]
  target_rms: Optional[float]
  seed: Optional[int]
  ```
- Updated all example payloads

### 6. **app/jobs/tasks/pipeline.py**
- Removed `dialect="MSA"` from TTS task dispatch
- Progressive TTS now dispatches with simplified parameters:
  ```python
  synthesize_tts.apply_async(
      kwargs={
          "text": txt,
          "job_id": f"{job_id}_segment_{idx}",
          "upload_to_minio": True,
          "minio_key": f"tts/{video_id}/segment_{idx}.wav",
      },
      queue="ai_tts",
  )
  ```

### 7. **.env.example**
Complete TTS section rewrite:
```env
# ========== TEXT-TO-SPEECH (TTS - SILMA) ==========
SILMA_DEVICE=auto
SILMA_REFERENCE_AUDIO=/path/to/reference.wav
SILMA_REFERENCE_TEXT="في هذا الدرس سنتعرف على أساسيات Machine Learning"
TTS_DEFAULT_SPEED=1.0
TTS_DEFAULT_CFG_STRENGTH=1.0
TTS_DEFAULT_NFE_STEP=32
TTS_DEFAULT_SWAY_COEF=-1.0
TTS_DEFAULT_TARGET_RMS=0.12
```

---

## New Files Created

1. **SILMA_TTS_MIGRATION.md** - Complete migration guide with:
   - Configuration examples
   - Quality presets
   - Troubleshooting tips
   - API usage examples

2. **test_silma_integration.py** - Integration test script to verify:
   - SILMA-TTS installation
   - Model loading
   - Configuration
   - Model manager functionality

3. **app/tts/models.py.backup** - Backup of original Habibi-TTS implementation

---

## Breaking API Changes

### Removed:
- `dialect` parameter (was required in Habibi-TTS)
- All Habibi-specific paths and configurations

### Added:
- `nfe_step` - Number of function evaluations (quality control)
- `sway_sampling_coef` - Sway sampling coefficient
- `target_rms` - Audio normalization level
- `seed` - Random seed for reproducibility

### Changed Defaults:
- `TTS_DEFAULT_SPEED`: `0.8` → `1.0` (more natural speech rate)
- `TTS_DEFAULT_CFG_STRENGTH`: `3.0` → `1.0` (better quality balance)

---

## Required Setup Steps

### 1. Install SILMA-TTS
```bash
pip uninstall habibi-tts
pip install silma-tts
```

### 2. Update Environment Variables
Copy settings from `.env.example` to `.env`:
```bash
SILMA_DEVICE=auto
SILMA_REFERENCE_AUDIO=/path/to/your/reference.wav
SILMA_REFERENCE_TEXT="النص المرجعي"
```

### 3. Prepare Reference Audio
- Format: WAV or MP3
- Sample Rate: 24kHz (recommended)
- Duration: 10-30 seconds
- Quality: Clear speech, no background noise

### 4. Test Installation
```bash
python test_silma_integration.py
```

### 5. Restart Workers
```bash
./stop_dev.sh
./start_dev.sh
```

---

## Key Improvements

1. **Better Quality**: Higher fidelity speech synthesis
2. **Voice Cloning**: Any reference audio can be used for voice matching
3. **Flexibility**: Supports mixed Arabic-English text natively
4. **Simpler API**: No dialect parameter needed
5. **More Control**: Additional parameters for fine-tuning quality and style
6. **Auto-transcription**: Reference text is optional

---

## Compatibility Notes

### Backward Compatibility
- ⚠️ **Breaking**: `dialect` parameter removed from all TTS endpoints
- ⚠️ **Breaking**: Reference audio is now **required** (set in `.env`)
- ✅ All other parameters remain compatible
- ✅ Job tracking and status APIs unchanged
- ✅ MinIO upload functionality unchanged

### Worker Configuration
- Still requires `--pool=solo` (blocking inference)
- Queue remains `ai_tts`
- Task name unchanged: `app.jobs.tasks.tts.synthesize`

---

## Testing

### Unit Test
```bash
python test_silma_integration.py
```

### API Test
```bash
curl -X POST http://localhost:8000/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "مرحباً بكم في منصة دبلجة عربية",
    "speed": 1.0,
    "upload_to_minio": true
  }'
```

### Pipeline Test
```bash
# Transcribe a video - TTS will be triggered automatically
POST /api/transcription/transcribe-async?video_id=123&language=en&target_lang=arb_Arab
```

---

## Rollback Procedure

If you need to rollback to Habibi-TTS:

1. Restore backup:
   ```bash
   cp app/tts/models.py.backup app/tts/models.py
   ```

2. Revert requirements:
   ```bash
   pip uninstall silma-tts
   pip install habibi-tts
   ```

3. Restore config (use git):
   ```bash
   git checkout HEAD -- app/config.py app/tts/schema.py app/tts/services.py .env.example
   ```

---

## Support & Resources

- **SILMA-TTS GitHub**: https://github.com/SILMA-AI/silma-tts
- **Migration Guide**: `SILMA_TTS_MIGRATION.md`
- **Test Script**: `test_silma_integration.py`
- **API Docs**: http://localhost:8000/docs#/TTS

---

**Reviewed by**: AI Assistant  
**Approved by**: Pending human review  
**Next Steps**: Test in production environment
