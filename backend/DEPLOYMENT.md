# DabljaAR Backend Deployment Guide

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/dabljaAR.git
   cd dabljaAR/web/backend
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env with your settings (see Configuration section below)
   ```

3. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Set up database**
   ```bash
   # Start PostgreSQL service
   # Create database: createdb dabljaar
   alembic upgrade head
   ```

5. **Start services**
   ```bash
   # Start MinIO, Redis, and workers
   ./start_dev.sh
   ```

---

## Configuration

### Required Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar` | |
| `SECRET_KEY` | JWT signing secret | `your-secret-key-change-this-in-production` | |
| `MINIO_ENDPOINT` | MinIO/S3 endpoint | `localhost:9000` | `s3.amazonaws.com` |
| `MINIO_ACCESS_KEY` | MinIO/S3 access key | `minioadmin` | |
| `MINIO_SECRET_KEY` | MinIO/S3 secret key | `minioadmin` | |

### AI Model Configuration

#### Speech-to-Text (Whisper)
| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `STT_DEVICE` | Processing device | `auto` | `auto`, `cpu`, `cuda` |
| `STT_MODEL_SIZE` | Whisper model size | `small` | `tiny`, `base`, `small`, `medium`, `large` |
| `STT_COMPUTE_TYPE` | Precision type | `auto` | `float32`, `float16`, `int8` |

#### Text-to-Speech (Habibi-TTS)
| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `HABIBI_DEVICE` | Processing device | `auto` | `auto`, `cpu`, `cuda` |
| `HABIBI_TTS_SRC` | Source code path | *(auto-detected)* | `/path/to/habibi-tts/src` |
| `HABIBI_MODEL_PATH` | Model cache path | *(auto-detected)* | `/path/to/huggingface/cache` |

---

## GPU Setup

### Prerequisites
- NVIDIA GPU with CUDA support
- NVIDIA drivers installed
- CUDA toolkit (version 12.1+ recommended)

### PyTorch GPU Installation

**For GPU support, install PyTorch with CUDA:**
```bash
# Uninstall CPU-only PyTorch first
pip uninstall torch torchaudio

# Install PyTorch with CUDA 12.1 (adjust version as needed)
pip install torch==2.6.0+cu121 torchaudio==2.6.0+cu121 --index-url https://download.pytorch.org/whl/cu121

# Or for latest version:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Verify GPU installation:**
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU count: {torch.cuda.device_count()}")
```

### Enable GPU in Configuration

**Update your `.env` file:**
```env
# Enable GPU for both STT and TTS
STT_DEVICE=cuda
HABIBI_DEVICE=cuda

# Use float16 for better GPU performance
STT_COMPUTE_TYPE=float16
```

### GPU Memory Management

**For limited VRAM, adjust settings:**
```env
# Use smaller Whisper model
STT_MODEL_SIZE=small  # instead of medium/large

# Set memory threshold
STT_GPU_MEMORY_THRESHOLD=0.8  # 80% max usage

# Process one task at a time
STT_MAX_CONCURRENT=1
```

---

## Installation Options

### Option 1: pip install habibi-tts (Recommended)
```bash
pip install habibi-tts
# Paths will be auto-detected
```

### Option 2: Manual Installation
```bash
git clone https://github.com/SWivid/Habibi-TTS.git
cd Habibi-TTS
pip install -e .

# Set paths in .env
echo "HABIBI_TTS_SRC=/path/to/Habibi-TTS/src" >> .env
```

---

## Production Deployment

### Environment Settings
```env
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=your-very-secure-secret-key-here
```

### Docker Deployment

**Create docker-compose.yml:**
```yaml
version: '3.8'
services:
  backend:
    build: .
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/dabljaar
      - HABIBI_DEVICE=cuda  # Set to cpu if no GPU
    volumes:
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
      - minio

  worker:
    build: .
    command: celery -A app.jobs.celery_app worker -Q ai_stt,ai_nmt,ai_tts,media,pipeline --pool=solo
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/dabljaar
      - HABIBI_DEVICE=cuda
    volumes:
      - ./logs:/app/logs
    depends_on:
      - db
      - redis

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: dabljaar
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

### Performance Tuning

**For high-load production:**
```env
# Increase worker concurrency
WORKER_CONCURRENCY=4

# Use larger Whisper model for better accuracy
STT_MODEL_SIZE=medium

