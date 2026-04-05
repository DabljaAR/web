#!/bin/bash
# =============================================================================
# DabljaAR VM Startup Script
# Auto-recovery for Spot VM preemptions
# =============================================================================
set -euo pipefail

# Logging
exec > >(tee -a /var/log/startup.log) 2>&1
echo "=========================================="
echo "Startup script started at $(date)"
echo "=========================================="

GPU_ENABLED="${gpu_enabled}"

# =============================================================================
# 1. Wait for GPU driver to be ready (GPU mode only)
# =============================================================================
if [ "$GPU_ENABLED" = "true" ]; then
  echo "Waiting for GPU driver..."
  MAX_RETRIES=30
  RETRY_COUNT=0
  until nvidia-smi > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
      echo "ERROR: GPU driver not ready after $MAX_RETRIES attempts"
      exit 1
    fi
    echo "Waiting for GPU... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 10
  done
  echo "GPU driver ready!"
  nvidia-smi
else
  echo "GPU disabled, running in CPU-only mode"
fi

# =============================================================================
# 2. Install Docker and Docker Compose (if not present)
# =============================================================================
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $(whoami)
fi

if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    apt-get update && apt-get install -y docker-compose-plugin
fi

# Install NVIDIA Container Toolkit for GPU support in Docker (GPU mode only)
if [ "$GPU_ENABLED" = "true" ]; then
  if ! dpkg -l | grep -q nvidia-container-toolkit; then
    echo "Installing NVIDIA Container Toolkit..."
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | apt-key add -
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
      tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update && apt-get install -y nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
  fi
else
  echo "Skipping NVIDIA Container Toolkit (CPU-only mode)"
fi

# =============================================================================
# 3. Mount data disk (persistent across preemptions)
# =============================================================================
echo "Mounting data disk..."
DISK_DEV="/dev/disk/by-id/google-${data_disk_name}"
MOUNT_POINT="/mnt/data"

mkdir -p $MOUNT_POINT

# Check if disk needs formatting
if ! blkid $DISK_DEV &> /dev/null; then
    echo "Formatting data disk..."
    mkfs.ext4 -F $DISK_DEV
fi

# Mount if not already mounted
if ! mountpoint -q $MOUNT_POINT; then
    mount -o discard,defaults $DISK_DEV $MOUNT_POINT
    echo "$DISK_DEV $MOUNT_POINT ext4 discard,defaults,nofail 0 2" >> /etc/fstab
fi

# Create data directories
mkdir -p $MOUNT_POINT/{postgres,redis,minio,models}
chmod 755 $MOUNT_POINT/*

echo "Data disk mounted at $MOUNT_POINT"

# =============================================================================
# 4. Fetch secrets from Secret Manager
# =============================================================================
echo "Fetching secrets from Secret Manager..."

export DB_PASSWORD=$(gcloud secrets versions access latest --secret="${name_prefix}-db-password" --project="${project_id}" 2>/dev/null || echo "postgres")
export SECRET_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-secret-key" --project="${project_id}" 2>/dev/null || echo "change-me-in-production")
export MINIO_ACCESS_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-minio-access-key" --project="${project_id}" 2>/dev/null || echo "minioadmin")
export MINIO_SECRET_KEY=$(gcloud secrets versions access latest --secret="${name_prefix}-minio-secret-key" --project="${project_id}" 2>/dev/null || echo "minioadmin")

echo "Secrets loaded"

# =============================================================================
# 5. Sync models from GCS (incremental - fast on restart)
# =============================================================================
echo "Syncing AI models from GCS..."
MODEL_DIR="/opt/models"
mkdir -p $MODEL_DIR

# Use gsutil rsync for incremental sync
if gsutil ls gs://${model_bucket}/ &> /dev/null; then
    gsutil -m rsync -r -d gs://${model_bucket}/ $MODEL_DIR/
    echo "Models synced to $MODEL_DIR"
else
    echo "WARNING: Model bucket gs://${model_bucket} not found or empty"
fi

# =============================================================================
# 6. Clone or update application repository
# =============================================================================
echo "Setting up application..."
APP_DIR="/opt/app"

if [ -d "$APP_DIR/.git" ]; then
    echo "Updating existing repository..."
    cd $APP_DIR
    git fetch origin
    git reset --hard origin/${app_repo_branch}
else
    echo "Cloning repository..."
    rm -rf $APP_DIR
    git clone --branch ${app_repo_branch} ${app_repo_url} $APP_DIR
fi

cd $APP_DIR

# =============================================================================
# 7. Create .env file with secrets
# =============================================================================
echo "Creating .env file..."
cat > $APP_DIR/.env <<EOF
# Database
DATABASE_URL=postgresql+asyncpg://postgres:$DB_PASSWORD@postgres:5432/dabljaar
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=dabljaar

# Security
SECRET_KEY=$SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=$MINIO_ACCESS_KEY
MINIO_SECRET_KEY=$MINIO_SECRET_KEY
MINIO_BUCKET_NAME=dablaja-videos
MINIO_SECURE=false
MINIO_ROOT_USER=$MINIO_ACCESS_KEY
MINIO_ROOT_PASSWORD=$MINIO_SECRET_KEY

# AI Models
NMT_MODEL_URL=/opt/models/nmt-v4

# GPU Memory Optimization
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
EOF

chmod 600 $APP_DIR/.env

# =============================================================================
# 8. Setup persistent volume symlinks
# =============================================================================
echo "Setting up persistent volumes..."

# Stop existing containers if running
docker compose down 2>/dev/null || true

# Create docker-compose override for volume mounts
cat > $APP_DIR/docker-compose.override.yml <<EOF
services:
  postgres:
    volumes:
      - /mnt/data/postgres:/var/lib/postgresql/data

  redis:
    volumes:
      - /mnt/data/redis:/data

  minio:
    volumes:
      - /mnt/data/minio:/data
EOF

cat >> $APP_DIR/docker-compose.override.yml <<EOF
  celery-worker-ai:
    volumes:
      - ./backend:/app
      - /opt/models:/opt/models:ro
EOF

if [ "$GPU_ENABLED" = "true" ]; then
cat >> $APP_DIR/docker-compose.override.yml <<EOF
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
EOF
fi

# =============================================================================
# 9. Start Docker Compose services
# =============================================================================
echo "Starting services..."
cd $APP_DIR
docker compose pull
docker compose up -d

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 30

# Check service status
docker compose ps

echo "=========================================="
echo "Startup script completed at $(date)"
echo "=========================================="
echo ""
echo "Services available at:"
echo "  Frontend:     http://$(curl -s ifconfig.me):5173"
echo "  Backend API:  http://$(curl -s ifconfig.me):8000"
echo "  API Docs:     http://$(curl -s ifconfig.me):8000/docs"
echo "  Flower:       http://$(curl -s ifconfig.me):5555"
echo "  MinIO:        http://$(curl -s ifconfig.me):9001"
echo ""
