# DabljaAR — API Reference

> Auto-generated documentation is available at **`/docs`** (Swagger UI) and **`/redoc`** (ReDoc) when the FastAPI server is running.

---

## Base URL

```
http://localhost:8000/api
```

All endpoints below are relative to this base.

---

## Authentication

All protected endpoints require:

```
Authorization: Bearer <access_token>
```

### Auth Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/signup` | Register a new user | ✗ |
| `POST` | `/login` | Login, returns token pair | ✗ |
| `POST` | `/logout` | Logout | ✓ |
| `POST` | `/auth/refresh` | Exchange refresh → new access token | ✗ |
| `GET` | `/me` | Current user profile | ✓ |
| `PATCH` | `/me` | Update profile | ✓ |

### Token Pair

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

- **Access token TTL:** 15 minutes
- **Refresh token TTL:** 7 days

---

## Media Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/videos/upload` | Upload video → creates Job | ✓ |
| `POST` | `/videos/upload/audio` | Upload audio → creates Job | ✓ |
| `POST` | `/videos/upload/text` | Upload text (no Job) | ✓ |
| `POST` | `/videos/upload/hls` | Upload video → HLS Job | ✓ |
| `GET` | `/videos/` | List user's videos (paginated) | ✓ |
| `GET` | `/videos/dashboard` | Active + recent videos | ✓ |
| `GET` | `/videos/{id}` | Get video detail | ✓ |
| `DELETE` | `/videos/{id}` | Delete video + files | ✓ |

### Upload Response

```json
{
  "id": "uuid-of-video",
  "job_id": "uuid-of-job",
  "message": "The media is being processed",
  "status": "PENDING"
}
```

### Pagination (GET /videos/)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `limit` | int | 10 | Items per page (max 100) |
| `search` | string | — | Search title or filename |
| `sortBy` | string | `date-desc` | Sort: `date-desc`, `date-asc`, `name-asc`, `name-desc`, `size-desc`, `size-asc` |
| `dateRange` | string | `allTime` | `today`, `thisWeek`, `thisMonth`, `last7Days`, `last30Days`, `last90Days`, `allTime` |
| `status` | string | — | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `mediaType` | string | — | `VIDEO`, `AUDIO`, `TEXT` |

---

## Job Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/jobs/{id}` | Get job status + progress | ✓ |
| `GET` | `/jobs/video/{video_id}` | All jobs for a video | ✓ |
| `GET` | `/jobs/` | List jobs (query params) | ✓ |
| `POST` | `/jobs/{id}/cancel` | Cancel a queued/processing job | ✓ |
| `PATCH` | `/jobs/{id}/progress` | Update job progress (internal) | ✓ |

### Job Response

```json
{
  "id": "uuid",
  "video_id": "uuid",
  "user_id": 1,
  "job_type": "VIDEO_PROCESS",
  "status": "PROCESSING",
  "progress": 60.0,
  "celery_task_id": "abc-123",
  "parent_job_id": null,
  "input_data": { "file_path_key": "videos/1/test.mp4" },
  "output_data": null,
  "error_message": null,
  "retry_count": 0,
  "max_retries": 3,
  "created_at": "2026-02-20T12:00:00",
  "updated_at": "2026-02-20T12:01:00",
  "started_at": "2026-02-20T12:00:05",
  "completed_at": null
}
```

### Job Types

| Type | Queue | Description |
|------|-------|-------------|
| `VIDEO_PROCESS` | `media` | Extract metadata, audio, thumbnail |
| `VIDEO_HLS` | `media` | Generate HLS stream |
| `STT_TRANSCRIBE` | `pipeline` | Whisper speech-to-text |
| `NMT_TRANSLATE` | `pipeline` | NLLB-200 translation |
| `TTS_SYNTHESIZE` | `pipeline` | MMS Arabic voice synthesis |
| `DUBBING_MERGE` | `pipeline` | FFmpeg merge dubbed audio |
| `FULL_DUBBING_PIPELINE` | `pipeline` | Orchestrates all AI stages |

### Job Status Values

| Status | Description |
|--------|-------------|
| `QUEUED` | Job created, waiting for worker pickup |
| `PROCESSING` | Worker is executing the task |
| `COMPLETED` | Finished successfully |
| `FAILED` | Task raised an exception |
| `RETRYING` | Failed and waiting for retry |
| `CANCELLED` | Cancelled via API |

---

## Error Responses

**Standard error:**
```json
{ "detail": "Human-readable error message" }
```

**Validation error (422):**
```json
{
  "detail": [
    { "loc": ["body", "email"], "msg": "invalid email", "type": "value_error" }
  ]
}
```

**Rate limit (429):**
```json
{ "detail": "Too many requests, wait 1 min and after 1 min make it can send request again" }
```