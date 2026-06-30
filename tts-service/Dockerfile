# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=shared . /tmp/dablja-worker
RUN pip install --no-cache-dir /tmp/dablja-worker

COPY --from=docker_torch install_cpu.sh verify_cpu_torch.py /tmp/docker-torch/
RUN chmod +x /tmp/docker-torch/install_cpu.sh \
    && TORCH_CPU_VERSION=2.6.0 bash /tmp/docker-torch/install_cpu.sh

COPY requirements-base.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=600 --retries=3 -r requirements-base.txt

# silma-tts pulls CUDA torch and onnxruntime-gpu — reinstall CPU stacks after requirements.
RUN TORCH_CPU_VERSION=2.6.0 bash /tmp/docker-torch/install_cpu.sh

COPY --from=docker_onnx install_cpu_onnx.sh verify_cpu_onnx.py /tmp/docker-onnx/
RUN chmod +x /tmp/docker-onnx/install_cpu_onnx.sh \
    && bash /tmp/docker-onnx/install_cpu_onnx.sh

# Guard: requirements must not leave CUDA torch or GPU ONNX wheels in the image.
RUN TORCH_CPU_VERSION=2.6.0 python /tmp/docker-torch/verify_cpu_torch.py \
    && python /tmp/docker-onnx/verify_cpu_onnx.py \
    && python -c "import torchaudio; import silma_tts"

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8005

CMD ["python", "-m", "app.main"]
