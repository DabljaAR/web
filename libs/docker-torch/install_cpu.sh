#!/usr/bin/env bash
# Install CPU-only PyTorch from the official PyTorch CPU wheel index.
#
# Usage (Dockerfile):
#   COPY --from=docker_torch install_cpu.sh verify_cpu_torch.py /tmp/docker-torch/
#   RUN bash /tmp/docker-torch/install_cpu.sh
#
# Environment (optional):
#   TORCH_CPU_VERSION   — pin e.g. 2.2.0 (default: 2.2.0)
#   PYTORCH_CPU_INDEX   — wheel index (default: https://download.pytorch.org/whl/cpu)
#   PIP_TIMEOUT         — seconds per pip attempt (default: 600)
#   PIP_RETRIES         — pip --retries (default: 3)
set -euo pipefail

TORCH_CPU_VERSION="${TORCH_CPU_VERSION:-2.2.0}"
PYTORCH_CPU_INDEX="${PYTORCH_CPU_INDEX:-https://download.pytorch.org/whl/cpu}"
PIP_TIMEOUT="${PIP_TIMEOUT:-600}"
PIP_RETRIES="${PIP_RETRIES:-3}"

if ! command -v python >/dev/null 2>&1; then
  echo "install_cpu.sh: python not found on PATH" >&2
  exit 1
fi

if ! command -v pip >/dev/null 2>&1; then
  echo "install_cpu.sh: pip not found on PATH" >&2
  exit 1
fi

purge_cuda_torch_artifacts() {
  echo "install_cpu.sh: purging CUDA torch and companion wheels"
  pip uninstall -y torch torchvision torchaudio 2>/dev/null || true
  local pkgs=""
  pkgs="$(pip freeze 2>/dev/null \
    | grep -iE '^(nvidia-|triton|cuda-toolkit|cuda-bindings|cuda-pathfinder)' \
    | cut -d= -f1 \
    | sort -u \
    | tr '\n' ' ' \
    || true)"
  if [[ -n "${pkgs// }" ]]; then
    # shellcheck disable=SC2086
    pip uninstall -y ${pkgs} 2>/dev/null || true
  fi
}

purge_cuda_torch_artifacts

echo "install_cpu.sh: installing torch==${TORCH_CPU_VERSION} from ${PYTORCH_CPU_INDEX}"

pip install --no-cache-dir \
  --timeout "${PIP_TIMEOUT}" \
  --retries "${PIP_RETRIES}" \
  "torch==${TORCH_CPU_VERSION}" \
  --index-url "${PYTORCH_CPU_INDEX}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/verify_cpu_torch.py" ]]; then
  python "${SCRIPT_DIR}/verify_cpu_torch.py"
else
  python -c "
import torch
assert torch.version.cuda is None, f'expected CPU torch, got cuda={torch.version.cuda!r}'
assert not torch.cuda.is_available(), 'cuda.is_available() must be False for CPU images'
print(f'OK: torch {torch.__version__} (cpu-only)')
"
fi
