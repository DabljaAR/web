# DabljaAR Observability

Self-hosted LGTM stack (Loki, Grafana, VictoriaMetrics, Tempo) for the microservices production deployment.

## Enable / disable

Observability is **optional**. Both compose files are always used; Docker Compose **profiles** control whether LGTM services start.

Add to `.env.production` (Secret Manager `env-production` on the VM):

```env
COMPOSE_PROFILES=observability
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your-strong-password
GRAFANA_BASIC_AUTH_USER=admin
GRAFANA_BASIC_AUTH_HASH=<caddy hash-password output>
```

Remove or comment out `COMPOSE_PROFILES=observability` to run the app stack without Loki/Grafana/Tempo. The pipeline does not depend on observability containers.

**DNS:** `grafana.app.yourbrand.tech` should resolve to the VM (`terraform apply` with `dns_include_grafana = true`, then `dig +short grafana.app.yourbrand.tech`).

## Production deploy path

```
push to main → .github/workflows/deploy-gcp.yml → infra/scripts/deploy-production.sh
  → validate committed Caddyfile.production
  → linear COMPOSE up -d (profile services start when COMPOSE_PROFILES=observability)
  → app health gates (Grafana check is warning-only)
```

For manual ops from repo root:

```bash
source infra/scripts/lib/compose-env.sh
$COMPOSE ps
$COMPOSE logs grafana --tail=50
```

## Quick start

```bash
# In .env.production:
#   COMPOSE_PROFILES=observability
#   GRAFANA_ADMIN_PASSWORD=your-strong-password
#   GRAFANA_BASIC_AUTH_HASH=$(caddy hash-password --plaintext 'your-strong-password')

source infra/scripts/lib/compose-env.sh
$COMPOSE up -d --build
```

Deploy can auto-generate `GRAFANA_BASIC_AUTH_HASH` for a single run when the profile is enabled and the hash is still a placeholder.

Access:

| UI | URL | Auth |
|----|-----|------|
| Grafana | `https://grafana.$DOMAIN` | Caddy basic auth + Grafana admin |
| RabbitMQ | `https://rabbitmq.$DOMAIN` | `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` |

Internal endpoints (not exposed publicly): VictoriaMetrics `:8428`, Loki `:3100`, Tempo `:3200`, OTLP `:4317`.

**Note:** `Caddyfile.production` includes the Grafana site block even when the profile is off. If DNS points at the VM but Grafana is not running, `https://grafana.$DOMAIN` may return 502 until you enable the profile.

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

Trace correlation:

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

Run without the observability profile:

```bash
source infra/scripts/lib/compose-env.sh
$COMPOSE up -d
```

Enable JSON logs only:

```bash
LOG_JSON_FORMAT=true docker compose ...
```
