# RabbitMQ-Native Python Workers

## Architecture Overview

The Go orchestrator (`orchestrator/`) is a pipeline state machine that
coordinates the dubbing workflow using RabbitMQ events. It publishes
messages to routing keys like `job.start.stt` and listens for results
on `job.results.*`.

These Python workers are the **actual AI workers** that the orchestrator
talks to. Each worker:

1. **Connects** to RabbitMQ and declares the same `dablja.jobs.exchange`
   topic exchange that the orchestrator uses.
2. **Consumes** messages from a specific `job.start.*` routing key.
3. **Processes** the AI work (transcription, translation, synthesis, merge).
4. **Publishes** results back to `job.results.*` in the format the
   orchestrator expects.

```
┌─────────────────┐     RabbitMQ      ┌──────────────────┐
│                 │  job.start.stt    │                  │
│  Go             │ ─────────────────► │  STT Worker      │
│  Orchestrator   │                    │  (Whisper)       │
│  (state machine)│ ◄───────────────── │                  │
│                 │  job.results.stt   └──────────────────┘
│                 │
│                 │  job.start.nmt    ┌──────────────────┐
│                 │ ─────────────────► │  NMT Worker      │
│                 │                    │  (NLLB-200)      │
│                 │ ◄───────────────── │                  │
│                 │  job.results.nmt   └──────────────────┘
│                 │
│                 │  job.start.tts    ┌──────────────────┐
│                 │ ─────────────────► │  TTS Worker      │
│                 │                    │  (SILMA-TTS)     │
│                 │ ◄───────────────── │                  │
│                 │  job.results.tts   └──────────────────┘
│                 │
│                 │  job.start.merge  ┌──────────────────┐
│                 │ ─────────────────► │  Merge Worker    │
│                 │                    │  (ffmpeg)        │
│                 │ ◄───────────────── │                  │
│                 │  job.results.merge └──────────────────┘
└─────────────────┘
```

### Worker Framework vs. Individual Workers

The codebase is split into two layers:

**Framework layer** (`__init__.py`, `types.py`, `registry.py`,
`connection.py`, `base_worker.py`, `cli.py`, `_db.py`):
Reusable components that any worker can use. Handles RabbitMQ
connections, message serialization, handler registration, database
access, and the consume-ack-publish lifecycle.

**Individual workers** (`stt_worker.py`, `nmt_worker.py`,
`tts_worker.py`, `merge_worker.py`):
Each contains a single async handler function decorated with `@register`,
plus a `create_worker()` factory function. The handler does one stage
of the pipeline and returns a dict with the output data.

---

## The Happy Path (end-to-end)

Here's what happens when a user uploads a video and requests dubbing:

### Step 1: FastAPI creates a pipeline job

The backend creates a `FULL_DUBBING_PIPELINE` job row in PostgreSQL with
`input_data` containing `video_id`, `source_lang`, `target_lang`, etc.
It then publishes `{"job_id": "<pipeline_id>"}` to routing key
`job.created` on the `dablja.jobs.exchange`.

### Step 2: Orchestrator starts the pipeline

The Go orchestrator receives the `job.created` message in its
`handleNewJob` handler. It marks the pipeline job as `PROCESSING` in
the DB and publishes `{"job_id": "<pipeline_id>"}` to `job.start.stt`.

### Step 3: STT Worker transcribes the audio

The STT worker consumes from `job.start.stt`. Its handler does:

1. **Load the pipeline job** from PostgreSQL via `load_job()` to get
   `video_id`, `source_lang`, etc.
2. **Create a child job** via `create_child_job()` — a new `STT_TRANSCRIBE`
   row in the `jobs` table. This is the job that the orchestrator will
   later look up to determine the next stage.
3. **Download the audio file** from MinIO (S3-compatible storage).
4. **Run Whisper transcription** via `WhisperModelManager.model.transcribe()`.
5. **Store the result** in the child job's `output_data` column via
   `update_job_output()`.
6. **Return** a dict with `_result_job_id` set to the child job's UUID.

The `BaseWorker._process_message()` method then:
- Strips `_result_job_id` from the output dict.
- Publishes `WorkerResultPayload` with `job_id=stt_child_job_id` to
  `job.results.stt`.
- Acks the RabbitMQ message.

### Step 4: Orchestrator advances to NMT

The orchestrator receives `job.results.stt`, looks up the STT child job,
stores its `output_data` in the DB, sees that `JobType == STT_TRANSCRIBE`,
and publishes `{"job_id": "<stt_child_id>"}` to `job.start.nmt`.

### Step 5: NMT Worker translates

