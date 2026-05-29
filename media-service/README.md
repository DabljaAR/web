# media-service

An async Rust microservice built with [Axum](https://github.com/tokio-rs/axum) that handles video/audio processing (ffmpeg), object storage (S3 / MinIO), and video metadata management (PostgreSQL).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Install Dependencies](#install-dependencies)
- [Environment Configuration (.env)](#environment-configuration-env)
- [Running the Service](#running-the-service)
- [Running with Docker](#running-with-docker)
- [API Endpoints](#api-endpoints)
- [Running Tests](#running-tests)

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [Rust](https://rustup.rs) | 1.75+ | Build toolchain |
| [ffmpeg](https://ffmpeg.org/download.html) | 4.x+ | Video/audio processing |
| [PostgreSQL](https://www.postgresql.org/download/) | 13+ | Video metadata storage |
| [MinIO](https://min.io/download) or AWS S3 | — | Object storage |

---

## Install Dependencies

### 1. Rust toolchain

```bash
# Install rustup (skip if already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Reload shell environment
source "$HOME/.cargo/env"

# Verify
rustc --version   # rustc 1.75.0 or newer
cargo --version
```

### 2. System packages (Debian / Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y \
    ffmpeg \
    libssl-dev \
    pkg-config
```

### 3. System packages (macOS with Homebrew)

```bash
brew install ffmpeg
```

### 4. Rust crate dependencies

Cargo downloads all crate dependencies automatically on first build:

```bash
cargo build
```

---

## Environment Configuration (.env)

Copy the example below into a file named `.env` in this directory (`media-service/.env`):

```bash
cp .env.example .env   # if an example file exists
# — or create it manually:
```

**.env file contents:**

```env
# ── Database ──────────────────────────────────────────────────────────────────
# Full PostgreSQL connection string
DATABASE_URL=postgres://postgres:postgres@localhost:5432/dabljaar

# ── S3 / MinIO object storage ─────────────────────────────────────────────────
# For local MinIO use http://localhost:9000
# For AWS S3, remove or comment out AWS_ENDPOINT_URL
AWS_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_DEFAULT_REGION=us-east-1

# Name of the S3 bucket to use (created automatically if it doesn't exist)
S3_MEDIA_BUCKET=dablaja-videos

# ── Server ────────────────────────────────────────────────────────────────────
PORT=8001

# ── Logging ───────────────────────────────────────────────────────────────────
# Options: error | warn | info | debug | trace
RUST_LOG=info
```

### Variable reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string |
| `AWS_ENDPOINT_URL` | No | `http://localhost:9000` | S3-compatible endpoint (omit for real AWS) |
| `AWS_ACCESS_KEY_ID` | No | `minioadmin` | S3 / MinIO access key |
| `AWS_SECRET_ACCESS_KEY` | No | `minioadmin` | S3 / MinIO secret key |
| `AWS_DEFAULT_REGION` | No | `us-east-1` | AWS region |
| `S3_MEDIA_BUCKET` | No | `dablaja-videos` | Bucket name (auto-created if missing) |
| `PORT` | No | `8001` | HTTP port the service listens on |
| `RUST_LOG` | No | `info` | Log level filter |

### Starting MinIO locally (Docker)

```bash
docker run -d \
  --name minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  quay.io/minio/minio server /data --console-address ":9001"
```

MinIO console → http://localhost:9001 (login: `minioadmin` / `minioadmin`)

---

## Running the Service

```bash
# Development (reads .env automatically)
cargo run

# Release build
cargo build --release
./target/release/media-service
```

The service starts on `http://localhost:8001` by default.  
Verify it is up:

```bash
curl http://localhost:8001/health
# {"status":"ok"}
```

---

## Running with Docker

```bash
# Build image
docker build -t media-service .

# Run (pass env vars explicitly or via --env-file)
docker run -d \
  --name media-service \
  -p 8001:8001 \
  --env-file .env \
  media-service
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/videos/:id` | Get video record |
| `PATCH` | `/videos/:id/paths` | Update file paths on a video |
| `PATCH` | `/videos/:id/status` | Update processing status |
| `GET` | `/ffmpeg/metadata?path=<key>` | Extract metadata from a stored file |
| `POST` | `/ffmpeg/extract-audio` | Extract audio track to MP3 |
| `POST` | `/ffmpeg/thumbnail` | Generate a thumbnail image |
| `POST` | `/storage/presign` | Generate a pre-signed download URL |

---

## Running Tests

All tests are **pure unit tests** — no database, no S3, no ffmpeg binary is required.

### Run everything

```bash
cargo test
```

Expected output:
```
running 66 tests
test config::tests::... ok
test db::tests::...     ok
test ffmpeg::tests::... ok
test routes::tests::... ok

test result: ok. 66 passed; 0 failed
```

### Run a specific module

```bash
cargo test config        # env-var / config parsing tests (10)
cargo test ffmpeg        # ffprobe JSON parsing + VideoMetadata tests (23)
cargo test db            # DB struct serialization tests (10)
cargo test routes        # HTTP handler tests with mock storage (23)
```

### Run a single test by name

```bash
cargo test test_full_video_with_audio
cargo test test_presign_returns_200_with_url_field
cargo test test_missing_database_url_returns_error
```

### Run with log output visible

```bash
cargo test -- --nocapture
```

### Run tests single-threaded (avoids env-var races in config tests)

```bash
cargo test -- --test-threads=1
```

### List all tests without running them

```bash
cargo test -- --list
```

### Test file layout

```
src/
├── config/
│   ├── mod.rs          # production code
│   └── tests.rs        # AppConfig::from_env() tests
├── ffmpeg/
│   ├── mod.rs          # production code
│   └── tests.rs        # ffprobe JSON parsing tests
├── db/
│   ├── mod.rs          # production code
│   └── tests.rs        # DB payload & Video struct tests
└── routes/
    ├── mod.rs
    ├── health.rs        # production code
    ├── ffmpeg_ops.rs    # production code
    └── tests/
        ├── mod.rs
        ├── health.rs    # health route tests
        └── ffmpeg_ops.rs # route handler tests (MockStorage)
```
