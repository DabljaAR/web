# TTS Silent Audio Issue - Fixed

## Problem
TTS synthesis was producing silent audio files with no speech.

## Root Cause
The code was looking for the MSA reference audio file at:
```
/home/moustafa/.cache/huggingface/hub/models--SWivid--Habibi-TTS/snapshots/.../assets/MSA.mp3
```

This file doesn't exist in the HuggingFace download. When the file was not found, the fallback code created a **silent reference audio** (`np.zeros()`), which caused the TTS model to clone a silent voice and produce silent output.

## Solution
The MSA.mp3 reference audio actually exists in the **installed habibi-tts package**:
```
.venv/lib/python3.12/site-packages/habibi_tts/assets/MSA.mp3
```

### Changes Made

1. **Updated `app/tts/models.py`** - Modified `_get_dialect_config()` to:
   - Use `importlib.util.find_spec()` to locate the installed habibi_tts package
   - Get reference audio from `package/assets/MSA.mp3` instead of HF snapshot
   - Keep fallback to snapshot path for backward compatibility

2. **Fixed variable shadowing bug** - Removed duplicate `import soundfile as sf` inside conditional block that was causing UnboundLocalError

3. **Updated AGENTS.md** - Removed outdated note about fallback silent audio

### Reference Audio Verification
```
Path: .venv/lib/python3.12/site-packages/habibi_tts/assets/MSA.mp3
Size: 146,285 bytes (0.14 MB)
Duration: 9.14 seconds
RMS amplitude: 0.171322 (has real speech!)
```

## Testing
After the fix, TTS synthesis now:
- ✅ Uses real Arabic voice reference audio
- ✅ Produces speech output (not silent)
- ✅ Successfully generates audio files with voice content

## Deployment
All services restarted with the fix applied:
```bash
cd /home/moustafa/dabljaAR/web/backend
bash stop_dev.sh
bash start_dev.sh
```

The TTS worker is now using the correct reference audio and should produce proper speech output.