The NMT worker consumes from `job.start.nmt`. Its handler:

1. Loads the STT job (received `job_id`), extracts segments from its
   `output_data`.
2. Creates an `NMT_TRANSLATE` child job.
3. Translates each segment via `NLLBTranslatorWrapper._translate_item()`,
   run in a thread via `asyncio.to_thread()` to avoid blocking.
4. Optionally applies Groq-based length adjustment.
5. Stores result and returns with `_result_job_id` = NMT child job ID.

### Step 6: Orchestrator advances to TTS

Same pattern — receives `job.results.nmt`, publishes `job.start.tts`.

### Step 7: TTS Worker synthesizes speech

The TTS worker consumes from `job.start.tts`. Its handler:

1. Loads the NMT job's output_data (translated segments).
2. Creates a `TTS_SYNTHESIZE` child job.
3. For each segment, calls `synthesize_tts.run()` (SILMA-TTS) and
   uploads the audio WAV to MinIO.
4. Records per-segment success/failure (individual segments can fail
   without crashing the whole stage).
5. Stores combined result and returns with `_result_job_id`.

### Step 8: Orchestrator advances to Merge

Receives `job.results.tts`, publishes `job.start.merge`.

### Step 9: Merge Worker assembles the final video

The merge worker consumes from `job.start.merge`. Its handler:

1. Loads the TTS job's output_data (audio keys).
2. Filters out failed segments.
3. Creates a `DUBBING_MERGE` child job.
4. Runs `DubbingMergeService.merge_segments()` to time-stretch,
   concatenate, and mux audio with the original video.
5. Updates the `videos` table with `dubbed_video_path`.
6. Returns result with `_result_job_id`.

### Step 10: Orchestrator marks the pipeline complete

Receives `job.results.merge`, sees `JobType == DUBBING_MERGE` has no
next stage in `nextStageRoutes`, and marks the parent
`FULL_DUBBING_PIPELINE` job as `COMPLETED`.

---

## File-by-File Code Walkthrough

### `types.py` — Payload Types

```python
@dataclass
class WorkerResultPayload:
    job_id: str
    job_type: str       # e.g. "STT_TRANSCRIBE"
    status: str         # "COMPLETED" or "FAILED"
    output_data: dict   # stage-specific result data
    error: str          # error message if FAILED
```

This must **exactly match** the Go struct in
`orchestrator/internal/pipeline/manager.go`:

```go
type WorkerResultPayload struct {
    JobID      string         `json:"job_id"`
    JobType    string         `json:"job_type"`
    Status     string         `json:"status"`
    OutputData map[string]any `json:"output_data"`
    Error      string         `json:"error,omitempty"`
}
```

`to_bytes()` serialises to JSON bytes for publishing over RabbitMQ.

`NewJobPayload` is the incoming message format: just `{"job_id": "..."}`.

### `registry.py` — Task Registration

A lightweight alternative to Celery's `@app.task` decorator:

```python
@register(
    routing_key="job.start.stt",
    result_key="job.results.stt",
    job_type="STT_TRANSCRIBE",
)
async def handle_stt(job_id: str) -> dict:
    ...
```

- `register()` stores a `TaskHandler` dataclass in a module-level dict.
- It validates that the handler is `async def` (rejects sync functions).
- `get_handler()`, `list_handlers()`, `get_routing_keys()` provide
  introspection.

The registry is **optional** — the `BaseWorker` uses its own internal
`_handlers` dict via `register_handler()`. The global registry exists
so that handlers can be discovered programmatically (e.g., for CLI help
or health checks).

### `connection.py` — RabbitMQ Connection Manager

Wraps `aio-pika`'s `connect_robust()` for automatic reconnection.

**Key responsibilities:**
- `connect()`: Opens a channel, sets QoS prefetch=1 (fair dispatch),
  declares `dablja.jobs.exchange` (topic, durable) and
  `dablja.jobs.dlx` (dead-letter, direct).
- `publish()`: Sends a JSON message to the exchange with a given
  routing key. Messages are marked `PERSISTENT` (survive broker restart).
- `close()`: Cleanly tears down channel and connection.

**Why not use Celery/Kombu?** Celery's consumer API is tightly coupled
to Redis broker semantics. These workers need direct AMQP control to
bind to the same exchange the Go orchestrator uses, with specific
routing keys and dead-letter configuration.

### `base_worker.py` — The Core Worker Loop

`BaseWorker` is the heart of the framework. Here's how it works:

**Constructor:**
```python
worker = BaseWorker(
    rabbitmq_url="amqp://...",
    concurrency=1,       # max in-flight messages
    worker_name="stt",   # used for queue naming
)
```

