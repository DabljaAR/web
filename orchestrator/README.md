# DabljaAR Orchestrator

Event-driven pipeline coordinator for the AI dubbing workflow. Written in Go, uses RabbitMQ for messaging and PostgreSQL for job state.

## How it works

```
FastAPI creates job
       │
       ▼  (publishes "job.created")
Orchestrator receives new job
       │
       ▼  (publishes "job.start.stt")
    STT Worker ─── transcribes audio ──► publishes result to "job.results.stt"
       │
       ▼  (orchestrator advances to next stage)
    NMT Worker ─── translates text ────► publishes result to "job.results.nmt"
       │
       ▼
    TTS Worker ─── synthesizes speech ─► publishes result to "job.results.tts"
       │
       ▼
   Merge Worker ─ assembles output ───► publishes result to "job.results.merge"
       │
       ▼  (orchestrator marks parent job COMPLETED)
      Done
```

The orchestrator **does not do AI work**. It is a state machine that:
1. Listens for new jobs (`job.created`) and kicks off the pipeline
2. Listens for worker results (`job.results.*`) and advances to the next stage
3. Tracks job status in PostgreSQL
4. Routes failed messages to a dead-letter queue

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `RABBITMQ_URL` | — | RabbitMQ connection string |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `HEALTH_PORT` | `8081` | Health check HTTP port |
| `WORKER_POOL_SIZE` | `10` | Max concurrent messages processed |

## Run locally

```bash
# Prerequisites: PostgreSQL and RabbitMQ running locally

export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
export DATABASE_URL="postgres://user:pass@localhost:5432/dabljaar?sslmode=disable"

go run ./cmd/server/main.go
```

## Run with Docker

```bash
docker build -t orchestrator .
docker run --rm \
  -e RABBITMQ_URL="amqp://guest:guest@rabbitmq:5672/" \
  -e DATABASE_URL="postgres://user:pass@postgres:5432/dabljaar?sslmode=disable" \
  orchestrator
```

## Happy path (current state)

1. FastAPI creates a `FULL_DUBBING_PIPELINE` job in the DB and publishes `{"job_id": "..."}` to routing key `job.created`
2. Orchestrator picks it up, sets status to `PROCESSING`, publishes to `job.start.stt`
3. **STT Worker** (not yet built) transcribes audio, publishes result to `job.results.stt`
4. Orchestrator persists result, publishes to `job.start.nmt`
5. **NMT Worker** (not yet built) translates, publishes to `job.results.nmt`
6. Orchestrator persists, publishes to `job.start.tts`
7. **TTS Worker** (not yet built) synthesizes, publishes to `job.results.tts`
8. Orchestrator persists, publishes to `job.start.merge`
9. **Merge Worker** (not yet built) assembles, publishes to `job.results.merge`
10. Orchestrator marks parent job `COMPLETED`

## Health endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness — returns 200 if DB + RabbitMQ are reachable |
| `GET /readiness` | Readiness — returns 200 only when both dependencies are healthy |

## Project structure

```
cmd/server/main.go     — entry point, wires everything
internal/
  db/db.go             — GORM model (Job), PostgreSQL connection
  mq/rabbitmq.go       — RabbitMQ connection + exchange
  pipeline/manager.go  — core state machine, consumers, handlers
  health/health.go     — health/readiness HTTP server
```
