# TTS Audio Access Guide

## ✅ Configuration Confirmed

The pipeline is **already correctly configured** for MinIO upload:

```python
# In app/jobs/tasks/pipeline.py line 234
"upload_to_minio": True,
"minio_key": f"tts/{video_id}/segment_{idx}.wav",
```

## 🎵 Where to Access TTS Audio

### 1. From TTS Task Results (Recommended)

Each TTS task returns an `audio_url` field with a **presigned URL**:

```json
{
  "status": "success",
  "job_id": "abc123_segment_0", 
  "dialect": "MSA",
  "minio_key": "tts/12345-abcd/segment_0.wav",
  "audio_url": "http://localhost:9000/dablaja-videos/tts/12345-abcd/segment_0.wav?AWSAccessKeyId=...&Expires=...",
  "bytes_size": 45678
}
```

**How to get this:**
1. Check Flower UI: http://localhost:5566
2. Find completed TTS tasks (named like `{job_id}_segment_0`)
3. Click task → Result → copy `audio_url`
4. Paste in browser or media player

### 2. Direct MinIO URLs

If the MinIO bucket is public, you can access directly:

```
http://localhost:9000/dablaja-videos/tts/{video_id}/segment_{N}.wav
```

**Example:**
```
http://localhost:9000/dablaja-videos/tts/58cf2705-85c1-4cf6-a1c2-673df98bba92/segment_0.wav
http://localhost:9000/dablaja-videos/tts/58cf2705-85c1-4cf6-a1c2-673df98bba92/segment_1.wav
http://localhost:9000/dablaja-videos/tts/58cf2705-85c1-4cf6-a1c2-673df98bba92/segment_2.wav
```

### 3. MinIO Web Console

Access MinIO's built-in file browser:

1. Go to: http://localhost:9000
2. Login: `minioadmin` / `minioadmin` 
3. Navigate: `dablaja-videos` → `tts` → `{video_id}`
4. Click any `.wav` file to download/play

### 4. Command Line Download

```bash
# Download specific segment
curl -o segment_0.wav "http://localhost:9000/dablaja-videos/tts/VIDEO_ID/segment_0.wav"

# Play directly with ffplay
ffplay "http://localhost:9000/dablaja-videos/tts/VIDEO_ID/segment_0.wav"
```

## 📋 How to Find Your Audio Files

### Step 1: Get Video ID
When you upload a file, note the `video_id` from the response:
```json
{
  "video_id": "58cf2705-85c1-4cf6-a1c2-673df98bba92",
  "status": "COMPLETED"
}
```

### Step 2: Check TTS Task Completion  
Monitor in Flower (http://localhost:5566):
- Look for tasks like `synthesize_tts`
- Job names: `{original_job_id}_segment_0`, `{original_job_id}_segment_1`, etc.
- Status should be `SUCCESS`

### Step 3: Access Audio
Use any of the methods above with your `video_id`.

## 🔧 Current Configuration

```
MinIO Endpoint: http://localhost:9000  
Bucket: dablaja-videos
TTS Path: tts/{video_id}/segment_{N}.wav
Upload: ✅ Enabled (upload_to_minio=True)
Presigned URLs: ✅ 1 hour expiry
```

## 🎯 Example Workflow

1. **Upload audio:** `POST /api/videos/upload/audio`
   ```json
   {"video_id": "12345-abcd", "status": "PENDING"}
   ```

2. **Start transcription:** `POST /api/transcription/transcribe-async?video_id=12345-abcd`
   ```json
   {"task_id": "job-67890", "status": "queued"}
   ```

3. **Monitor progress:** http://localhost:5566
   - STT task completes → segments dispatched to NMT
   - NMT tasks complete → segments dispatched to TTS  
   - TTS tasks complete → audio files ready

4. **Access audio files:**
   - **Direct:** `http://localhost:9000/dablaja-videos/tts/12345-abcd/segment_0.wav`
   - **Presigned:** From TTS task result `audio_url` field
   - **Browser:** http://localhost:9000 → login → navigate to files

## ✅ Verification

The progressive TTS pipeline is working correctly with MinIO upload enabled. Audio files will be automatically uploaded to MinIO as each segment is synthesized, and you can access them immediately via the URLs above.
