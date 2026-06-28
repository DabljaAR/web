# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared worker library (provided via additional_contexts in compose)
COPY --from=shared . /tmp/dablja-worker
RUN pip install --no-cache-dir /tmp/dablja-worker

# CPU-only PyTorch — must run before requirements-base.txt so pip never pulls CUDA torch from PyPI.
COPY --from=docker_torch install_cpu.sh verify_cpu_torch.py /tmp/docker-torch/
RUN chmod +x /tmp/docker-torch/install_cpu.sh \
    && TORCH_CPU_VERSION=2.2.0 bash /tmp/docker-torch/install_cpu.sh

COPY requirements-base.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=600 --retries=3 -r requirements-base.txt

# Guard: transformers must not replace CPU torch with a CUDA wheel.
RUN python /tmp/docker-torch/verify_cpu_torch.py

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

COPY . .
# Remove the vendored copy now that the package is installed
RUN rm -f app/dablja_worker.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8002

CMD ["python", "-m", "app.main"]
