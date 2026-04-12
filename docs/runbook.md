# DabljaAR — Troubleshooting & Operations Runbook

> Operational playbook for diagnosing and resolving common production issues.

---

## Quick Health Checks

```bash
# Is the API alive?
curl http://localhost:8000/docs

# Is Redis responding?
docker compose exec redis redis-cli ping
# Expected: PONG

# Are workers registered?
celery -A app.jobs.celery_app inspect active
celery -A app.jobs.celery_app inspect ping

# Check Flower dashboard
open http://localhost:5555
```

---

## Common Issues

### 1. Redis Connection Refused

**Symptoms:** Workers crash on startup, `ConnectionRefusedError`, tasks never execute.

**Diagnosis:**
```bash
docker compose ps redis
docker compose logs redis
```

**Fix:**
```bash
docker compose up redis -d
# Or restart
docker compose restart redis
```

**Verify:**
```bash
docker compose exec redis redis-cli ping
```

---

### 2. Workers Not Picking Up Tasks

**Symptoms:** Jobs stay in `QUEUED` forever, Flower shows 0 active workers.

**Diagnosis:**
```bash
# Check worker processes
docker compose ps worker-media worker-pipeline
docker compose logs --tail=50 worker-media

# Inspect registered tasks
celery -A app.jobs.celery_app inspect registered
```

**Common causes:**
- Worker crashed → `docker compose restart worker-media worker-pipeline`
- Queue mismatch → Verify `--queues=media` matches `task_routes` in `celery_app.py`
- Import error in task module → Check worker logs for `ImportError`

**Fix:**
```bash
docker compose restart worker-media worker-pipeline
```

---

### 3. Stuck / Zombie Jobs (Processing forever)

**Symptoms:** Job status is `PROCESSING` but Flower shows no active task.

**Diagnosis:**
```sql
-- Find stuck jobs (processing for over 1 hour)
SELECT id, job_type, status, started_at, NOW() - started_at AS duration
FROM jobs
WHERE status = 'processing'
  AND started_at < NOW() - INTERVAL '1 hour';
```

**Fix — Manual status update:**
```sql
UPDATE jobs
SET status = 'failed', error_message = 'Manually failed: worker lost', updated_at = NOW()
WHERE id = '<job_id>';
```

**Fix — Revoke the Celery task:**
```bash
celery -A app.jobs.celery_app control revoke <celery_task_id> --terminate
```

---

### 4. Database Connection Pool Exhausted

**Symptoms:** `sqlalchemy.exc.TimeoutError: QueuePool limit exceeded`.

**Diagnosis:**
```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'dabljaar';
```

**Fix:**
- Increase pool size in `config.py`: `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`
- Restart backend: `docker compose restart backend`
- Identify connection leaks: look for sessions not properly closed in async context managers

---

### 5. FFmpeg Errors in Media Worker

**Symptoms:** `VIDEO_PROCESS` jobs fail, error mentions `ffmpeg`.

**Diagnosis:**
```bash
docker compose exec worker-media which ffmpeg
docker compose exec worker-media ffmpeg -version
docker compose logs worker-media | grep -i ffmpeg
```

**Common causes:**
- `ffmpeg` not installed in worker image → Check Dockerfile includes `ffmpeg` in `apt-get install`
- Input file not found → Check storage paths and mount volumes
- Codec not supported → Check FFmpeg build flags

---

### 6. Alembic Migration Failures

**Symptoms:** Backend container fails to start, logs show `alembic.util.exc.CommandError`.

**Diagnosis:**
```bash
docker compose logs backend | grep -i alembic
# Check current revision
cd backend && alembic current
```

**Fix — Stamp to current and re-run:**
```bash
alembic stamp head    # Mark DB as up-to-date
alembic upgrade head  # Re-apply migrations
```

**Fix — Resolve merge conflict:**
```bash
alembic merge heads -m "merge branches"
alembic upgrade head
```

---

