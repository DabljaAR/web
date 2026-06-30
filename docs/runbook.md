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

## Microservices observability (production)

The microservices stack ships with an optional self-hosted observability overlay. See [docs/observability.md](observability.md) for full setup.

### Quick access

| UI | URL |
|----|-----|
| Grafana (logs, metrics, traces) | `https://grafana.$DOMAIN` |
| RabbitMQ Management | `https://rabbitmq.$DOMAIN` |

### Debugging a failed job

1. **Find the job ID** from the API response, database, or user report (`parent_job_id` for the pipeline, child `job_id` per stage).

2. **Search logs in Grafana** → Explore → Loki:
   ```logql
   {service=~".+"} |= "YOUR_JOB_ID"
   ```
   Or open dashboard **Logs Explorer** (`dablja-logs`) and set the `job_id` variable.

3. **Check pipeline metrics** → dashboard **Pipeline** (`dablja-pipeline`):
   - Failure rate spike?
   - Which stage has high p95 latency?
   - Queue depth growing on `stage.stt`, `stage.nmt`, `stage.tts`, or `stage.merge`?

4. **Inspect the trace** (if sampled): Grafana → Explore → Tempo → search by `job_id` tag, or click **TraceID** from a correlated log line.

5. **Check RabbitMQ** at `https://rabbitmq.$DOMAIN`:
   - Queue depth on stage queues
   - **orchestrator.dlq** for poison messages (unparseable payloads, permanent handler errors)

6. **DLQ recovery:** inspect the message in RabbitMQ UI → orchestrator.dlq → get payload → fix root cause → re-publish or delete after fixing data.

7. **Fallback (SSH):** if Grafana is down:
   ```bash
   docker compose -f docker-compose.microservices.prod.yml -f docker-compose.observability.yml logs --tail=200 orchestrator stt-service nmt-service tts-service media-service backend
   ```

### Common pipeline failure patterns

| Symptom | Likely cause | Where to look |
|---------|--------------|---------------|
| Job stuck in `QUEUED` | Worker not consuming / queue backlog | Pipeline dashboard queue depth; worker `/readiness` |
| Job `FAILED` at STT | Audio missing, model error, S3 download | `{service="stt"} \|= "job_id"` |
| Job `FAILED` at NMT/TTS | GPU OOM, model load failure | Infra dashboard container memory; worker logs |
| DLQ messages | Poison JSON or permanent orchestrator error | `orchestrator.dlq` in RabbitMQ; orchestrator logs |
| High failure rate alert | Upstream API or storage outage | Backend logs + S3 connectivity |

---

## Log Locations

### Microservices production (current)

| Component | Location | Notes |
|-----------|----------|-------|
| All services | Grafana → Loki | JSON stdout via Promtail; search by `job_id` |
| Backend API | stdout + optional `backend/logs/` | `LOG_JSON_FORMAT=true` |
| Orchestrator | stdout | JSON slog with `parent_job_id` / `child_job_id` |
| AI workers | stdout | JSON via `dablja_worker.logging` |
| Caddy | stdout | JSON access logs |
| Deploy script | `~/web/deploy.log` on VM | GitHub Actions deploy output |

**Without Grafana (SSH fallback):**
```bash
docker compose -f docker-compose.microservices.prod.yml logs -f --tail=100 orchestrator backend stt-service
```

### Legacy Celery stack

| Component | Location | Notes |
|-----------|----------|-------|
| Backend API | `backend/logs/` + stdout | `shared/logging.py` config |
| Media Worker | `docker compose logs worker-media` | Celery task output |
| Pipeline Worker | `docker compose logs worker-pipeline` | AI task output |
| PostgreSQL | `docker compose logs postgres` | Query errors |
| Redis | `docker compose logs redis` | Connection issues |
| Flower | `docker compose logs flower` | Monitoring UI |

**Tail all logs (legacy):**
```bash
docker compose logs -f --tail=100
```

**Filter by service (legacy):**
```bash
docker compose logs -f worker-media worker-pipeline
```

---

## Monitoring

### Microservices (Grafana LGTM)

See [docs/observability.md](observability.md). Dashboards: **Pipeline**, **Infrastructure**, **Logs Explorer**.

### Legacy: Flower

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
