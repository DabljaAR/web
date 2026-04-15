# Arabic Dialects with SILMA-TTS

## How Dialects Work in SILMA-TTS vs Habibi-TTS

### Old Way (Habibi-TTS)
```json
POST /api/tts/synthesize
{
  "text": "مرحبا بكم",
  "dialect": "EGY"  // Egyptian or MSA
}
```

### New Way (SILMA-TTS)
```json
POST /api/tts/synthesize
{
  "text": "مرحبا بكم",
  // No dialect parameter - use reference audio instead!
}
```

## How to Get Egyptian Dialect with SILMA-TTS

SILMA-TTS uses **voice cloning** instead of dialect parameters. To get Egyptian Arabic:

1. **Get Egyptian Reference Audio** (10-30 seconds)
   - Record an Egyptian speaker saying Arabic text
   - Or use existing Egyptian Arabic audio
   - Save as WAV/MP3, preferably 24kHz

2. **Set in Environment (.env)**
   ```env
   SILMA_REFERENCE_AUDIO=/path/to/egyptian_voice.wav
   SILMA_REFERENCE_TEXT="النص المسجل بالصوت المرجعي"
   ```

3. **SILMA automatically adapts** to the accent/dialect in your reference audio

## Multiple Dialect Support

For different dialects, you can:

### Option 1: Multiple Reference Audio Files
```env
# Egyptian dialect
SILMA_REFERENCE_AUDIO_EGY=/path/to/egyptian_voice.wav
SILMA_REFERENCE_TEXT_EGY="النص المصري"

# MSA (Modern Standard Arabic)
SILMA_REFERENCE_AUDIO_MSA=/path/to/msa_voice.wav
SILMA_REFERENCE_TEXT_MSA="النص الفصيح"

# Gulf dialect
SILMA_REFERENCE_AUDIO_GULF=/path/to/gulf_voice.wav
SILMA_REFERENCE_TEXT_GULF="النص الخليجي"
```

### Option 2: Dynamic Reference in API Call
```json
POST /api/tts/synthesize
{
  "text": "أهلا وسهلا",
  "ref_audio_path": "/path/to/egyptian_speaker.wav",
  "ref_text": "النص المرجعي المصري"
}
```

## Advantages of SILMA-TTS Approach

1. **More Natural**: Clones actual human voices, not synthetic dialects
2. **Any Accent**: Works with any Arabic variety (Egyptian, Levantine, Gulf, Moroccan, etc.)
3. **Personalization**: Can clone specific speakers
4. **Better Quality**: More natural prosody and pronunciation

## Getting Egyptian Reference Audio

### Professional Sources:
- Egyptian news broadcasts (Al-Ahram, etc.)
- Egyptian YouTube content creators
- Egyptian audiobooks/podcasts

### Recording Your Own:
```bash
# Use Egyptian speaker to record:
"أهلا وسهلا، إزيك؟ النهاردة هنتكلم عن الذكاء الاصطناعي وإزاي بيشتغل في مصر."
```

### Technical Requirements:
- **Duration**: 10-30 seconds optimal
- **Quality**: Clear, no background noise  
- **Format**: WAV (preferred) or MP3
- **Sample Rate**: 24kHz recommended
- **Single Speaker**: One person only

## Example Configuration for Egyptian TTS

```env
# .env file
SILMA_DEVICE=cpu
SILMA_REFERENCE_AUDIO=/home/user/voices/egyptian_speaker.wav
SILMA_REFERENCE_TEXT="أهلا وسهلا، إزيك؟ النهاردة هنتكلم عن الذكاء الاصطناعي."
```

## Testing Egyptian TTS

```bash
curl -X POST http://localhost:8000/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "إزيك؟ أهلا وسهلا بيك في مصر!",
    "speed": 1.0,
    "nfe_step": 32
  }'
```

The output will automatically have Egyptian accent based on your reference audio!