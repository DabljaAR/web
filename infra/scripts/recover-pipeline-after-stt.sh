#!/usr/bin/env bash
# Re-publish a COMPLETED STT result so the orchestrator advances the pipeline.
# Use after fixing the orchestrator duplicate-result guard when a parent job is
# stuck at ~25% with a COMPLETED STT child but no NMT dispatch.
#
# Usage (from repo root on prod VM):
#   ./infra/scripts/recover-pipeline-after-stt.sh <stt_child_job_id>
#
# Example:
#   ./infra/scripts/recover-pipeline-after-stt.sh 40802ab4-8c75-43e4-bd77-64349190eec0

set -euo pipefail

STT_JOB_ID="${1:-}"
if [[ -z "$STT_JOB_ID" ]]; then
  echo "Usage: $0 <stt_child_job_id>" >&2
  exit 1
fi

COMPOSE=(docker compose --env-file .env.production -f docker-compose.microservices.prod.yml)
PAYLOAD=$(printf '{"job_id":"%s","job_type":"STT_TRANSCRIBE","status":"COMPLETED","output_data":{}}' "$STT_JOB_ID")

echo "Publishing job.results.stt COMPLETED for child $STT_JOB_ID ..."
"${COMPOSE[@]}" exec -T rabbitmq rabbitmqadmin publish \
  exchange=dablja.jobs.exchange \
  routing_key=job.results.stt \
  payload="$PAYLOAD"

echo "Done. Check orchestrator logs for NMT dispatch:"
echo "  ${COMPOSE[*]} logs orchestrator --tail=50"
