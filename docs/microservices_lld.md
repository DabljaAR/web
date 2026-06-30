# DabljaAR — Microservices Low-Level Design

> **Status:** Phase 2 Complete — microservices pipeline live in dev and prod compose  
> **Last updated:** June 2026  
> **Phase 1 scope:** Full-app LLD + STT/NMT validation  
> **Companion doc:** [microservices_migration.md](microservices_migration.md)

---

## Table of Contents

1. [Phase overview](#1-phase-overview)
2. [System topology](#2-system-topology)
3. [Repository layout](#3-repository-layout)
4. [Python worker pattern](#4-python-worker-pattern)
5. [Shared worker library](#5-shared-worker-library-libsdablja-worker)
6. [Service specs](#6-service-specs)
   - 6.1 [orchestrator (Go)](#61-orchestrator-go)
   - 6.2 [stt-service](#62-stt-service)
   - 6.3 [nmt-service](#63-nmt-service)
   - 6.4 [tts-service](#64-tts-service)
   - 6.5 [media-service merge stage](#65-media-service-merge-stage)
   - 6.6 [backend](#66-backend)
7. [Messaging topology](#7-messaging-topology)
8. [Data flow per output_type](#8-data-flow-per-output_type)
9. [Cancellation, retries, idempotency](#9-cancellation-retries-idempotency)
10. [DB ownership (Phase 1–2)](#10-db-ownership-phase-12-shared-db)
11. [Design patterns catalog](#11-design-patterns-catalog)
12. [Testing strategy](#12-testing-strategy)
13. [Phase 1 exit criteria](#13-phase-1-exit-criteria)
14. [Phase 2 preview](#14-phase-2-preview)
15. [Production deployment](#15-production-deployment)

---

## 1. Phase overview

| Phase | Goal | In scope | Not in scope |
|-------|------|----------|--------------|
| **Phase 1 (done)** | Freeze full-app LLD; validate STT + NMT | Shared lib, STT/NMT hardening, test infra | TTS service, merge worker, Celery removal |
| **Phase 2 (active)** | TTS + merge + Celery cutover | `tts-service`, `media-service` merge stage, orchestrator merge stage, prod compose | K8s, Phase 3 DB ownership |

Phase 2 cutover: `fullDubbing` and `translationAndTTS` run through `tts-service` (port 8005) and `media-service` merge worker (port 8003). The Celery `tts_bridge.py` shim has been removed.

---

## 2. System topology

```
frontend ──REST──▶ backend ──job.created──▶ RabbitMQ
                   │                           │
                   └──media BackgroundTask      │
                                           ▼
                                       orchestrator (Go)
                                       ┌────────────────────┐
                            ┌──────────┤ saga state machine  │
                            │          └────────────────────┘
                       job.start.*              │
         ┌─────────┬─────────┬─────────┐       │ job.results.*
    stt-service  nmt-service  tts-service      │
    (port 8001)  (port 8002)  (port 8005)      │
         │           │           │              │
        DB+S3       DB+S3       DB+S3           │
                              media-service (merge, port 8003)
                                   DB+S3+ffmpeg
```

All inter-stage pipeline communication goes through **RabbitMQ** topic exchange `dablja.jobs.exchange`. No stage-to-stage HTTP. The orchestrator is the only component that knows pipeline order.

---

## 3. Repository layout

```
web/
├── libs/
│   └── dablja-worker/                   # Phase 1: shared installable Python package
│       ├── pyproject.toml               # name="dablja-worker", package="dablja_worker"
│       └── dablja_worker/
│           ├── __init__.py              # re-exports: consume_loop, make_engine, …
│           ├── consumer.py              # AMQP consumer loop, engine factory, failure classifier
│           ├── job_state.py             # mark_processing/completed/failed (raw SQL helpers)
│           └── results.py              # publish_result (WorkerResultPayload contract)
├── orchestrator/                        # Go saga coordinator
│   ├── cmd/server/main.go
│   └── internal/
│       ├── db/db.go                     # Job, JobType, JobStatus, ConnectDB
│       ├── health/health.go             # /health /readiness HTTP server
│       ├── mq/rabbitmq.go               # RabbitMQ dial, exchange declare
│       └── pipeline/
│           ├── manager.go               # state machine: handleNewJob, handleResult, publishNextJob
│           ├── manager_test.go          # unit: JSON contracts, enum parity
│           ├── manager_nextstage_test.go # unit: nextStage() for all output_types
│           ├── manager_integration_test.go      # integration: T01–T15
│           └── manager_stt_integration_test.go  # integration: fake STT worker
├── stt-service/                         # Phase 1: validate + harden
│   ├── Dockerfile  Dockerfile.gpu
│   ├── requirements.txt                 # fastapi, uvicorn, pika, faster-whisper, sqlalchemy, boto3
│   ├── pytest.ini
│   ├── tests/
│   │   ├── conftest.py
│   │   └── test_worker.py               # Phase 1: unit tests (no infra)
│   └── app/
│       ├── main.py                      # FastAPI lifespan → consumer daemon; /health /readiness
│       ├── config.py                    # pydantic Settings (RabbitMQ, DB, S3, model, PORT=8001)
│       ├── worker.py                    # consume stage.stt → transcribe → job.results.stt
│       ├── model.py                     # WhisperModelManager (lazy singleton, S3/HF cache)
│       ├── storage.py                   # S3 download for audio
│       └── transcribe.py               # sync POST /transcribe, GET /health/model
├── nmt-service/                         # Phase 1: validate + harden
│   ├── Dockerfile
│   ├── requirements.txt                 # + transformers, sentencepiece, langdetect, groq
│   ├── pytest.ini
│   ├── tests/
│   │   ├── conftest.py
│   │   └── test_worker_logic.py         # Phase 1: unit tests (no infra)
│   └── app/
│       ├── main.py                      # FastAPI lifespan → consumer daemon; /health /readiness
│       ├── config.py                    # pydantic Settings (NMT model, Groq, concurrency, PORT=8002)
│       ├── worker.py                    # consume stage.nmt → translate → job.results.nmt
│       ├── model.py                     # NLLBTranslatorWrapper (lazy singleton)
│       ├── length_adjuster.py          # Groq Arabic length adjustment (optional)
│       └── translate.py                # sync POST /translate, GET /health/model
├── tts-service/                         # Phase 2: SILMA TTS + audio combine (port 8005)
├── media-service/                       # Phase 2: merge stage + auxiliary media HTTP (port 8003)
│   ├── Dockerfile  Dockerfile.gpu
│   ├── requirements-base.txt
│   ├── pytest.ini
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_worker_logic.py
│   │   └── test_mux.py
│   └── app/
│       ├── main.py                      # FastAPI lifespan → merge consumer; /health /readiness
│       ├── config.py
│       ├── worker.py                    # consume stage.merge → mux → job.results.merge
│       ├── mux.py                       # ffmpeg replace-audio (from backend DubbingMergeService)
│       ├── storage.py
│       └── ffmpeg.py
├── backend/                             # FastAPI monolith (auth, media preprocess, job creation, status)
│   └── app/
│       ├── media/service.py            # publish_job_created() after media preprocess
│       └── dubbing/service.py          # legacy merge logic (reference only; merge lives in media-service)
├── docker-compose.yml                   # dev stack (all services)
├── docker-compose.test.yml             # Phase 1: test infra (no AI model volumes)
└── docs/
    ├── microservices_lld.md            # this file
    └── microservices_migration.md      # original migration design doc
```

---

## 4. Python worker pattern

Every AI worker service (stt, nmt, tts, merge) follows the same **dual-role single process** pattern:

```
One Python process
├── Main thread:   uvicorn + FastAPI  →  /health, /readiness, optional sync API
└── Daemon thread: pika BlockingConnection  →  AMQP consumer loop
```

The FastAPI `lifespan` hook starts the daemon consumer thread. The thread runs `consume_loop()` from the shared library, which handles reconnects, exchange/queue declares, and QoS.

**DB access in workers:** Sync SQLAlchemy Core — `text()` raw SQL only. No ORM entities. Engine is a module-level singleton created by `make_engine()`.

**Config:** `pydantic_settings.BaseSettings` reading from env vars (no secrets baked into images).

**Model loading:** class-level singleton + `threading.Lock`, lazy on first inference. Resolution chain: local `/model-cache` volume → S3 prefix download → HuggingFace Hub fallback.

### Health endpoints

| Endpoint | HTTP code | Checks |
|----------|-----------|--------|
| `GET /health` | 200 always | Process is alive |
| `GET /readiness` | 200 / 503 | Consumer daemon thread is alive |
| `GET /health/model` | 200 / 503 | Model singleton loaded |

Docker healthcheck: `curl -f http://localhost:{PORT}/readiness`

### Consumer message flow

```python
def on_message(channel, method, _properties, body):
    # 1. Parse JSON — ack and discard if malformed
    # 2. Check cancelled (DB) — ack silently if CANCELLED
    #    Transient DB error → nack(requeue=True)
    # 3. Start cancel-watcher daemon (NMT/TTS only — long jobs)
    # 4. process_job(job_id)
    #    a. Load job from DB; skip if already COMPLETED (idempotency §10.3)
    #    b. mark_processing
    #    c. Run inference (download S3 / translate / synthesize)
    #    d. Write result to video_tasks + mark_completed
    # 5. publish_result(COMPLETED, lean summary)
    # 6. ack
    # On exception → mark_failed + publish_result(FAILED) → ack
    # On cancel mid-job → ack silently (no FAILED publish)
```

**Critical:** `basic_ack` is always called exactly once — after `publish_result`. Nacks (requeue=True) only occur for transient infrastructure failures during the cancel-check DB read. Failures during inference are reported as result messages (status: FAILED) and then acked, not nacked.

---

## 5. Shared worker library (`libs/dablja-worker`)

Replaces the triplicated `dablja_worker.py` files in stt-service, nmt-service, and backend.

### Package structure

```
libs/dablja-worker/
├── pyproject.toml
└── dablja_worker/
    ├── __init__.py      # re-exports all public symbols
    ├── consumer.py      # consume_loop, make_engine, classify_failure, check_cancelled
    ├── job_state.py     # mark_processing, mark_completed, mark_failed, is_completed
    └── results.py       # publish_result (WorkerResultPayload shape)
```

### `consumer.py`

- `make_engine(database_url)` — cached `(engine, SessionLocal)` pair, pool_pre_ping=True
- `classify_failure(exc)` → `"transient" | "permanent"` — AMQP/DB/IO errors are transient
- `check_cancelled(db, job_id)` → `bool` — reads `jobs.status`
- `consume_loop(rabbitmq_url, queue, binding_key, exchange, on_message, ...)` — blocking loop with exponential backoff reconnect

### `job_state.py`

Raw SQL helpers for common job lifecycle transitions (no ORM imports):

```python
mark_processing(db, job_id: str) -> None
mark_completed(db, job_id: str, output_data: dict) -> None
mark_failed(db, job_id: str, error: str) -> None
is_completed(db, job_id: str) -> bool
```

### `results.py`

```python
def publish_result(
    channel,
    routing_key: str,
    job_id: str,
    job_type: str,
    status: str,           # "COMPLETED" | "FAILED"
    output_data: dict = None,
    error: str = None,
) -> None
```

Publishes `WorkerResultPayload` matching the Go orchestrator contract (persistent, `content_type=application/json`).

### Adoption

- **Phase 1:** stt-service and nmt-service install from `libs/dablja-worker`. Local `app/dablja_worker.py` files removed. Import changes from `from app.dablja_worker import` to `from dablja_worker import`.
- **Phase 2:** tts-service and media-service use `job_state.py` and `results.py` from the start.

### Docker build integration

```yaml
# docker-compose.yml (stt-service and nmt-service)
build:
  context: ./stt-service
  additional_contexts:
    shared: ./libs/dablja-worker
```

```dockerfile
# In each service Dockerfile:
COPY --from=shared . /tmp/dablja-worker
RUN pip install --no-cache-dir /tmp/dablja-worker
```

---

## 6. Service specs

### 6.1 orchestrator (Go)

**Location:** `orchestrator/`  
**Purpose:** Pipeline saga coordinator — the only component that knows stage order.

#### State machine

| Event | Action |
|-------|--------|
| `job.created` | Mark parent PROCESSING; resolve `output_type`; create first child job (STT); publish `job.start.stt` |
| `job.results.X COMPLETED` | Re-check cancel; resolve next stage; create next child; publish `job.start.next`; if no next → mark parent COMPLETED at 100% |
| `job.results.X FAILED` | Mark child FAILED; mark parent FAILED |
| `job.results.X RETRYING/CANCELLED` | No action |

#### Stage sequences (`stageOrder` in `manager.go`)

| `output_type` | Stages (all via RabbitMQ) |
|---------------|---------------------------|
| `uploadOnly` | (none — complete immediately) |
| `captionsOnly` | STT → done |
| `captionsAndTranslation` | STT → NMT → done |
| `translationAndTTS` | STT → NMT → TTS → done |
| `fullDubbing` | STT → NMT → TTS → merge → done |

#### Child job creation

The orchestrator creates each child job before publishing `job.start.X`. The child has:
- `parent_job_id` = pipeline job UUID
- `job_type` = stage job type (STT_TRANSCRIBE, NMT_TRANSLATE, etc.)
- `input_data` = copied from parent (contains `video_id`, `task_id`, `output_type`, etc.)
- `status` = QUEUED, `max_retries` = 3

Workers receive only `{"job_id": "<child_uuid>"}` — they load all inputs from DB (Claim Check).

#### Duplicate prevention

On `job.created`, if a child for `parent + firstStage` already exists:
- QUEUED/PROCESSING/RETRYING → re-publish dispatch (original message may have been lost)
- COMPLETED → skip (already done)
- FAILED → create new child for retry
- CANCELLED → skip

Same logic applies when advancing to next stage.

#### Orchestrator health

- `/health` (port 8081): liveness — returns 200 when the HTTP server responds (process alive)
- `/readiness`: DB ping + RabbitMQ connected + pipeline consumers started → 200 / 503

Docker healthcheck: `curl -f http://localhost:8081/readiness`

#### Key files

- `orchestrator/internal/pipeline/manager.go` — state machine
- `orchestrator/internal/db/db.go` — GORM models: `Job`, `JobType`, `JobStatus`; `CeleryTaskID` field is legacy/bridge, not used by orchestrator
- `orchestrator/internal/mq/rabbitmq.go` — RabbitMQ dial, exchange declare
- `orchestrator/internal/health/health.go` — HTTP health server

---

### 6.2 stt-service

**Location:** `stt-service/`  
**Port:** 8001  
**Queue:** `stage.stt` (binding key: `job.start.stt`)  
**Result routing key:** `job.results.stt`  
**Runtime:** Python 3.12 + faster-whisper + torch  
**GPU:** `Dockerfile.gpu` (CUDA cu118)

#### File responsibilities

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI + lifespan; starts `start_consumer()` as daemon thread; `/health` `/readiness` |
| `app/config.py` | Settings: `RABBITMQ_URL`, `DATABASE_URL`, S3 vars, `STT_MODEL_SIZE`, `STT_MODEL_KEY`, `STT_MODEL_LOCAL_PATH`, `STT_DEVICE`, `PORT=8001` |
| `app/worker.py` | Full consumer: load job → download audio → transcribe → write `video_tasks` → publish result |
| `app/model.py` | `WhisperModelManager`: lazy singleton (class-level `_model` + `_lock`); resolution: local path → S3 prefix → HuggingFace |
| `app/storage.py` | `download_file(s3_key, local_path)` via boto3 |
| `app/transcribe.py` | Optional sync `POST /transcribe`, `GET /health/model` |

#### DB writes (D1)

```sql
-- After inference:
UPDATE video_tasks
   SET stt_segments = :segs::jsonb,
       transcript   = :tr,
       stt_metadata = :meta::jsonb,
       source_lang  = COALESCE(:lang, source_lang),
       updated_at   = :now
 WHERE id = :task_id;

UPDATE jobs
   SET status='COMPLETED', output_data=:output::jsonb,
       progress=100.0, completed_at=:now, updated_at=:now
 WHERE id = :job_id;
```

#### Result payload (Claim Check — §15)

```json
{
  "job_id": "<child UUID>",
  "job_type": "STT_TRANSCRIBE",
  "status": "COMPLETED",
  "output_data": {
    "segment_count": 42,
    "language": "en",
    "duration": 123.4
  }
}
```

Full `stt_segments` are in `video_tasks` — never sent over the wire.

#### Invariants validated in Phase 1

1. Idempotency: if job status is COMPLETED on load, return cached `output_data` immediately
2. Cancel before work: if DB reports CANCELLED, ack without processing
3. Transient DB error (cancel check): `nack(requeue=True)`
4. Permanent errors: write FAILED to jobs, publish FAILED result, ack
5. `task_id` fallback: if not in `input_data`, resolve via `SELECT id FROM video_tasks WHERE video_id = :vid ORDER BY created_at DESC LIMIT 1`
6. S3 key resolution: prefers `videos.audio_path` over `videos.file_path`

---

### 6.3 nmt-service

**Location:** `nmt-service/`  
**Port:** 8002  
**Queue:** `stage.nmt` (binding key: `job.start.nmt`)  
**Result routing key:** `job.results.nmt`  
**Runtime:** Python 3.12 + transformers (NLLB-200) + optional Groq

#### File responsibilities

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI + lifespan; starts `start_consumer()` as daemon; `/health` `/readiness` |
| `app/config.py` | Settings: model path, `NMT_INTERNAL_CONCURRENCY=4`, `GROQ_API_KEY`, `NMT_LENGTH_ADJUST_ENABLED`, `PORT=8002` |
| `app/worker.py` | Full consumer: load job → load `stt_segments` from DB → fan-out translate → write `video_tasks` → publish result |
| `app/model.py` | `NLLBTranslatorWrapper`: lazy singleton; resolution: local path → S3 prefix → HuggingFace; multi-stage NLLB pipeline |
| `app/length_adjuster.py` | `adjust_ar(ar_text, en_text, ...)` — Groq iterative length rewrite; no-ops gracefully if no key |
| `app/translate.py` | Optional sync `POST /translate`, `GET /health/model` |

#### Internal fan-out (D3)

One `job.start.nmt` in → one `job.results.nmt` out. No distributed chord.

```python
# Bounded ThreadPoolExecutor over all stt_segments
translated = _translate_all_segments(
    job_id, stt_segments, source_lang, target_lang,
    num_beams, english_ratio_threshold, cancelled_flag
)
```

Cancel watcher: a background daemon thread polls `check_cancelled()` every 3 seconds. Sets `cancelled_flag[0] = True` if job is cancelled. Each segment worker checks the flag before inference. When cancelled, `_translate_all_segments` returns `None` → worker acks silently without publishing FAILED.

#### DB writes (D1)

```sql
UPDATE video_tasks
   SET translated_transcript = :tr,
       segments              = :segs::jsonb,
       status                = :status::taskstatus,  -- COMPLETED or PROCESSING
       progress              = :progress,            -- 100.0 or 50.0
       completed_at          = :completed_at,        -- utcnow() or NULL
       updated_at            = :now
 WHERE id = :task_id;

UPDATE jobs
   SET status='COMPLETED', output_data=:output::jsonb,
       progress=100.0, completed_at=:now, updated_at=:now
 WHERE id = :job_id;
```

#### Parent completion logic

| `output_type` | `video_tasks.status` | `video_tasks.progress` |
|---------------|----------------------|------------------------|
| `captionsAndTranslation` | `COMPLETED` | 100.0 |
| `fullDubbing` | `PROCESSING` | 50.0 |
| `translationAndTTS` | `PROCESSING` | 50.0 |

NMT child job always ends COMPLETED. The *parent* pipeline job status is controlled by the orchestrator (which advances to TTS for fullDubbing/translationAndTTS, or marks COMPLETED for captionsAndTranslation).

#### TTS contract (Phase 2 dependency — document now)

`video_tasks.segments` written by NMT is an array of:
```json
[
  {
    "start": 0.0,
    "end": 2.5,
    "original_text": "Hello world",
    "translated_text": "مرحبا بالعالم"
  }
]
```
This is the format the future `tts-service` reads (`job.input_data → task_id → video_tasks.segments`).

#### Result payload

```json
{
  "job_id": "<child UUID>",
  "job_type": "NMT_TRANSLATE",
  "status": "COMPLETED",
  "output_data": {
    "segment_count": 42,
    "target_lang": "arb_Arab",
    "output_type": "fullDubbing"
  }
}
```

---

### 6.4 tts-service

**Location:** `tts-service/`  
**Port:** 8005  
**Queue:** `stage.tts` (binding key: `job.start.tts`)  
**Runtime:** Python 3.12 + silma-tts + torch (GPU optional)

#### File structure

```
tts-service/
├── Dockerfile  Dockerfile.gpu  requirements-base.txt  pytest.ini
├── tests/{conftest.py, test_worker_logic.py, test_audio_combine.py, test_model.py, test_prewarm.py}
└── app/
    ├── main.py          # FastAPI + lifespan; /health /readiness /health/model
    ├── routes.py        # POST /synthesize (standalone HTTP API)
    ├── prewarm.py       # optional model prewarm at startup
    ├── config.py        # PORT=8005, TTS_INTERNAL_CONCURRENCY, PREWARM_TTS_MODEL
    ├── worker.py        # consume stage.tts → synth + combine → job.results.tts
    ├── model.py         # OmniVoiceManager (non-Celery)
    ├── audio_combine.py # stretch/fit/concat segment WAVs → combined_audio_key
    └── storage.py       # S3 up/down for wavs
```

#### What it does

1. Load translated segments from `video_tasks.segments`
2. Synthesize each segment in a bounded `ThreadPoolExecutor` (D4 — no Redis counter)
3. Run `audio_combine.py` to stretch/fit/concat all segments with silence gaps
4. Upload combined WAV to S3 at `tts/{video_id}/combined_{job_id}.wav`
5. Write `video_tasks.combined_audio_key`
6. Publish `job.results.tts {combined_audio_key, segment_count}`

Standalone `POST /synthesize` on tts-service serves direct HTTP synthesis (also proxied from backend `POST /api/tts/synthesize`).

---

### 6.5 media-service merge stage

**Location:** `media-service/`  
**Port:** 8003  
**Queue:** `stage.merge` (binding key: `job.start.merge`)  
**Runtime:** Python 3.12 + ffmpeg (no ML model)

Media preprocess (audio extract, thumbnail) remains in **backend** `app/media/service.py` (D6). The merge worker is the production path for `fullDubbing` final mux.

#### Source code

- `mux.py` ← `backend/app/dubbing/service.py`: `_replace_video_audio` — explicit `-map 0:v:0`, apad to video duration, `-c:v copy`, `-c:a aac`
- `worker.py` — `dablja-worker` consumer pattern (same as STT/NMT/TTS)

#### What it does (mux-only)

TTS (`tts-service`) already synthesizes per-segment WAVs, combines them, uploads `tts/{video_id}/combined_{job_id}.wav`, and writes `video_tasks.combined_audio_key`. Merge **must not** re-download segments or re-concat.

1. Read `video_tasks.combined_audio_key` + `videos.file_path` (original video)
2. Download both to temp dir (`MERGE_TEMP_DIR`)
3. FFmpeg mux: replace audio track (apad + stream mapping)
4. Upload dubbed video to S3 at `dubbed/{video_id}/dubbed_{job_id}.mp4`
5. Write `videos.dubbed_video_path`; mark `video_tasks` COMPLETED / progress 100
6. Publish `job.results.merge` with lean `{dubbed_video_key, combined_audio_key}`

**Audio-only edge case:** If `media_type != video`, skip mux; mark job COMPLETED with combined audio ref only (`dubbed_video_key: null`).

#### Orchestrator

`fullDubbing` stage order includes `JobTypeDubbingMerge` in `orchestrator/internal/pipeline/manager.go`:

```go
"fullDubbing": {db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate, db.JobTypeTTSSynthesize, db.JobTypeDubbingMerge},
```

---

### 6.6 backend

**Location:** `backend/`  
**Port:** 8000  
**Keeps:** auth, users, videos CRUD, job creation, media preprocess, status polling API

**Publishes `job.created`:** After media preprocess in `app/media/service.py`, calls `publish_job_created(parent_job_id)` via `app/shared/rabbitmq.py`. This is the entry point for the orchestrator.

**Media preprocess** runs as a FastAPI `BackgroundTasks` coroutine (D6) — not via Celery. It:
1. Downloads uploaded video to temp dir
2. Extracts audio (MP3) with ffmpeg
3. Generates thumbnail (JPG)
4. Updates `videos` row (audio_path, thumbnail, metadata)
5. Creates `VideoTask` row
6. Creates parent `FULL_DUBBING_PIPELINE` job row
7. Publishes `job.created`

TTS and merge stages are handled by `tts-service` and `media-service` respectively. Pipeline Celery bridge (`tts_bridge.py`) removed. Standalone TTS API proxied to `tts-service` HTTP (`TTS_SERVICE_URL`).

---

## 7. Messaging topology

Exchange: `dablja.jobs.exchange` (topic, durable)  
DLX: `dablja.jobs.dlx` (direct, durable)  
All messages: `delivery_mode=2` (persistent), `content_type=application/json`

| Queue | Binding key | Consumer | Phase |
|-------|-------------|----------|-------|
| `orchestrator.new_jobs` | `job.created` | orchestrator | 1 |
| `orchestrator.results` | `job.results.*` | orchestrator | 1 |
| `stage.stt` | `job.start.stt` | stt-service | 1 |
| `stage.nmt` | `job.start.nmt` | nmt-service | 1 |
| `stage.tts` | `job.start.tts` | tts-service | 2 |
| `stage.merge` | `job.start.merge` | media-service | 2 |
| `orchestrator.dlq` | DLX routes here | manual inspection | 1 |

QoS: `prefetch_count=1` on all stage queues — natural backpressure.  
Dead letter: poison messages (non-retryable permanent errors) route via DLX to `orchestrator.dlq`.

### Message contracts

**`job.created`** (backend → orchestrator):
```json
{ "job_id": "<FULL_DUBBING_PIPELINE uuid>" }
```

**`job.start.<stage>`** (orchestrator → worker):
```json
{ "job_id": "<child stage job uuid>" }
```
Workers load ALL inputs from the DB via `job_id` (Claim Check — no payloads on the wire).

**`job.results.<stage>`** (worker → orchestrator):
```json
{
  "job_id": "<child stage job uuid>",
  "job_type": "STT_TRANSCRIBE | NMT_TRANSLATE | TTS_SYNTHESIZE | DUBBING_MERGE",
  "status": "COMPLETED | FAILED",
  "output_data": { "...": "lean summary only" },
  "error": "error message — present only on FAILED"
}
```

Golden fixtures in `orchestrator/internal/pipeline/testdata/worker_result_payload.json`.

---

## 8. Data flow per output_type

### `captionsOnly` (Phase 1 validated)

```
backend → job.created → orchestrator
orchestrator → job.start.stt → stt-service
stt-service writes stt_segments to video_tasks
stt-service → job.results.stt → orchestrator
orchestrator: nextStage(captionsOnly, STT) = none → parent COMPLETED
```

### `captionsAndTranslation` (Phase 1 validated)

```
... → stt-service → job.results.stt
orchestrator → job.start.nmt → nmt-service
nmt-service writes translated_segments, video_tasks.status=COMPLETED
nmt-service → job.results.nmt → orchestrator
orchestrator: nextStage(captionsAndTranslation, NMT) = none → parent COMPLETED
```

### `fullDubbing`

```
... → stt → nmt → job.results.nmt
orchestrator → job.start.tts → tts-service
tts-service → job.results.tts → orchestrator
orchestrator → job.start.merge → media-service
media-service → job.results.merge → orchestrator
orchestrator → parent COMPLETED (100%)
```

---

## 9. Cancellation, retries, idempotency

### Cancellation (D8 — cooperative)

```
POST /api/jobs/{id}/cancel
  → backend sets parent + active child status = CANCELLED in DB

Orchestrator: re-reads parent on each job.results.* advance;
              if CANCELLED → stop, no next child created.

Workers: check check_cancelled() at stage start.
NMT/TTS: additional cancel-watcher thread polls every 3s mid-job.
         Sets cancelled_flag; segment loop returns None → ack silently.
```

### Retries

| Failure type | Handling |
|--------------|----------|
| Deterministic stage error | Worker: ack + publish FAILED; orchestrator marks parent FAILED |
| Transient infra error (DB/S3/broker during cancel check) | Worker: nack(requeue=True) |
| Worker crash mid-message | RabbitMQ redelivers (unacked) → idempotent re-run |
| Poison message | DLX → `orchestrator.dlq` for manual inspection |

### Idempotency (§10.3)

- **Workers:** check if job status is already COMPLETED at the start of `process_job()`; if yes, return cached `output_data` without re-running inference.
- **S3 keys:** deterministic derivation from `{video_id}/{job_id}` — re-runs overwrite same key.
- **DB writes:** `UPDATE ... WHERE id = :task_id` — idempotent overwrites on same row.
- **Orchestrator:** duplicate `job.created` → re-publish dispatch if child exists in non-terminal state; skip if COMPLETED.

---

## 10. DB ownership (Phase 1–2 shared DB)

All services share the PostgreSQL instance. Workers write directly via raw SQL (D1).

| Writer | Tables written |
|--------|---------------|
| backend | `videos`, `video_tasks` (create), `jobs` (create parent) |
| orchestrator | `jobs` (create children, update status/progress) |
| stt-service | `video_tasks` (stt_segments, transcript), `jobs` (child status) |
| nmt-service | `video_tasks` (segments, translated_transcript), `jobs` (child status) |
| tts-service | `video_tasks` (combined_audio_key), `jobs` (child status) |
| media-service (merge) | `videos` (dubbed_video_path), `video_tasks`, `jobs` (child status) |

Phase 3 (post-K8s): orchestrator becomes the single writer for `jobs`/`video_tasks`; workers return results only in messages.

---

## 11. Design patterns catalog

| Pattern | Implementation |
|---------|---------------|
| Orchestration-based Saga | Go orchestrator — single source of pipeline order |
| Async Messaging / Event-Driven | All stage comms via AMQP topic exchange |
| Competing Consumers | Stage queues, prefetch=1, scale by replicas |
| Claim Check | S3 for large artifacts; messages carry `job_id` only |
| Correlation ID | `job_id` across all messages and DB rows |
| Idempotent Consumer | At-least-once safe: COMPLETED skip + deterministic S3 keys |
| Dead Letter Queue | `dablja.jobs.dlx → orchestrator.dlq` |
| Cooperative Cancellation | DB flag; orchestrator stops; workers check at boundaries |
| Strangler Fig | One queue at a time: Phase 1 = STT+NMT; Phase 2 = TTS+merge |
| Shared Database (transitional) | All services use PostgreSQL Phase 1 (retired Phase 3) |
| API Gateway / Ingress | backend + frontend are the only internet-facing services |
| Externalized Configuration | All config via env vars; no secrets in images |
| Health Check API | Every service: `/health`, `/readiness`; AI services also `/health/model` (media-service is ffmpeg-only — no model endpoint) |
| Singleton Model Manager | Thread-safe lazy load with double-checked locking |

---

## 12. Testing strategy

### Layer 1 — Unit tests (no infrastructure required)

**Run with:** `pytest` / `go test ./internal/pipeline/...`

| Test file | What it covers |
|-----------|---------------|
| `stt-service/tests/test_worker.py` | `on_message` flow: cancel/bad-JSON/missing-id/idempotency/transient-nack; result payload shape |
| `nmt-service/tests/test_worker_logic.py` | Fan-out cancel; `_update_video_task_nmt` per output_type; segment shape contract; translationAndTTS |
| `orchestrator/internal/pipeline/manager_nextstage_test.go` | `nextStage()` for all 5 `output_type` values |
| `orchestrator/internal/pipeline/manager_test.go` | `WorkerResultPayload` JSON contract; enum parity with Python |
| `backend/tests/test_worker_result_payload.py` | Golden fixture round-trip |
| `media-service/tests/test_worker_logic.py` | Idempotency; cancel pre-check; requires `combined_audio_key`; audio-only skips mux; result payload shape |
| `media-service/tests/test_mux.py` | Mock S3 + ffmpeg; verifies apad filter and stream mapping |

### Layer 2 — Go integration tests (requires postgres:5433 + rabbitmq:5672)

**Run with:** `go test ./internal/pipeline/... -tags=integration -v -count=1`

Covered by `manager_integration_test.go` (T01–T15) and `manager_stt_integration_test.go` (T01–T07):
- New job → PROCESSING → STT dispatch
- Fake STT worker happy path → NMT dispatch
- Failure at every stage → parent FAILED
- Concurrent 20 jobs, worker pool saturation (50 jobs)
- Malformed messages, non-existent job ID
- Duplicate `job.created` idempotency
- `captionsOnly`: parent COMPLETED after STT
- `captionsAndTranslation`: parent COMPLETED after NMT

### Layer 3 — Python integration tests (requires docker-compose.test.yml up)

**Run with:** `./backend/run_integration_tests.sh`

| Test file | What it covers |
|-----------|---------------|
| `backend/tests/integration/test_orchestrator.py` | Full state machine with fake workers; drives `fullDubbing` through STT→NMT→TTS→merge |
| `backend/tests/integration/test_integration.py` | Skipped placeholder |

Shell-script E2E (`test_e2e_*.sh`) is the canonical integration path for live stacks. Python files `test_captions_only.py` / `test_captions_and_translation.py` listed in early drafts were not added — use shell scripts instead.

### Layer 4 — E2E shell scripts (requires full dev stack: `docker compose up`)

| Script | What it covers |
|--------|---------------|
| `test_e2e_stt.sh` | Upload audio to MinIO, seed DB, publish job.created, poll until COMPLETED |
| `test_e2e_captions_and_translation.sh` | Full `captionsAndTranslation` with real STT + NMT |
| `test_e2e_translation_and_tts.sh` | `translationAndTTS` through TTS terminal stage |
| `test_e2e_cancel_mid_tts.sh` | Cooperative cancel during TTS |
| `test_e2e_full_dubbing.sh` | Full `fullDubbing` with real STT + NMT + TTS + merge |
| `test_e2e_merge_only.sh` | Merge smoke: pre-seeded `combined_audio_key`, direct `job.start.merge` |

### Layer 5 — CI (GitHub Actions)

| Workflow | Trigger | What runs |
|----------|---------|-----------|
| `.github/workflows/backend-tests.yml` | PR touching `backend/**` | ruff lint + pytest (unit only, `-m "not integration and not slow"`) |
| `.github/workflows/go-tests.yml` | PR touching `orchestrator/**`, `libs/**`, `stt-service/**`, `nmt-service/**`, `tts-service/**`, `media-service/**` | Go unit tests + Python worker unit tests |

Integration and E2E tests remain manual (require real infra) or optional CI.

---

## 13. Phase 1 exit criteria

- [x] `docs/microservices_lld.md` exists (this file) with full-app design incl. Phase 2 TTS/merge specs
- [x] `libs/dablja-worker` installed by stt-service and nmt-service (local `app/dablja_worker.py` copies removed at Docker build)
- [x] `stt-service/tests/test_worker.py` passes with `pytest` (unit, no infra)
- [x] `nmt-service/tests/test_worker_logic.py` covers all output_types + segment shape contract
- [x] `docker-compose.test.yml` exists and `run_integration_tests.sh` succeeds
- [x] `helpers.py` uses port 5672 (matching docker-compose.yml)
- [x] `captionsOnly` E2E script runs successfully against live stack
- [x] `captionsAndTranslation` E2E script runs successfully against live stack
- [x] Go unit tests pass: `go test ./internal/pipeline/...`
- [x] Backend CI (`backend-tests.yml`) + Go CI (`go-tests.yml`) workflows enabled
- [x] Pipeline TTS via RabbitMQ (`tts-service`) — Celery bridge retired

---

## 14. Phase 2 preview

Full specs in §6.4 (tts-service) and §6.5 (media-service merge stage). Status:

1. [x] Build `tts-service` — extract `SilmaTTSModelManager` + `audio_combine.py` from backend
2. [x] Build `media-service` merge worker — `mux.py` from `DubbingMergeService._replace_video_audio` (mux-only)
3. [x] Orchestrator: restore `JobTypeDubbingMerge` in `stageOrder["fullDubbing"]`
4. [x] Backend: remove `tts_bridge.py`, pipeline Celery TTS tasks, Redis counter
5. [x] Decommission Celery/Redis/Flower from prod compose → `docker-compose.microservices.prod.yml`
6. [x] E2E: `translationAndTTS`, `fullDubbing`, cancel mid-TTS, merge-only smoke

---

## 15. Production deployment

**Dev stack:** `docker compose up` — [docker-compose.yml](../docker-compose.yml) includes rabbitmq, orchestrator, stt/nmt/tts/media-service.

**Prod stack (target):** `docker compose --env-file .env.production -f docker-compose.microservices.prod.yml up -d --build`

| Requirement | Notes |
|-------------|-------|
| `RABBITMQ_URL` on backend | Required for `publish_job_created` after media preprocess |
| `TTS_SERVICE_URL` on backend | Standalone TTS API proxies to tts-service HTTP |
| External S3 | Same as `docker-compose.prod.minimal.yml` — no in-stack MinIO |
| No Celery/Redis/Flower | Pipeline workers are microservices |

**Legacy:** `docker-compose.prod.minimal.yml` (Celery monolith) is deprecated. GCP deploy ([deploy-gcp.yml](../.github/workflows/deploy-gcp.yml)) switches to microservices prod compose.

**Deploy CI:** path filters include `orchestrator/**`, `*-service/**`, `libs/dablja-worker/**` ([deploy-gcp.yml](../.github/workflows/deploy-gcp.yml)).