**`start()`:**
1. Connects to RabbitMQ via `RabbitMQConnection`.
2. For each registered handler, declares a durable queue named
   `worker.{name}.{routing_key}` and binds it to the exchange.
3. Starts consuming with manual ack (`no_ack=False`).
4. Registers SIGINT/SIGTERM handlers for graceful shutdown.
5. Blocks on `_shutdown_event.wait()` until `stop()` is called.

**`_process_message()` — the message lifecycle:**

```
RabbitMQ message arrives
  → acquire semaphore (limits concurrency)
  → parse JSON body
  → call handler.fn(job_id)
  → on success:
      strip _result_job_id from output
      publish WorkerResultPayload(status=COMPLETED)
      ack message
  → on JSON decode error:
      ack and discard (poison message)
  → on handler exception:
      publish WorkerResultPayload(status=FAILED)
      reject message (no requeue — goes to DLQ)
  → release semaphore
```

**The `_result_job_id` pattern:**

When a handler creates a child job (e.g., the STT worker creates an
`STT_TRANSCRIBE` child), the orchestrator needs to receive the child
job's ID, not the parent's. The handler returns:

```python
return {
    "_result_job_id": stt_child_job_id,  # ← overrides publish job_id
    "transcript": "...",
    "segments": [...],
}
```

`_process_message()` pops `_result_job_id` from the dict, uses it as
`job_id` in the published `WorkerResultPayload`, and excludes it from
the `output_data`. The orchestrator then looks up the child job,
determines its `JobType`, and advances the pipeline.

### `_db.py` — Database Helpers

All DB access in workers uses **sync psycopg2 + NullPool** (NOT asyncpg),
because:
- Workers are not FastAPI processes — they don't share an event loop.
- SQLAlchemy's async engine (asyncpg) crashes in worker processes with
  "another operation is in progress".
- This is the **same pattern** used by the existing Celery workers in
  `BaseJobTask._make_db()`.

**Key functions:**

| Function | Purpose |
|----------|---------|
| `load_job(job_id)` | Load a job row from DB, return as plain dict |
| `update_job_output(job_id, data, status, error)` | Update a job's output_data and status |
| `create_child_job(parent_id, job_type, input_data)` | Create a child job inheriting user_id/video_id |
| `get_video_file_key(video_id)` | Get audio/file path for a video |

`create_child_job()` is critical — it creates the stage-level job row
that the orchestrator uses to determine job type and advance the pipeline:

```python
child = Job(
    id=new_id,
    parent_job_id=parent_job_id,
    job_type=resolved_type,    # e.g. STT_TRANSCRIBE
    status=QUEUED,
    user_id=parent.user_id,
    video_id=parent.video_id,
    input_data={...},          # merged with parent's input_data
)
```

The module also imports `app.media.models.Video` at import time to
ensure SQLAlchemy's mapper can resolve the foreign key from
`jobs.video_id` to `videos.id`. This is a hard requirement documented
in `AGENTS.md`.

### `cli.py` — CLI Entry Point

The CLI is invoked as `python -m app.worker.run <type>`.

```bash
python -m app.worker.run stt    # STT worker (concurrency=1)
python -m app.worker.run nmt    # NMT worker (concurrency=2)
python -m app.worker.run tts    # TTS worker (concurrency=1)
python -m app.worker.run merge  # Merge worker (concurrency=2)
```

**What it does:**

1. **Configures the device** via `_configure_device()` — sets
   `CUDA_VISIBLE_DEVICES` based on `SILMA_DEVICE` setting, mirroring
   the same logic in `celery_app.py`. This must happen before any AI
   library imports torch.
2. **Imports the worker module** dynamically via `importlib`.
3. **Calls `create_worker(url, concurrency)`** to build the worker.
4. **Starts the asyncio event loop** with `asyncio.run(worker.start())`.

### `stt_worker.py` — STT Worker

**Consumes:** `job.start.stt`
**Publishes:** `job.results.stt`
**Child job type:** `STT_TRANSCRIBE`

The handler receives the `FULL_DUBBING_PIPELINE` job ID. It:

1. Loads the pipeline job from DB (not a child — this is the top-level job).
2. Creates an `STT_TRANSCRIBE` child job.
3. Downloads the audio file from MinIO (uses `asyncio.new_event_loop()`
   + `run_until_complete()` for the async S3 call, same pattern as the
   existing Celery workers).
4. Runs Whisper transcription via `WhisperModelManager`.
5. On error: updates the child job as FAILED and **re-raises** — the
   `BaseWorker` catches this and publishes a FAILED result.