# Enable multiple STT workers (if you have multiple GPUs)
STT_MAX_CONCURRENT=2
```

---

## Troubleshooting

### Common Issues

**1. "habibi_tts module not found"**
```bash
pip install habibi-tts
# Or set HABIBI_TTS_SRC manually in .env
```

**2. "CUDA out of memory"**
```env
# Reduce model sizes
STT_MODEL_SIZE=small
STT_COMPUTE_TYPE=int8
```

**3. "Reference audio not found"**
- The system will auto-create fallback audio
- Or set custom path: `HABIBI_REFERENCE_AUDIO=/path/to/reference.wav`

**4. Import errors after GPU installation**
```bash
pip install --upgrade torch torchaudio faster-whisper
```

### Performance Optimization

**CPU-only setup (no GPU):**
```env
STT_DEVICE=cpu
HABIBI_DEVICE=cpu
STT_COMPUTE_TYPE=int8
STT_MODEL_SIZE=small
```

**GPU-optimized setup:**
```env
STT_DEVICE=cuda
HABIBI_DEVICE=cuda
STT_COMPUTE_TYPE=float16
STT_MODEL_SIZE=medium
```

---

## Model Downloads

**On first run, models will be downloaded automatically:**
- Whisper models: `~/.cache/huggingface/hub/`
- Habibi-TTS models: `~/.cache/huggingface/hub/models--SWivid--Habibi-TTS/`
- NLLB models: `~/.cache/huggingface/hub/models--facebook--nllb-200-distilled-600M/`

**Pre-download models (optional):**
```python
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")

from transformers import pipeline
translator = pipeline("translation", model="facebook/nllb-200-distilled-600M")
```

---

## Architecture Overview

```
Audio → STT (Whisper) → NMT (NLLB) → TTS (Habibi) → Audio Files
         ↓             ↓              ↓              ↓
    Transcription   Translation   Synthesis      MinIO/S3
```

---

## Troubleshooting

### PostgreSQL Authentication Error: "password authentication failed"

**Error message:**
```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "postgres"
```

**Root Causes:**
1. `POSTGRES_PASSWORD` environment variable not set or incorrect in `.env` or docker-compose
2. Backend container starts before PostgreSQL is ready to accept connections
3. DATABASE_URL doesn't match the postgres credentials configured

**Solutions:**

**For Production (docker-compose.prod.yml):**

1. **Ensure environment variables are set:**
   ```bash
   # Copy the template and fill in required values
   cp ../.env.production.example ../.env.production
   
   # Edit and set secure values:
   # POSTGRES_PASSWORD=your-very-secure-password
   # SECRET_KEY=your-secret-key
   # MINIO_ROOT_USER=minioadmin
   # MINIO_ROOT_PASSWORD=your-secure-password
   ```

2. **Verify credentials match:**
   - Backend `DATABASE_URL` must use the same credentials as postgres service
   - Check docker-compose.prod.yml backend service environment section
   - Ensure `${POSTGRES_PASSWORD}` variable is consistent

3. **Wait for PostgreSQL before starting:**
   - docker-compose.prod.yml backend now includes `depends_on: postgres: condition: service_healthy`
   - This ensures postgres passes health check before backend starts
   - entrypoint.sh includes `wait_for_postgres()` function for extra safety

4. **Start services in correct order:**
   ```bash
   # Start postgres and let it initialize
   docker-compose -f docker-compose.prod.yml up -d postgres
   
   # Wait 10-15 seconds for postgres to be ready
   sleep 15
   
   # Then start all services
   docker-compose -f docker-compose.prod.yml up -d
   ```

5. **Check logs for details:**
   ```bash
   # See postgres service logs
   docker-compose -f docker-compose.prod.yml logs postgres
   
   # See backend service logs
   docker-compose -f docker-compose.prod.yml logs backend
   ```

**For Development (docker-compose.yml):**

1. **Ensure logs directory exists:**
   ```bash
   mkdir -p logs
   ```

2. **Set DATABASE_URL if not using defaults:**
   ```bash
   # Verify in .env:
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/dabljaar
   ```

3. **Restart postgres container:**
   ```bash
   docker-compose down postgres
   docker-compose up -d postgres
   sleep 5
   docker-compose up backend
   ```

### Backend Health Check Failing

**Error message:**
```
WARNING: unhealthy (in interval 10, having failed 5/5 checks)
```

**Causes:**
- Database migrations failed (check logs)
- API not responding on `http://localhost:8000/api/health`
- Insufficient time for startup (increase `start_period` in healthcheck)

**Solution:**
```bash
# Check logs for actual error
docker-compose logs backend
```

### Progressive Processing
- TTS starts immediately when each segment translation completes
- 30-40% faster than sequential processing
- Parallel execution across STT, NMT, and TTS workers