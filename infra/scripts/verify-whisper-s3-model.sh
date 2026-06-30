#!/usr/bin/env bash
# Verify Whisper medium weights exist in the models bucket at STT_MODEL_KEY prefix.
# Requires aws CLI and .env.production (or exported S3_* vars).
#
# Usage (from repo root):
#   ./infra/scripts/verify-whisper-s3-model.sh
#
# Expects at least:
#   s3://$S3_MODELS_BUCKET/$STT_MODEL_KEY/model.bin
#   s3://$S3_MODELS_BUCKET/$STT_MODEL_KEY/config.json

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f .env.production ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.production
  set +a
fi

: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required}"
: "${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID is required}"
: "${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY is required}"
: "${S3_MODELS_BUCKET:?S3_MODELS_BUCKET is required}"

STT_MODEL_KEY="${STT_MODEL_KEY:-whisper-medium}"
PREFIX="${STT_MODEL_KEY%/}/"

export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"

echo "Listing s3://${S3_MODELS_BUCKET}/${PREFIX} ..."
if ! aws s3 ls "s3://${S3_MODELS_BUCKET}/${PREFIX}" --endpoint-url "$S3_ENDPOINT_URL"; then
  echo "ERROR: Could not list prefix (check bucket, credentials, and STT_MODEL_KEY)" >&2
  exit 1
fi

missing=0
for key in model.bin config.json; do
  if aws s3 ls "s3://${S3_MODELS_BUCKET}/${PREFIX}${key}" --endpoint-url "$S3_ENDPOINT_URL" >/dev/null 2>&1; then
    echo "OK: ${PREFIX}${key}"
  else
    echo "MISSING: ${PREFIX}${key}" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "Upload CTranslate2 faster-whisper files to the prefix above, then set STT_ALLOW_HF_FALLBACK=false." >&2
  exit 1
fi

echo "Whisper S3 model layout looks valid."
