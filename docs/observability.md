# DabljaAR Observability

Self-hosted LGTM stack (Loki, Grafana, VictoriaMetrics, Tempo) for the microservices production deployment.

## Production deploy path

Observability is **optional**. It activates when `GRAFANA_ADMIN_PASSWORD` is set in the VM's `.env.production` (from Secret Manager `env-production`).

```
push to main → .github/workflows/deploy-gcp.yml → infra/scripts/deploy-production.sh
  → assemble Caddyfile.production (with grafana block only when enabled)
  → Phase B2: loki, victoriametrics, tempo, otel-collector
  → Phase E2: promtail, exporters, grafana
  → Phase E3: caddy (TLS for grafana.app.$ZONE)
  → health gate: https://grafana.$DOMAIN/api/health
```

**DNS prerequisite:** `grafana.app.yourbrand.tech` must resolve to the VM before the first observability deploy (`terraform apply` with `dns_include_grafana = true`, then `dig +short grafana.app.yourbrand.tech`).

For manual ops commands, use the shared compose helper from repo root:

```bash
source infra/scripts/lib/compose-env.sh
$COMPOSE ps
$COMPOSE logs grafana --tail=50
```

## Quick start

```bash
# Generate Caddy basic-auth hash for Grafana (run once)
caddy hash-password --plaintext 'your-strong-password'

# Add to .env.production, then upload to Secret Manager and re-deploy:
#   GRAFANA_ADMIN_USER=admin
#   GRAFANA_ADMIN_PASSWORD=your-strong-password
#   GRAFANA_BASIC_AUTH_USER=admin
#   GRAFANA_BASIC_AUTH_HASH=<output of caddy hash-password>

source infra/scripts/lib/compose-env.sh
cat Caddyfile.minimal infra/observability/Caddyfile.grafana > Caddyfile.production
$COMPOSE up -d --build
```

Access:

| UI | URL | Auth |
|----|-----|------|
| Grafana | `https://grafana.$DOMAIN` | Caddy basic auth + Grafana admin |
| RabbitMQ | `https://rabbitmq.$DOMAIN` | `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` |

Internal endpoints (not exposed publicly): VictoriaMetrics `:8428`, Loki `:3100`, Tempo `:3200`, OTLP `:4317`.

## Log search (LogQL)

Search by parent or child job ID:

```logql
{service=~"stt|nmt|tts|media|orchestrator|backend"} |= "YOUR_JOB_ID"
```

Structured JSON filter:

```logql
{service="backend"} | json | level="ERROR"
{service="orchestrator"} | json | parent_job_id="YOUR_PARENT_JOB_ID"
{service=~"stt|nmt|tts|media"} | json | job_id="YOUR_CHILD_JOB_ID"
```

Trace correlation (after tracing is enabled):

```logql
{service=~".+"} | json | trace_id="YOUR_TRACE_ID"
```

In Grafana Explore → Loki, use the **TraceID** derived field link to jump to Tempo.

## Dashboards

Pre-provisioned under folder **DabljaAR**:

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Logs Explorer | `dablja-logs` | Filter logs by `service` and `job_id` |
| Pipeline | `dablja-pipeline` | Job rate, failure rate, stage p95, queue depth |
| Infrastructure | `dablja-infra` | CPU, RAM, disk, container memory, Postgres connections |

## Metrics (PromQL)

```promql
# Job throughput
sum(rate(dablja_jobs_completed_total[5m])) by (status)

# Stage latency p95
histogram_quantile(0.95, sum(rate(dablja_stage_duration_seconds_bucket[5m])) by (le, stage))

# Queue backlog
rabbitmq_queue_messages{queue=~"stage\\..*"}

# DLQ
rabbitmq_queue_messages{queue="orchestrator.dlq"}
```

## Tracing

Services export OTLP gRPC to `otel-collector:4317` (20% head sampling in production). Trace context propagates over RabbitMQ via W3C `traceparent` headers.

**Explore workflow:** Tempo → select trace → **Logs for this span** → correlated Loki lines with matching `trace_id`.

Disable tracing locally:

```bash
OTEL_SDK_DISABLED=true
```

## Alerts

Provisioned in Grafana Unified Alerting (`infra/observability/grafana/provisioning/alerting/rules.yml`):

| Alert | Condition |
|-------|-----------|
| DLQ has messages | `orchestrator.dlq` > 0 for 5m |
| Pipeline queue backlog | any `stage.*` queue > 20 for 10m |
| High job failure rate | failed/completed > 5% over 1h |
| Host disk low | root filesystem < 15% free |
| Scrape target down | `up{job=~"backend|orchestrator|..."} == 0` for 2m |

Configure notification channels in Grafana → Alerting → Contact points (email, Slack webhook, etc.).

## Resource limits

| Component | Retention | Compose `mem_limit` |
|-----------|-----------|---------------------|
| Loki | 7 days | 512m |
| VictoriaMetrics | 15 days | 512m |
| Tempo | 3 days | 384m |
| Grafana | — | 256m |
| Promtail | — | 128m |
| OTel Collector | — | 128m |

## Go orchestrator dependencies

After changing `orchestrator/go.mod`, refresh the module cache on a machine with Go 1.21+:

```bash
cd orchestrator && go mod tidy && go mod vendor
```

The production Docker build runs `go mod vendor` automatically.

## Local dev (optional)

Observability overlay is optional. For local debugging without the full stack:

```bash
docker compose -f docker-compose.microservices.prod.yml up -d
```

Enable JSON logs only:

```bash
LOG_JSON_FORMAT=true docker compose ...
```