```python
# Key pattern: child job creation + _result_job_id
stt_job_id = create_child_job(job_id, "STT_TRANSCRIBE", ...)
# ... do work ...
output = {
    "_result_job_id": stt_job_id,
    "transcript": full_transcript,
    "segments": structured_segments,
}
return output
```

### `nmt_worker.py` — NMT Worker

**Consumes:** `job.start.nmt` (receives STT child job ID)
**Publishes:** `job.results.nmt`
**Child job type:** `NMT_TRANSLATE`

Translates all segments sequentially using NLLB-200. Each segment
translation runs in a thread via `asyncio.to_thread()` to avoid blocking
the event loop.

**Length adjustment:** When `NMT_LENGTH_ADJUST_ENABLED` is true, calls
`adjust_ar()` (Groq API) to shorten/rephrase Arabic translations so
they fit the original audio duration. Falls back gracefully if Groq
fails.

**Error handling:** Per-segment translation failures fall back to the
original text — a single bad segment doesn't fail the whole job.

### `tts_worker.py` — TTS Worker

**Consumes:** `job.start.tts` (receives NMT child job ID)
**Publishes:** `job.results.tts`
**Child job type:** `TTS_SYNTHESIZE`

Synthesizes each translated segment using SILMA-TTS:

```python
result = synthesize_tts.run(
    text=translated_text.strip(),
    ref_audio_path=ref_audio,
    job_id=f"{tts_job_id}_seg_{segment_id}",
    upload_to_minio=True,
    minio_key=f"tts/{tts_job_id}/segment_{segment_id}.wav",
)
```

Each segment synthesis runs in a thread. Individual failures are recorded
per-segment without failing the whole job:

```python
result_segments.append({
    ...
    "tts_key": synth_result.get("minio_key"),
    "audio_url": synth_result.get("audio_url"),
    # or on failure:
    "tts_error": str(exc),
})
```

The segment that failed is reported in `metadata.failed`.

### `merge_worker.py` — Merge Worker

**Consumes:** `job.start.merge` (receives TTS child job ID)
**Publishes:** `job.results.merge`
**Child job type:** `DUBBING_MERGE`

The final stage. It:

1. Filters to segments with valid TTS audio (`tts_key` present, no
   `tts_error`). If no valid segments exist, returns a FAILED result
   rather than crashing.
2. Builds `SegmentTimingInfo` objects with precise start/end/duration.
3. Calls `DubbingMergeService.merge_segments()` to:
   - Download all TTS WAVs from MinIO.
   - Time-stretch each segment with FFmpeg `atempo` filter.
   - Concatenate with silence gaps.
   - Replace original video audio with the dubbed track.
4. Updates the `videos` table's `dubbed_video_path` and
   `dubbing_metadata` columns so the API can serve the result.

---

## Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| Handler raises exception | `BaseWorker` publishes `FAILED` result, rejects message (→ DLQ) |
| Bad JSON message | Acknowledged and discarded (poison message) |
| Individual segment fails (TTS/NMT) | Recorded per-segment with `tts_error`; other segments continue |
| No valid segments (merge) | Returns FAILED result, does not crash |
| Missing job in DB | Handler raises `ValueError` → base worker publishes FAILED |
| RabbitMQ connection lost | `aio-pika` `connect_robust()` auto-reconnects; messages wait in queue |

The Go orchestrator handles retry logic at the pipeline level: if a
stage fails, the parent pipeline job is marked FAILED and won't advance.
Future enhancement: the orchestrator could re-publish `job.start.*`
with a retry count.

---

## Database Access Pattern

Workers use sync SQLAlchemy with psycopg2 + NullPool:

```python
def _make_engine():
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, poolclass=NullPool)
    return engine, sessionmaker(bind=engine)
```

Every database operation:
1. Creates a fresh engine + session.
2. Does the work.
3. Disposes the engine in `finally`.

This avoids connection pool leaks and asyncpg incompatibility. The
NullPool means every operation opens/closes a connection — acceptable
for worker processes that handle a few concurrent jobs.

---

## Configuration

| Env Var | Default | Used By |
|---------|---------|---------|
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | All workers |
| `DATABASE_URL` | (from settings) | All workers |
| `SILMA_DEVICE` | `auto` | TTS worker |
| `NMT_LENGTH_ADJUST_ENABLED` | `true` | NMT worker |
| `GROQ_API_KEY` | — | NMT worker (length adjust) |

---

## Running the Workers

### With Docker Compose

```bash
docker compose up -d worker-stt worker-nmt worker-tts worker-merge
```

