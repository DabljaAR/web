# SILMA-TTS Migration Guide

## Overview

The DabljaAR backend has been migrated from Habibi-TTS to SILMA-TTS for improved Arabic speech synthesis quality and flexibility.

## Key Changes

### 1. Dependencies
- **Removed**: `habibi-tts>=0.1.1`
- **Added**: `silma-tts>=0.1.0`

### 2. Configuration (.env)

**Old (Habibi-TTS)**:
```env
HABIBI_DEVICE=auto
HABIBI_TTS_SRC=
HABIBI_MODEL_PATH=
HABIBI_REFERENCE_AUDIO=
TTS_DEFAULT_SPEED=0.8
TTS_DEFAULT_CFG_STRENGTH=3.0
```

**New (SILMA-TTS)**:
```env
SILMA_DEVICE=auto
SILMA_REFERENCE_AUDIO=/path/to/reference.wav
SILMA_REFERENCE_TEXT="النص المرجعي للصوت"
TTS_DEFAULT_SPEED=1.0
TTS_DEFAULT_CFG_STRENGTH=1.0
TTS_DEFAULT_NFE_STEP=32
TTS_DEFAULT_SWAY_COEF=-1.0
TTS_DEFAULT_TARGET_RMS=0.12
```

### 3. Model Manager

- **File**: `app/tts/models.py`
- **Old**: `HabibiTTSModelManager`
- **New**: `SilmaTTSModelManager`

### 4. API Changes

#### Removed Parameters:
- `dialect` (SILMA supports all Arabic varieties natively)

#### New Parameters:
- `nfe_step`: Number of function evaluations (quality control)
- `sway_sampling_coef`: Sway sampling coefficient
- `target_rms`: Audio normalization level
- `seed`: Random seed for reproducibility

### 5. Reference Audio Setup

SILMA-TTS **requires** a reference audio file for voice cloning:

1. **Prepare Reference Audio**:
   - Format: WAV or MP3
   - Sample Rate: 24kHz (recommended)
   - Duration: 10-30 seconds of clear speech
   - Quality: High-quality recording without background noise

2. **Set Environment Variables**:
   ```env
   SILMA_REFERENCE_AUDIO=/path/to/your/reference.wav
   SILMA_REFERENCE_TEXT="Transcript of the reference audio"
   ```

3. **Optional**: Reference text can be auto-transcribed if not provided

### 6. Quality Presets

SILMA-TTS supports different quality/style presets through parameter combinations:

#### Lecture/Professional (Default)
```python
cfg_strength=1.2
nfe_step=32
sway_sampling_coef=-1.0
speed=0.96
target_rms=0.12
```

#### Natural/Human
```python
cfg_strength=1.0
nfe_step=40
sway_sampling_coef=-1.0
speed=0.94
target_rms=0.12
```

#### Energetic/Expressive
```python
cfg_strength=1.3
nfe_step=32
sway_sampling_coef=-0.7
speed=1.02
target_rms=0.14
```

## Migration Steps

### 1. Update Dependencies
```bash
pip uninstall habibi-tts
pip install silma-tts
```

### 2. Update Environment Variables
Copy `.env.example` and update your `.env` file with the new SILMA-TTS settings.

### 3. Prepare Reference Audio
Create or obtain a reference audio file and set `SILMA_REFERENCE_AUDIO` path.

### 4. Restart Workers
```bash
./stop_dev.sh
./start_dev.sh
```

### 5. Test TTS
```bash
# Test via API
curl -X POST http://localhost:8000/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "مرحباً بكم في منصة دبلجة عربية",
    "speed": 1.0,
    "upload_to_minio": true
  }'
```

## Breaking Changes

1. **Dialect parameter removed**: SILMA works with all Arabic varieties automatically
2. **Reference audio required**: Must set `SILMA_REFERENCE_AUDIO` in .env
3. **Default speed changed**: 0.8 → 1.0 (more natural)
4. **Default cfg_strength changed**: 3.0 → 1.0 (better quality)

## Benefits

1. **Better Quality**: Higher fidelity speech synthesis
2. **Voice Cloning**: Use any reference audio for voice matching
3. **Flexibility**: Supports mixed Arabic-English text
4. **Auto-transcription**: Reference text is optional
5. **Fine-tuning**: More control parameters for quality/style

## Troubleshooting

### Issue: "Reference audio not found"
**Solution**: Verify `SILMA_REFERENCE_AUDIO` path exists and is readable

### Issue: "SILMA-TTS not installed"
**Solution**: Run `pip install silma-tts`

### Issue: Audio quality issues
**Solution**: 
- Increase `nfe_step` to 40 or 50
- Adjust `cfg_strength` between 1.0-1.5
- Ensure reference audio is high quality (24kHz, clear speech)

### Issue: Slow synthesis
**Solution**:
- Decrease `nfe_step` to 32
- Use GPU: set `SILMA_DEVICE=cuda`
- Reduce text length per request

## Additional Resources

- SILMA-TTS GitHub: https://github.com/SILMA-AI/silma-tts
- API Documentation: http://localhost:8000/docs#/TTS
- Reference Audio Guide: See notebook example in project root

---

**Date**: 2026-04-06
**Version**: 1.0.0
