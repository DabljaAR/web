#!/usr/bin/env bash
# Install CPU-only ONNX Runtime (replaces onnxruntime-gpu pulled by catt-tashkeel / silma-tts).
#
# Usage (Dockerfile):
#   COPY --from=docker_onnx install_cpu_onnx.sh verify_cpu_onnx.py /tmp/docker-onnx/
#   RUN bash /tmp/docker-onnx/install_cpu_onnx.sh
#
# Environment (optional):
#   ONNXRUNTIME_CPU_VERSION — pin e.g. 1.24.4 (default: 1.24.4)
#   PIP_TIMEOUT             — seconds per pip attempt (default: 600)
#   PIP_RETRIES             — pip --retries (default: 3)
set -euo pipefail

ONNXRUNTIME_CPU_VERSION="${ONNXRUNTIME_CPU_VERSION:-1.24.4}"
PIP_TIMEOUT="${PIP_TIMEOUT:-600}"
PIP_RETRIES="${PIP_RETRIES:-3}"

if ! command -v python >/dev/null 2>&1; then
  echo "install_cpu_onnx.sh: python not found on PATH" >&2
  exit 1
fi

if ! command -v pip >/dev/null 2>&1; then
  echo "install_cpu_onnx.sh: pip not found on PATH" >&2
  exit 1
fi

echo "install_cpu_onnx.sh: purging GPU ONNX Runtime wheels"
pip uninstall -y onnxruntime-gpu onnxruntime 2>/dev/null || true

echo "install_cpu_onnx.sh: installing onnxruntime==${ONNXRUNTIME_CPU_VERSION}"

pip install --no-cache-dir \
  --timeout "${PIP_TIMEOUT}" \
  --retries "${PIP_RETRIES}" \
  "onnxruntime==${ONNXRUNTIME_CPU_VERSION}"

python -c "
import onnxruntime as ort
providers = ort.get_available_providers()
print(f'OK: onnxruntime {ort.__version__} providers={providers}')
assert 'CPUExecutionProvider' in providers, providers
"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/verify_cpu_onnx.py" ]]; then
  python "${SCRIPT_DIR}/verify_cpu_onnx.py"
fi