Each worker is a separate container, independently scalable:

```yaml
worker-stt:   # concurrency=1 (GPU-bound Whisper)
worker-nmt:   # concurrency=2
worker-tts:   # concurrency=1 (GPU-bound SILMA)
worker-merge: # concurrency=2 (ffmpeg, CPU)
```

### Manually

```bash
# STT worker
python -m app.worker.run stt --concurrency 1 --log-level DEBU
G
# NMT worker with custom RMQ
python -m app.worker.run nmt --rabbitmq-url "amqp://user:pass@host:5672/"
```

---

## Comparison with Celery Workers

| Aspect | Celery Workers | RabbitMQ Workers |
|--------|---------------|------------------|
| **Broker** | Redis | RabbitMQ |
| **Task definition** | `@celery_app.task(...)` | `@register(...)` |
| **Result backend** | Redis | PostgreSQL (via orchestrator) |
| **Concurrency control** | `--pool=solo`, `--concurrency` | asyncio `Semaphore` |
| **Retry** | `max_retries`, `default_retry_delay` | Orchestrator manages retry |
| **Pipeline orchestration** | Celery chords/canvases | Go orchestrator state machine |
| **Queue naming** | Celery task routes | Queue per handler per worker |
| **Serialization** | JSON | JSON |

The RabbitMQ workers are designed to coexist with the existing Celery
workers — both share the same `jobs` table. You can migrate stage by
stage.

---

## Testing

### 1. Unit Tests (fast, no infrastructure needed)

Unit tests mock all external dependencies (DB, RabbitMQ, AI models, MinIO).
They live in `tests/worker/` and run without any infrastructure.

```bash
# All worker unit tests
pytest tests/worker/ -v

# Single file
pytest tests/worker/test_stt_worker.py -v

# With coverage
pytest tests/worker/ --cov=app.worker --cov-report=term
```

**Status: 67 tests, all pass.**

Go orchestrator unit tests also exist in `orchestrator/internal/pipeline/`:

```bash
cd orchestrator && go test ./... -v -count=1
```

---

### 2. Integration Tests (need real RabbitMQ + PostgreSQL)

Integration tests validate the orchestrator state machine and worker DB
helpers against **real infrastructure**. They are guarded behind the
`--run-integration` flag.

**Files:**
- `tests/integration/test_orchestrator.py` — drives the orchestrator through
  all 4 pipeline stages via real RabbitMQ messages, acting as a fake AI
  worker. Asserts every stage fires in order and the parent job completes.
- `tests/integration/test_worker_db.py` — exercises `_db.py` helpers
  (`load_job`, `create_child_job`, `update_job_output`, `get_video_file_key`)
  against a real PostgreSQL database.

**How to run (automatic — starts/tears down infrastructure):**

```bash
cd ~/dabljaAR/web
./backend/run_integration_tests.sh

# Options:
#   --skip-build         reuse existing Docker images
#   --orchestrator-only  only the state machine test
#   --worker-db-only     only the DB helper test
```

What the script does:
1. Starts `docker compose -f docker-compose.test.yml up -d` (PostgreSQL,
   RabbitMQ, MinIO, Redis, orchestrator, backend)
2. Waits for the orchestrator health endpoint to return OK
3. Runs `pytest --run-integration tests/integration/`
4. Prompts to keep or tear down the infrastructure

---

### 3. Full End-to-End Pipeline Test (manual)

To test the complete STT → NMT → TTS → Merge flow with real AI models:

```bash
# 1. Start the full stack
docker compose up -d orchestrator worker-stt worker-nmt worker-tts worker-merge backend

# 2. Check everything is healthy
curl -s http://localhost:8081/health | jq .
# → {"status":"ok","checks":{"database":"healthy","rabbitmq":"healthy"}}

# 3. Upload a test audio file (requires JWT token)
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"...","password":"..."}' | jq -r '.access_token')

curl -X POST "http://localhost:8000/api/videos/upload/audio" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_sample.mp3"

# 4. Watch the pipeline flow in real-time
docker compose logs -f orchestrator worker-stt worker-nmt worker-tts worker-merge

# 5. Poll the pipeline job status
curl -s "http://localhost:8000/api/dubbing/jobs/$PIPELINE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq

# 6. Get the final dubbed video URL
curl -s "http://localhost:8000/api/dubbing/videos/$VIDEO_ID/dubbed" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.dubbed_video_url'
```

---

### 4. Full Pipeline Automation: `verify_pipeline.sh`

A convenience script that checks all services are running, workers are
registered, and TTS reference audio is found:

```bash
./backend/verify_pipeline.sh
```
