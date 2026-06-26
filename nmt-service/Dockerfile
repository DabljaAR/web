FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY nmt-service/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=600 -r requirements.txt

# Copy shared NMT core from backend (single source of truth)
COPY backend/app/nmt/model.py nmt_core/model.py
COPY backend/app/nmt/length_adjuster.py nmt_core/length_adjuster.py
RUN touch nmt_core/__init__.py

COPY nmt-service/app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8002

CMD ["python", "-m", "app.main"]