### 7. Frontend Build / Vite Errors

**Symptoms:** `npm run dev` fails, import errors, blank white page.

**Diagnosis:**
```bash
cd frontend
npm run build 2>&1 | head -50  # Check for build errors
```

**Common fixes:**
```bash
rm -rf node_modules package-lock.json
npm install
npm run dev
```

**Environment variable issues:**
- Ensure `VITE_API_BASE_URL` is set in `.env`
- Vite requires env vars to start with `VITE_`

---

### 8. CORS Errors in Browser

**Symptoms:** `Access-Control-Allow-Origin` errors in browser console.

**Fix:** Ensure backend middleware includes the frontend origin:

```python
# app/main.py — check CORSMiddleware
allow_origins=["http://localhost:5173", "http://localhost:3000"]
```

---

## Operational Procedures

### Manually Retry a Failed Job

```bash
# Via API
curl -X PATCH http://localhost:8000/api/jobs/<job_id>/progress \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"status": "queued", "progress": 0, "error_message": null}'
```

Then re-dispatch the Celery task:
```python
from app.jobs.tasks.media import process_video
process_video.delay(job_id="<job_id>", video_id="<video_id>", input_path="...")
```

### Cancel a Running Job

```bash
# Via API
curl -X POST http://localhost:8000/api/jobs/<job_id>/cancel \
  -H "Authorization: Bearer <token>"
```

### Purge All Pending Tasks

```bash
celery -A app.jobs.celery_app purge           # All queues
celery -A app.jobs.celery_app purge -Q media  # Media queue only
```

### Inspect Queue Lengths

```bash
# Via Redis CLI
docker compose exec redis redis-cli LLEN media
docker compose exec redis redis-cli LLEN pipeline
```

### Scale Workers

```bash
# Scale media workers to 3 instances
docker compose up --scale worker-media=3 -d
```

---

## Log Locations

| Component | Location | Notes |
|-----------|----------|-------|
| Backend API | `backend/logs/` + stdout | `shared/logging.py` config |
| Media Worker | `docker compose logs worker-media` | Celery task output |
| Pipeline Worker | `docker compose logs worker-pipeline` | AI task output |
| PostgreSQL | `docker compose logs postgres` | Query errors |
| Redis | `docker compose logs redis` | Connection issues |
| Flower | `docker compose logs flower` | Monitoring UI |

**Tail all logs:**
```bash
docker compose logs -f --tail=100
```

**Filter by service:**
```bash
docker compose logs -f worker-media worker-pipeline
```

---

## Monitoring with Flower

Flower dashboard: [http://localhost:5555](http://localhost:5555)

Key pages:
- **Dashboard** → Active/processed/failed task counts per worker
- **Tasks** → Individual task state, args, runtime, retries
- **Workers** → Online workers, CPU, load average
- **Broker** → Queue sizes and message rates

### Useful Flower API Endpoints

```bash
# Worker status
curl http://localhost:5555/api/workers

# Task info
curl http://localhost:5555/api/task/info/<task_id>

# Queue lengths
curl http://localhost:5555/api/queues/length
```

---

## Emergency: Full Reset

**Warning:** This destroys all data.

```bash
docker compose down -v          # Stop services + delete volumes
docker compose up --build -d    # Rebuild and start fresh
```

If only the database needs resetting:
```bash
docker compose down postgres
docker volume rm dabljaar_postgres_data
docker compose up postgres -d
cd backend && alembic upgrade head
```

---

## GPU Setup and Validation

### Install CUDA-enabled PyTorch

```bash
pip uninstall torch torchaudio
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Verify CUDA

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda, torch.cuda.device_count())"
```

### Runtime Configuration

Set in environment:

```env
STT_DEVICE=cuda
SILMA_DEVICE=cuda
STT_COMPUTE_TYPE=float16
```

For low VRAM:

```env
STT_MODEL_SIZE=small
STT_GPU_MEMORY_THRESHOLD=0.7
```
