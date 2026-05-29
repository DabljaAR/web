# Media Microservice — Implementation Plan

> Total estimated time: 2.5 hours
> Language: Rust + Tokio + Axum
> Each phase has a VERIFY block — do not proceed until it passes

---

## Phase 0 — Environment Check & Setup (5 min)

- [ ] Verify Rust toolchain
- [ ] Verify ffmpeg, ffprobe, pkg-config, libssl-dev, cmake are installed
- [ ] Install any missing tools (exact commands below)
- [ ] Install cargo-watch and sqlx-cli

```bash
rustc --version
# Expected: rustc 1.7x.x (...)

cargo --version
# Expected: cargo 1.7x.x (...)

ffmpeg -version 2>&1 | head -1
# Expected: ffmpeg version 4.x or 5.x or 6.x

ffprobe -version 2>&1 | head -1
# Expected: ffprobe version 4.x or 5.x or 6.x

docker compose version
# Expected: Docker Compose version v2.x.x

ls /home/eslam-amr/Documents/web-main/
# Expected: backend  docker-compose.yml  frontend  (and possibly Caddyfile)
```

- [ ] Install sqlx-cli (needed to ping DB and run prepare):

```bash
cargo install sqlx-cli --no-default-features --features postgres
sqlx --version
# Expected: sqlx-cli x.x.x
```

- [ ] Install cargo-watch (needed for dev iteration):

```bash
cargo install cargo-watch
cargo watch --version
# Expected: cargo-watch x.x.x
```

### ✅ VERIFY Phase 0

```bash
rustc --version && cargo --version && ffmpeg -version 2>&1 | head -1 && docker compose version
# Expected (all four succeed, no "command not found"):
# rustc 1.7x.x (...)
# cargo 1.7x.x (...)
# ffmpeg version 6.x.x (or 4.x/5.x) ...
# Docker Compose version v2.x.x
```

### 🔁 RETRY Phase 0

If rustc missing:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
source "$HOME/.cargo/env"
rustc --version
```

If ffmpeg missing:
```bash
sudo apt update && sudo apt install -y ffmpeg
ffmpeg -version
```

If pkg-config or libssl-dev missing (needed for Docker build):
```bash
sudo apt install -y pkg-config libssl-dev cmake
```

If sqlx-cli missing after cargo install:
```bash
source "$HOME/.cargo/env"
sqlx --version
```

Re-run VERIFY until all pass.

---

## Phase 1 — Scaffold the Rust Project (10 min)

- [ ] Change to the web-main root (NOT inside backend — media-service is a sibling):

```bash
cd /home/eslam-amr/Documents/web-main
cargo new media-service --bin
```

- [ ] Verify the generated layout:

```bash
ls /home/eslam-amr/Documents/web-main/media-service/
# Expected: Cargo.toml  src/

ls /home/eslam-amr/Documents/web-main/media-service/src/
# Expected: main.rs
```

- [ ] Create the module directory layout:

> **Verified:** Only `storage/mod.rs` is created — there is no `s3.rs` or `local.rs` subfile.
> `S3Storage` is defined directly in `storage/mod.rs` and exported from there,
> so `use storage::{S3Storage, StorageBackend}` in `main.rs` is correct as-is.
> Do NOT create s3.rs or local.rs.

```bash
mkdir -p /home/eslam-amr/Documents/web-main/media-service/src/{db,storage,ffmpeg,routes,config}
touch /home/eslam-amr/Documents/web-main/media-service/src/routes/{mod.rs,health.rs,videos.rs,ffmpeg_ops.rs}
touch /home/eslam-amr/Documents/web-main/media-service/src/db/mod.rs
touch /home/eslam-amr/Documents/web-main/media-service/src/storage/mod.rs
touch /home/eslam-amr/Documents/web-main/media-service/src/ffmpeg/mod.rs
touch /home/eslam-amr/Documents/web-main/media-service/src/config/mod.rs
```

- [ ] Replace `/home/eslam-amr/Documents/web-main/media-service/Cargo.toml` with:

> **Verified:** This Cargo.toml does NOT contain `tokio-process`, `axum-multipart`, or
> `multipart = "0.18"`. Those crates are wrong and have been removed:
> - `tokio-process` was merged into tokio 1.x — `tokio::process` is available via `features = ["full"]`
> - `axum-multipart` does not exist on crates.io — axum has multipart via `features = ["multipart"]`
> - `multipart = "0.18"` is an unrelated crate, not needed here
> There is exactly one Cargo.toml block below. Use it.

```toml
[package]
name = "media-service"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "media-service"
path = "src/main.rs"

[dependencies]
# Async runtime — tokio::process is built-in via features=["full"], NO tokio-process crate
tokio = { version = "1", features = ["full"] }

# Web framework — multipart is built into axum via features=["multipart"], NO axum-multipart crate
axum = { version = "0.7", features = ["multipart"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["trace", "cors"] }

# Database
sqlx = { version = "0.7", features = ["runtime-tokio-rustls", "postgres", "chrono", "json", "uuid"] }

# S3 / MinIO (force_path_style required for MinIO compatibility)
aws-config = { version = "1.1", features = ["behavior-version-latest"] }
aws-sdk-s3 = "1.14"

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"

# Config / env
dotenvy = "0.15"

# Error handling
thiserror = "1"
anyhow = "1"

# Logging / tracing
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "json"] }

# Async traits
async-trait = "0.1"

# UUIDs
uuid = { version = "1", features = ["v4"] }

# Time
chrono = { version = "0.4", features = ["serde"] }

# Temp files (for FFmpeg pipeline)
tempfile = "3"

# Byte helpers
bytes = "1"

[profile.release]
opt-level = 3
lto = true
codegen-units = 1
strip = true
```

### ✅ VERIFY Phase 1

```bash
cd /home/eslam-amr/Documents/web-main/media-service && cargo check 2>&1 | tail -3
# Expected: Finished `dev` profile [unoptimized + debuginfo] target(s) in Xs
# Must NOT contain any line starting with "error["

find /home/eslam-amr/Documents/web-main/media-service/src -type f | sort
# Expected:
# .../src/config/mod.rs
# .../src/db/mod.rs
# .../src/ffmpeg/mod.rs
# .../src/main.rs
# .../src/routes/ffmpeg_ops.rs
# .../src/routes/health.rs
# .../src/routes/mod.rs
# .../src/routes/videos.rs
# .../src/storage/mod.rs
```

### 🔁 RETRY Phase 1

If `cargo new` fails because directory already exists:
```bash
rm -rf /home/eslam-amr/Documents/web-main/media-service
cd /home/eslam-amr/Documents/web-main && cargo new media-service --bin
```

If `cargo check` reports dependency resolution errors:
```bash
cargo update
cargo check 2>&1 | grep "^error"
```

Re-run VERIFY until zero errors.

---

## Phase 2 — Environment Config (5 min)

- [ ] Create `/home/eslam-amr/Documents/web-main/media-service/src/config/mod.rs`:

```rust
use std::env;

// Clone IS derived — main.rs calls cfg.clone() when building AppState
#[derive(Debug, Clone)]
pub struct AppConfig {
    pub database_url: String,
    pub aws_endpoint_url: String,
    pub aws_access_key_id: String,
    pub aws_secret_access_key: String,
    pub aws_default_region: String,
    pub s3_media_bucket: String,
    pub port: u16,
}

impl AppConfig {
    pub fn from_env() -> Result<Self, String> {
        Ok(Self {
            // Note: SQLx requires postgres:// prefix, NOT postgresql+asyncpg://
            database_url: env::var("DATABASE_URL")
                .map_err(|_| "DATABASE_URL must be set".to_string())?,
            aws_endpoint_url: env::var("AWS_ENDPOINT_URL")
                .unwrap_or_else(|_| "http://localhost:9000".to_string()),
            aws_access_key_id: env::var("AWS_ACCESS_KEY_ID")
                .unwrap_or_else(|_| "minioadmin".to_string()),
            aws_secret_access_key: env::var("AWS_SECRET_ACCESS_KEY")
                .unwrap_or_else(|_| "minioadmin".to_string()),
            aws_default_region: env::var("AWS_DEFAULT_REGION")
                .unwrap_or_else(|_| "us-east-1".to_string()),
            s3_media_bucket: env::var("S3_MEDIA_BUCKET")
                .unwrap_or_else(|_| "dablaja-videos".to_string()),
            port: env::var("PORT")
                .unwrap_or_else(|_| "8001".to_string())
                .parse::<u16>()
                .map_err(|_| "PORT must be a valid u16".to_string())?,
        })
    }
}
```

- [ ] Create `/home/eslam-amr/Documents/web-main/media-service/.env` for local dev:

```env
# SQLx uses postgres:// — NOT postgresql+asyncpg:// (that is the Python asyncpg driver prefix)
# Port 5433 because docker-compose.yml maps postgres 5432→5433 on the host
DATABASE_URL=postgres://postgres:postgres@localhost:5433/dabljaar
AWS_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_DEFAULT_REGION=us-east-1
S3_MEDIA_BUCKET=dablaja-videos
PORT=8001
RUST_LOG=info
```

### ✅ VERIFY Phase 2

```bash
grep -n "DATABASE_URL\|AWS_ENDPOINT" \
  /home/eslam-amr/Documents/web-main/media-service/src/config/mod.rs | head -5
# Expected: lines containing DATABASE_URL and AWS_ENDPOINT_URL env var reads
```

### 🔁 RETRY Phase 2

If file is missing, re-create it with the content above. No compilation check in this phase —
that happens in Phase 3 when module declarations are added to main.rs.

---

## Phase 3 — Database Layer (15 min)

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/db/mod.rs`:

```rust
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};

pub async fn create_pool(database_url: &str) -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        .max_connections(10)
        .connect(database_url)
        .await
}

/// Mirrors exactly the `videos` table schema.
/// id is VARCHAR(36) — UUID stored as String, NOT a postgres native UUID type.
/// user_id is Integer (i32), not UUID.
/// status and media_type are Postgres ENUMs — cast to TEXT in SELECT for sqlx compat.
/// duration and frame_rate use ::FLOAT8 cast in SELECT in case columns are NUMERIC type.
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Video {
    pub id: String,
    pub user_id: i32,
    pub title: String,
    pub original_filename: String,
    pub media_type: String,
    pub file_path: String,
    pub thumbnail_path: Option<String>,
    pub audio_path: Option<String>,
    pub dubbed_video_path: Option<String>,
    pub dubbing_metadata: Option<serde_json::Value>,
    pub duration: Option<f64>,
    pub width: Option<i32>,
    pub height: Option<i32>,
    pub size_bytes: Option<i64>,
    pub format: Option<String>,
    pub codec: Option<String>,
    pub frame_rate: Option<f64>,
    pub status: String,
    pub error_message: Option<String>,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
}

/// Payload for PATCH /videos/:id/paths
/// Called by Python Celery after dubbing to write dubbed_video_path + metadata.
#[derive(Debug, Deserialize)]
pub struct PatchPathsPayload {
    pub dubbed_video_path: Option<String>,
    pub dubbing_metadata: Option<serde_json::Value>,
    pub audio_path: Option<String>,
    pub thumbnail_path: Option<String>,
    pub file_path: Option<String>,
}

/// Payload for PATCH /videos/:id/status
/// Called by Python background tasks to update processing state + metadata.
#[derive(Debug, Deserialize)]
pub struct PatchStatusPayload {
    pub status: String,
    pub error_message: Option<String>,
    pub duration: Option<f64>,
    pub width: Option<i32>,
    pub height: Option<i32>,
    pub size_bytes: Option<i64>,
    pub format: Option<String>,
    pub codec: Option<String>,
    pub frame_rate: Option<f64>,
}

pub async fn get_video(pool: &PgPool, video_id: &str) -> Result<Option<Video>, sqlx::Error> {
    sqlx::query_as::<_, Video>(
        r#"SELECT
            id,
            user_id,
            title,
            original_filename,
            media_type::TEXT AS media_type,
            file_path,
            thumbnail_path,
            audio_path,
            dubbed_video_path,
            dubbing_metadata,
            duration::FLOAT8 AS duration,
            width,
            height,
            size_bytes,
            format,
            codec,
            frame_rate::FLOAT8 AS frame_rate,
            status::TEXT AS status,
            error_message,
            created_at,
            updated_at
        FROM videos WHERE id = $1"#,
    )
    .bind(video_id)
    .fetch_optional(pool)
    .await
}

pub async fn patch_video_paths(
    pool: &PgPool,
    video_id: &str,
    payload: &PatchPathsPayload,
) -> Result<u64, sqlx::Error> {
    let result = sqlx::query(
        r#"UPDATE videos SET
            dubbed_video_path  = COALESCE($2, dubbed_video_path),
            dubbing_metadata   = COALESCE(
                (COALESCE(dubbing_metadata::jsonb, '{}'::jsonb) || $3::jsonb)::json,
                dubbing_metadata
            ),
            audio_path         = COALESCE($4, audio_path),
            thumbnail_path     = COALESCE($5, thumbnail_path),
            file_path          = COALESCE($6, file_path),
            updated_at         = NOW()
        WHERE id = $1"#,
    )
    .bind(video_id)
    .bind(&payload.dubbed_video_path)
    .bind(&payload.dubbing_metadata)
    .bind(&payload.audio_path)
    .bind(&payload.thumbnail_path)
    .bind(&payload.file_path)
    .execute(pool)
    .await?;
    Ok(result.rows_affected())
}

pub async fn patch_video_status(
    pool: &PgPool,
    video_id: &str,
    payload: &PatchStatusPayload,
) -> Result<u64, sqlx::Error> {
    let result = sqlx::query(
        r#"UPDATE videos SET
            status        = $2::videostatus,
            error_message = COALESCE($3, error_message),
            duration      = COALESCE($4, duration),
            width         = COALESCE($5, width),
            height        = COALESCE($6, height),
            size_bytes    = COALESCE($7, size_bytes),
            format        = COALESCE($8, format),
            codec         = COALESCE($9, codec),
            frame_rate    = COALESCE($10, frame_rate),
            updated_at    = NOW()
        WHERE id = $1"#,
    )
    .bind(video_id)
    .bind(&payload.status)
    .bind(&payload.error_message)
    .bind(payload.duration)
    .bind(payload.width)
    .bind(payload.height)
    .bind(payload.size_bytes)
    .bind(&payload.format)
    .bind(&payload.codec)
    .bind(payload.frame_rate)
    .execute(pool)
    .await?;
    Ok(result.rows_affected())
}
```

- [ ] Write placeholder `src/main.rs` to make `cargo check` happy while other modules are empty:

```rust
mod config;
mod db;
mod ffmpeg;
mod routes;
mod storage;

fn main() {}
```

### ✅ VERIFY Phase 3

```bash
cd /home/eslam-amr/Documents/web-main/media-service && cargo check 2>&1 | grep "^error" | head -10
# Expected: no output (zero errors)
```

Confirm postgres container name and enum types (run only if Postgres container is up):

```bash
# Step 1: confirm actual postgres container name
docker ps --format "{{.Names}}" | grep -i postgres
# Expected: dabljaar_postgres
# If a different name appears, use THAT name in all docker exec commands below
```

```bash
# Step 2: confirm enum names
docker exec dabljaar_postgres psql -U postgres -d dabljaar -c "\dT+" 2>/dev/null | grep -i "video\|media"
# Expected: videostatus and mediatype rows (confirms $2::videostatus cast is correct)
```

```bash
# Step 3 (Issue B): confirm duration/frame_rate column types to verify f64 mapping
docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "\d videos" 2>/dev/null | grep -E "duration|frame_rate|size_bytes"
# Expected output examples:
#   duration    | double precision  → f64 mapping is correct, ::FLOAT8 cast is harmless
#   duration    | numeric           → ::FLOAT8 cast in SELECT is REQUIRED (already added above)
#   frame_rate  | double precision  → correct
#   size_bytes  | bigint            → i64 is correct
# The ::FLOAT8 casts in get_video() above handle BOTH cases safely
```

### 🔁 RETRY Phase 3

If `error[E0412]: cannot find type NaiveDateTime`:
- Confirm `chrono = { version = "0.4", features = ["serde"] }` is in Cargo.toml.

If `error[E0432]: unresolved import sqlx::FromRow`:
- The `sqlx` entry must include `features = ["runtime-tokio-rustls", "postgres", "chrono", "json"]`.

If the enum cast fails at runtime with `invalid input value for enum videostatus`:
```bash
docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "SELECT enum_range(NULL::videostatus);"
# Shows valid values; PENDING/PROCESSING/COMPLETED/FAILED must match exactly (uppercase)
```

If sqlx throws a type mismatch for duration/frame_rate at runtime despite the ::FLOAT8 cast:
```bash
# Check the exact error in docker compose logs media-service
# If it mentions "cannot convert numeric to f64": the cast in get_video() is already present
# Verify the SELECT query in db/mod.rs shows:
#   duration::FLOAT8 AS duration,
#   frame_rate::FLOAT8 AS frame_rate,
# If those lines are missing, re-write the file with the content above
cargo check 2>&1 | grep "^error"
# Expected: no output
```

---

## Phase 4 — Storage Layer (15 min)

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/storage/mod.rs`:

```rust
use anyhow::Result;
use async_trait::async_trait;
use aws_config::{BehaviorVersion, Region};
use aws_sdk_s3::config::Builder as S3ConfigBuilder;
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::presigning::PresigningConfig;
use aws_sdk_s3::Client as S3Client;
use std::path::Path;
use std::time::Duration;

use crate::config::AppConfig;

#[async_trait]
pub trait StorageBackend: Send + Sync {
    async fn upload_file(&self, local_path: &Path, key: &str, content_type: &str) -> Result<String>;
    async fn download_file(&self, key: &str, local_path: &Path) -> Result<bool>;
    async fn delete_object(&self, key: &str) -> Result<bool>;
    async fn get_presigned_url(&self, key: &str, expires_secs: u64) -> Result<String>;
}

pub struct S3Storage {
    client: S3Client,
    bucket: String,
}

impl S3Storage {
    pub async fn new(cfg: &AppConfig) -> Result<Self> {
        std::env::set_var("AWS_ENDPOINT_URL", &cfg.aws_endpoint_url);
        std::env::set_var("AWS_ACCESS_KEY_ID", &cfg.aws_access_key_id);
        std::env::set_var("AWS_SECRET_ACCESS_KEY", &cfg.aws_secret_access_key);
        std::env::set_var("AWS_DEFAULT_REGION", &cfg.aws_default_region);

        let sdk_config = aws_config::defaults(BehaviorVersion::latest())
            .region(Region::new(cfg.aws_default_region.clone()))
            .load()
            .await;

        let s3_cfg = S3ConfigBuilder::from(&sdk_config)
            .endpoint_url(&cfg.aws_endpoint_url)
            .force_path_style(true) // Required for MinIO path-style addressing
            .build();

        let client = S3Client::from_conf(s3_cfg);
        let bucket = cfg.s3_media_bucket.clone();

        match client.head_bucket().bucket(&bucket).send().await {
            Ok(_) => tracing::info!("S3Storage: bucket '{}' found.", bucket),
            Err(_) => {
                tracing::warn!("S3Storage: bucket '{}' not found, creating...", bucket);
                client
                    .create_bucket()
                    .bucket(&bucket)
                    .send()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to create bucket '{}': {}", bucket, e))?;
                tracing::info!("S3Storage: bucket '{}' created.", bucket);
            }
        }

        Ok(Self { client, bucket })
    }
}

#[async_trait]
impl StorageBackend for S3Storage {
    async fn upload_file(&self, local_path: &Path, key: &str, content_type: &str) -> Result<String> {
        let body = ByteStream::from_path(local_path)
            .await
            .map_err(|e| anyhow::anyhow!("Failed to read file {:?}: {}", local_path, e))?;

        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .content_type(content_type)
            .body(body)
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("S3 put_object failed for key '{}': {}", key, e))?;

        tracing::info!("S3Storage: uploaded {:?} → {}", local_path, key);
        Ok(key.to_string())
    }

    async fn download_file(&self, key: &str, local_path: &Path) -> Result<bool> {
        let resp = match self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => {
                tracing::error!("S3 get_object failed for key '{}': {}", key, e);
                return Ok(false);
            }
        };

        if let Some(parent) = local_path.parent() {
            tokio::fs::create_dir_all(parent).await
                .map_err(|e| anyhow::anyhow!("Failed to create dir {:?}: {}", parent, e))?;
        }

        let data = resp.body.collect().await
            .map_err(|e| anyhow::anyhow!("Failed to read S3 body for '{}': {}", key, e))?;

        tokio::fs::write(local_path, data.into_bytes()).await
            .map_err(|e| anyhow::anyhow!("Failed to write file {:?}: {}", local_path, e))?;

        tracing::info!("S3Storage: downloaded {} → {:?}", key, local_path);
        Ok(true)
    }

    async fn delete_object(&self, key: &str) -> Result<bool> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("S3 delete_object failed for key '{}': {}", key, e))?;
        Ok(true)
    }

    async fn get_presigned_url(&self, key: &str, expires_secs: u64) -> Result<String> {
        let presign_cfg = PresigningConfig::expires_in(Duration::from_secs(expires_secs))
            .map_err(|e| anyhow::anyhow!("Failed to build presigning config: {}", e))?;

        let presigned = self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .presigned(presign_cfg)
            .await
            .map_err(|e| anyhow::anyhow!("Failed to generate presigned URL for '{}': {}", key, e))?;

        Ok(presigned.uri().to_string())
    }
}
```

### ✅ VERIFY Phase 4

```bash
cd /home/eslam-amr/Documents/web-main/media-service && cargo check 2>&1 | grep "^error" | head -10
# Expected: no output
```

### 🔁 RETRY Phase 4

If `error[E0432]: unresolved import aws_sdk_s3::presigning`:
- The `aws-sdk-s3` version must be `"1.14"` or newer. Run `cargo tree | grep aws-sdk-s3` to check.

If `cannot find function force_path_style in this scope`:
- Ensure `use aws_sdk_s3::config::Builder as S3ConfigBuilder;` is present as shown.

---

## Phase 5 — FFmpeg Service (20 min)

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/ffmpeg/mod.rs`:

```rust
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;
use tokio::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoMetadata {
    pub duration: f64,
    pub width: Option<i32>,
    pub height: Option<i32>,
    pub format: String,
    pub codec: String,
    pub frame_rate: f64,
    pub size: i64,
    pub audio_present: bool,
}

#[derive(Debug, Deserialize)]
struct FfprobeOutput {
    format: Option<FfprobeFormat>,
    streams: Option<Vec<FfprobeStream>>,
}

#[derive(Debug, Deserialize)]
struct FfprobeFormat {
    duration: Option<String>,
    format_name: Option<String>,
    size: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FfprobeStream {
    codec_type: Option<String>,
    codec_name: Option<String>,
    width: Option<i32>,
    height: Option<i32>,
    duration: Option<String>,
    r_frame_rate: Option<String>,
}

pub struct FFmpegService {
    pub ffprobe_path: String,
    pub ffmpeg_path: String,
}

impl Default for FFmpegService {
    fn default() -> Self {
        Self {
            ffprobe_path: "ffprobe".to_string(),
            ffmpeg_path: "ffmpeg".to_string(),
        }
    }
}

impl FFmpegService {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn get_metadata(&self, file_path: &str) -> Result<VideoMetadata> {
        let output = Command::new(&self.ffprobe_path)
            .args(["-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path])
            .output()
            .await
            .map_err(|e| anyhow!("ffprobe spawn failed: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(anyhow!("ffprobe failed: {}", stderr));
        }

        let data: FfprobeOutput = serde_json::from_slice(&output.stdout)
            .map_err(|e| anyhow!("ffprobe JSON parse error: {}", e))?;

        let fmt = data.format.unwrap_or(FfprobeFormat { duration: None, format_name: None, size: None });
        let streams = data.streams.unwrap_or_default();

        let video_stream = streams.iter().find(|s| s.codec_type.as_deref() == Some("video"));
        let audio_stream = streams.iter().find(|s| s.codec_type.as_deref() == Some("audio"));

        if video_stream.is_none() && audio_stream.is_none() {
            return Err(anyhow!("No video or audio stream found in {}", file_path));
        }

        let mut duration = fmt.duration.as_deref()
            .and_then(|d| d.parse::<f64>().ok()).unwrap_or(0.0);
        if duration == 0.0 {
            duration = video_stream.and_then(|vs| vs.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok()).unwrap_or(0.0);
        }
        if duration == 0.0 {
            duration = audio_stream.and_then(|a| a.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok()).unwrap_or(0.0);
        }

        let width  = video_stream.and_then(|vs| vs.width);
        let height = video_stream.and_then(|vs| vs.height);
        let codec  = video_stream.and_then(|vs| vs.codec_name.clone())
            .or_else(|| audio_stream.and_then(|a| a.codec_name.clone()))
            .unwrap_or_else(|| "unknown".to_string());
        let format = fmt.format_name.unwrap_or_else(|| "unknown".to_string());
        let size   = fmt.size.as_deref().and_then(|s| s.parse::<i64>().ok()).unwrap_or(0);

        let frame_rate = video_stream.and_then(|vs| vs.r_frame_rate.as_deref()).map(|r| {
            let parts: Vec<&str> = r.split('/').collect();
            if parts.len() == 2 {
                let num = parts[0].parse::<f64>().unwrap_or(0.0);
                let den = parts[1].parse::<f64>().unwrap_or(0.0);
                if den != 0.0 { num / den } else { 0.0 }
            } else { 0.0 }
        }).unwrap_or(0.0);

        Ok(VideoMetadata { duration, width, height, format, codec, frame_rate, size,
            audio_present: audio_stream.is_some() })
    }

    pub async fn get_audio_duration(&self, file_path: &str) -> f64 {
        self.get_metadata(file_path).await.map(|m| m.duration).unwrap_or(0.0)
    }

    pub async fn extract_audio(&self, input_path: &str, output_path: &str) -> Result<bool> {
        let output = Command::new(&self.ffmpeg_path)
            .args(["-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg extract_audio spawn failed: {}", e))?;
        Ok(output.status.success())
    }

    pub async fn generate_thumbnail(
        &self, input_path: &str, output_path: &str, time_offset: f64,
    ) -> Result<bool> {
        let offset_str = time_offset.to_string();
        let output = Command::new(&self.ffmpeg_path)
            .args(["-ss", &offset_str, "-i", input_path, "-vframes", "1",
                   "-vf", "scale=640:-1", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg thumbnail spawn failed: {}", e))?;

        if !output.status.success() && time_offset > 0.0 {
            return Box::pin(self.generate_thumbnail(input_path, output_path, 0.0)).await;
        }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }

    pub async fn generate_hls(
        &self, input_path: &str, output_dir: &str, segment_time: u32,
    ) -> Result<bool> {
        let output_playlist = Path::new(output_dir).join("index.m3u8");
        let segment_filename = Path::new(output_dir)
            .join("segment_%03d.ts").to_string_lossy().to_string();
        let output = Command::new(&self.ffmpeg_path)
            .args(["-i", input_path, "-codec:v", "libx264", "-codec:a", "aac",
                   "-map", "0", "-f", "hls",
                   "-hls_time", &segment_time.to_string(),
                   "-hls_list_size", "0",
                   "-hls_segment_filename", &segment_filename,
                   output_playlist.to_str().unwrap_or("index.m3u8")])
            .output().await
            .map_err(|e| anyhow!("ffmpeg generate_hls spawn failed: {}", e))?;
        Ok(output.status.success())
    }
}
```

### ✅ VERIFY Phase 5

```bash
cd /home/eslam-amr/Documents/web-main/media-service && cargo check 2>&1 | grep "^error" | head -10
# Expected: no output
```

### 🔁 RETRY Phase 5

If `error[E0432]: unresolved import tokio::process`:
- Confirm `tokio = { version = "1", features = ["full"] }` in Cargo.toml.
- `tokio::process` is included in `full` — there is no separate `tokio-process` crate for tokio 1.x.

---

## Phase 6 — Routes (30 min)

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/routes/mod.rs`:

```rust
pub mod ffmpeg_ops;
pub mod health;
pub mod videos;
```

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/routes/health.rs`:

```rust
use axum::{http::StatusCode, response::Json};
use serde_json::{json, Value};

pub async fn health_check() -> (StatusCode, Json<Value>) {
    (StatusCode::OK, Json(json!({"status": "ok"})))
}
```

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/routes/videos.rs`:

```rust
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
};
use serde_json::{json, Value};
use std::sync::Arc;

use crate::db::{get_video, patch_video_paths, patch_video_status, PatchPathsPayload, PatchStatusPayload};
use crate::AppState;

pub async fn patch_video_paths_handler(
    State(state): State<Arc<AppState>>,
    Path(video_id): Path<String>,
    Json(payload): Json<PatchPathsPayload>,
) -> (StatusCode, Json<Value>) {
    match patch_video_paths(&state.pool, &video_id, &payload).await {
        Ok(rows) if rows > 0 => (
            StatusCode::OK,
            Json(json!({"status": "ok", "rows_affected": rows, "video_id": video_id})),
        ),
        Ok(_) => (
            StatusCode::NOT_FOUND,
            Json(json!({"status": "error", "message": "Video not found"})),
        ),
        Err(e) => {
            tracing::error!("patch_video_paths DB error for {}: {}", video_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        }
    }
}

pub async fn patch_video_status_handler(
    State(state): State<Arc<AppState>>,
    Path(video_id): Path<String>,
    Json(payload): Json<PatchStatusPayload>,
) -> (StatusCode, Json<Value>) {
    match patch_video_status(&state.pool, &video_id, &payload).await {
        Ok(rows) if rows > 0 => (
            StatusCode::OK,
            Json(json!({"status": "ok", "rows_affected": rows, "video_id": video_id})),
        ),
        Ok(_) => (
            StatusCode::NOT_FOUND,
            Json(json!({"status": "error", "message": "Video not found"})),
        ),
        Err(e) => {
            tracing::error!("patch_video_status DB error for {}: {}", video_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        }
    }
}

pub async fn get_video_handler(
    State(state): State<Arc<AppState>>,
    Path(video_id): Path<String>,
) -> (StatusCode, Json<Value>) {
    match get_video(&state.pool, &video_id).await {
        Ok(Some(video)) => (StatusCode::OK, Json(json!(video))),
        Ok(None) => (StatusCode::NOT_FOUND, Json(json!({"status": "error", "message": "Video not found"}))),
        Err(e) => {
            tracing::error!("get_video DB error for {}: {}", video_id, e);
            (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"status": "error", "message": e.to_string()})))
        }
    }
}
```

- [ ] Write `/home/eslam-amr/Documents/web-main/media-service/src/routes/ffmpeg_ops.rs`:

```rust
use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;
use tempfile::TempDir;

use crate::AppState;

#[derive(Deserialize)]
pub struct FileKeyQuery {
    pub path: String,
}

pub async fn get_metadata_handler(
    State(state): State<Arc<AppState>>,
    Query(params): Query<FileKeyQuery>,
) -> (StatusCode, Json<Value>) {
    let tmp = match TempDir::new() {
        Ok(t) => t,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    };
    let local_path = tmp.path().join("input_file");
    match state.storage.download_file(&params.path, &local_path).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({"error": "File not found in storage"}))),
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
    match state.ffmpeg.get_metadata(local_path.to_str().unwrap_or("")).await {
        Ok(meta) => (StatusCode::OK, Json(json!(meta))),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
}

#[derive(Deserialize)]
pub struct ExtractAudioRequest {
    pub input_key: String,
    pub output_key: String,
}

pub async fn extract_audio_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<ExtractAudioRequest>,
) -> (StatusCode, Json<Value>) {
    let tmp = match TempDir::new() {
        Ok(t) => t,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    };
    let input_local  = tmp.path().join("input");
    let output_local = tmp.path().join("output.mp3");
    if let Err(e) = state.storage.download_file(&req.input_key, &input_local).await {
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()})));
    }
    match state.ffmpeg.extract_audio(
        input_local.to_str().unwrap_or(""),
        output_local.to_str().unwrap_or(""),
    ).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": "ffmpeg extract_audio failed"}))),
        Err(e)   => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
    match state.storage.upload_file(&output_local, &req.output_key, "audio/mpeg").await {
        Ok(key) => (StatusCode::OK, Json(json!({"status": "ok", "key": key}))),
        Err(e)  => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
}

#[derive(Deserialize)]
pub struct ThumbnailRequest {
    pub input_key: String,
    pub output_key: String,
    pub time_offset: Option<f64>,
}

pub async fn generate_thumbnail_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<ThumbnailRequest>,
) -> (StatusCode, Json<Value>) {
    let tmp = match TempDir::new() {
        Ok(t) => t,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    };
    let input_local  = tmp.path().join("input");
    let output_local = tmp.path().join("thumb.jpg");
    let time_offset  = req.time_offset.unwrap_or(1.0_f64);
    if let Err(e) = state.storage.download_file(&req.input_key, &input_local).await {
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()})));
    }
    match state.ffmpeg.generate_thumbnail(
        input_local.to_str().unwrap_or(""),
        output_local.to_str().unwrap_or(""),
        time_offset,
    ).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": "ffmpeg thumbnail failed"}))),
        Err(e)   => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
    match state.storage.upload_file(&output_local, &req.output_key, "image/jpeg").await {
        Ok(key) => (StatusCode::OK, Json(json!({"status": "ok", "key": key}))),
        Err(e)  => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
}

#[derive(Deserialize)]
pub struct PresignRequest {
    pub key: String,
    pub expires_secs: Option<u64>,
}

pub async fn get_presigned_url_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<PresignRequest>,
) -> (StatusCode, Json<Value>) {
    let expires = req.expires_secs.unwrap_or(3600);
    match state.storage.get_presigned_url(&req.key, expires).await {
        Ok(url) => (StatusCode::OK, Json(json!({"url": url}))),
        Err(e)  => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
}
```

- [ ] Replace `/home/eslam-amr/Documents/web-main/media-service/src/main.rs` with:

```rust
mod config;
mod db;
mod ffmpeg;
mod routes;
mod storage;

use std::sync::Arc;

use axum::{
    routing::{get, patch, post},
    Router,
};
use dotenvy::dotenv;
use sqlx::PgPool;
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use tracing_subscriber::EnvFilter;

use config::AppConfig;
use ffmpeg::FFmpegService;
use storage::{S3Storage, StorageBackend};

pub struct AppState {
    pub pool: PgPool,
    pub storage: Arc<dyn StorageBackend>,
    pub ffmpeg: FFmpegService,
    pub config: AppConfig,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _ = dotenv();

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::from_default_env()
                .add_directive("media_service=info".parse()?),
        )
        .init();

    let cfg = AppConfig::from_env().map_err(|e| anyhow::anyhow!(e))?;
    tracing::info!("Starting media-service on port {}", cfg.port);

    let pool = db::create_pool(&cfg.database_url).await?;
    tracing::info!("Database pool created.");

    let storage = S3Storage::new(&cfg).await?;
    tracing::info!("S3Storage initialized, bucket = {}", cfg.s3_media_bucket);

    let state = Arc::new(AppState {
        pool,
        storage: Arc::new(storage),
        ffmpeg: FFmpegService::new(),
        config: cfg.clone(),
    });

    let app = Router::new()
        .route("/health",               get(routes::health::health_check))
        .route("/videos/:id/paths",     patch(routes::videos::patch_video_paths_handler))
        .route("/videos/:id/status",    patch(routes::videos::patch_video_status_handler))
        .route("/videos/:id",           get(routes::videos::get_video_handler))
        .route("/ffmpeg/metadata",      get(routes::ffmpeg_ops::get_metadata_handler))
        .route("/ffmpeg/extract-audio", post(routes::ffmpeg_ops::extract_audio_handler))
        .route("/ffmpeg/thumbnail",     post(routes::ffmpeg_ops::generate_thumbnail_handler))
        .route("/storage/presign",      post(routes::ffmpeg_ops::get_presigned_url_handler))
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive())
        .with_state(state);

    let bind_addr = format!("0.0.0.0:{}", cfg.port);
    tracing::info!("Listening on {}", bind_addr);
    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
```

### ✅ VERIFY Phase 6

```bash
# Step 1: compilation check
cd /home/eslam-amr/Documents/web-main/media-service && cargo build 2>&1 | grep "^error" | head -20
# Expected: no output

cargo build 2>&1 | tail -2
# Expected: Finished `dev` profile [unoptimized + debuginfo] target(s) in Xs
```

```bash
# Step 1b (Issue A): check if Postgres is reachable on host before attempting cargo run
pg_isready -h localhost -p 5433 -U postgres 2>/dev/null
# Expected: localhost:5433 - accepting connections  (exit code 0)
# If NOT reachable (exit code 1 or 2): SKIP Step 2, proceed directly to Phase 7
# The Docker build in Phase 8 is the real runtime test when DB is not on host
echo "pg_isready exit code: $?"
# 0 = reachable → run Step 2
# non-zero = not reachable → skip Step 2, note it and move to Phase 7
```

```bash
# Step 2: runtime smoke test — only run if Step 1b showed exit code 0
# Catches panics that cargo build does not catch
cd /home/eslam-amr/Documents/web-main/media-service
DATABASE_URL=postgres://postgres:postgres@localhost:5433/dabljaar \
AWS_ENDPOINT_URL=http://localhost:9000 \
S3_MEDIA_BUCKET=dablaja-videos \
cargo run &
CARGO_PID=$!
sleep 5

# Check process is still alive (did not panic at startup)
kill -0 $CARGO_PID 2>/dev/null && echo "Process alive — good" || echo "PROCESS DIED — read cargo run output above for panic"

curl -s http://localhost:8001/health
# Expected: {"status":"ok"}
# If connection refused: process died at startup — read cargo run output for the panic message

kill $CARGO_PID 2>/dev/null
wait $CARGO_PID 2>/dev/null
```

### 🔁 RETRY Phase 6

If `error[E0412]: cannot find type TempDir`:
- Confirm `tempfile = "3"` is in Cargo.toml and `use tempfile::TempDir;` is at top of `ffmpeg_ops.rs`.

If `error[E0277]: the trait StorageBackend is not object-safe`:
- Ensure `#[async_trait]` is applied to both the trait definition and every impl block in `storage/mod.rs`.

If `error: unresolved import crate::routes::...`:
- Ensure all three entries in `routes/mod.rs` match file names exactly: `health`, `videos`, `ffmpeg_ops`.

If cargo run panics with `DATABASE_URL must be set`:
- The env var prefix in the command is correct. Check shell is reading it:
  ```bash
  echo $DATABASE_URL
  # If empty: export DATABASE_URL=postgres://postgres:postgres@localhost:5433/dabljaar first
  ```

---

## Phase 7 — Break Python Coupling (30 min)

### Pre-check 7.0 — Count engine_u blocks before editing (Issue C)

```bash
# MUST run this before making any edits
grep -n "engine_u, SessionLocal_u" \
  /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# If 1 line appears: only one block to replace — follow 7a as written
# If 2+ lines appear: EACH line is a separate ORM write block
#   → apply the httpx replacement to ALL of them, not just the first
#   → each block has its own local variables (video_id, job_id, etc.) — adjust the payload accordingly
```

### 7a — Modify `app/jobs/tasks/pipeline.py`

Find the block inside `tts_combine_results` starting with
`engine_u, SessionLocal_u = BaseJobTask._make_db()` (approximately line 756):

```python
                engine_u, SessionLocal_u = BaseJobTask._make_db()
                try:
                    with SessionLocal_u() as db:
                        up_video = db.get(MediaVideo, video_id)
                        if up_video is not None:
                            if dubbed_video_key:
                                up_video.dubbed_video_path = dubbed_video_key
                            existing_meta = (
                                dict(up_video.dubbing_metadata)
                                if up_video.dubbing_metadata
                                else {}
                            )
                            up_video.dubbing_metadata = {
                                **existing_meta,
                                "tts_job_id": job_id,
                                "media_type": media_type_value,
                                "combined_audio_key": combined_minio_key,
                                "combined_audio_url": combined_audio_url,
                                "dubbed_video_key": dubbed_video_key,
                                "dubbed_video_url": dubbed_video_url,
                                "updated_at": _utcnow().isoformat(),
                            }
                            db.commit()
                finally:
                    engine_u.dispose()
```

Replace the entire block (from `engine_u, SessionLocal_u = ...` through `engine_u.dispose()`) with:

```python
                import httpx as _httpx
                import os as _os
                _media_svc_url = _os.getenv(
                    "MEDIA_SERVICE_URL", "http://media-service:8001"
                )
                _patch_payload = {}
                if dubbed_video_key:
                    _patch_payload["dubbed_video_path"] = dubbed_video_key
                _patch_payload["dubbing_metadata"] = {
                    "tts_job_id": job_id,
                    "media_type": media_type_value,
                    "combined_audio_key": combined_minio_key,
                    "combined_audio_url": combined_audio_url,
                    "dubbed_video_key": dubbed_video_key,
                    "dubbed_video_url": dubbed_video_url,
                    "updated_at": _utcnow().isoformat(),
                }
                try:
                    with _httpx.Client(timeout=10.0) as _client:
                        _resp = _client.patch(
                            f"{_media_svc_url}/videos/{video_id}/paths",
                            json=_patch_payload,
                        )
                        _resp.raise_for_status()
                        logger.info(
                            "[TTS] media-service PATCH /videos/%s/paths → %s",
                            video_id, _resp.status_code,
                        )
                except Exception as _http_exc:
                    logger.error(
                        "[TTS] Failed to PATCH media-service for video %s: %s",
                        video_id, _http_exc,
                    )
                    raise
```

**Critical indentation note:** The replacement block must use the exact same indentation as the
block it replaces. Get the exact space count with:

```bash
python3 -c "
with open('/home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py') as f:
    for i, line in enumerate(f, 1):
        if 'engine_u, SessionLocal_u' in line:
            print(f'Line {i}: indent={len(line) - len(line.lstrip())} spaces')
            break
"
# Use that exact number of leading spaces for EVERY line in the replacement block
```

### 7b — httpx is already installed ✓ (no action needed)

> **Confirmed by Claude Code review:** The backend uses `pyproject.toml`, not `requirements.txt`.
> There is no `requirements.txt` file. `httpx>=0.28.1` is already declared in `pyproject.toml`
> and is already installed in the backend container. **Skip this step entirely.**

```bash
# Just confirm httpx is present — no installation needed
grep -i "httpx" /home/eslam-amr/Documents/web-main/backend/pyproject.toml
# Expected: httpx>=0.28.1 (or similar version line)
# If found: nothing to do, proceed to 7c
```

### 7c — Do NOT touch `app/dubbing/service.py`

`dubbing/service.py` still uses `FFmpegService` and `get_storage_service()` directly.
These stay in Python for this phase. No changes now.

### 7d — Do NOT touch `app/stt/router.py`

`stt/router.py` only writes to the `Job` table (not `videos`). No changes needed.

### 7e — Add `MEDIA_SERVICE_URL` to docker-compose Celery workers

Under `celery-worker-ai` → `environment:`:
```yaml
      MEDIA_SERVICE_URL: http://media-service:8001
```

Under `celery-worker-media` → `environment:`:
```yaml
      MEDIA_SERVICE_URL: http://media-service:8001
```

### ✅ VERIFY Phase 7

```bash
grep -n "httpx\|MEDIA_SERVICE_URL\|media-service" \
  /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py | head -10
# Expected: lines showing _httpx import, MEDIA_SERVICE_URL env var read, and PATCH call

grep -n "MEDIA_SERVICE_URL" /home/eslam-amr/Documents/web-main/docker-compose.yml
# Expected: 2 lines — one per Celery worker

python3 -c "
import ast
ast.parse(open('/home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py').read())
print('syntax OK')
"
# Expected: syntax OK
```

### 🔁 RETRY Phase 7

If syntax check fails:
```bash
python3 -m py_compile /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# Shows exact line number — fix indentation in the replacement block
```

If Pre-check 7.0 found multiple `engine_u` blocks and only the first was replaced:
```bash
# Find all remaining unreplaced blocks
grep -n "engine_u, SessionLocal_u" \
  /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# Apply the same httpx replacement pattern to each remaining block
# Confirm count reaches zero:
grep -c "engine_u, SessionLocal_u" \
  /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# Expected: 0
```

If httpx missing at runtime in Celery container:
```bash
docker exec dabljaar_worker_ai pip install httpx
```

---

## Phase 8 — Dockerfile (10 min)

- [ ] Create `/home/eslam-amr/Documents/web-main/media-service/Dockerfile`:

```dockerfile
# ── Stage 1: Build ────────────────────────────────────────────────────────────
# rust:1-slim-bookworm tracks latest stable — avoids "requires rustc 1.80+" errors
# from transitive aws-sdk deps that have bumped MSRV beyond 1.78
FROM rust:1-slim-bookworm AS builder

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache dependency compilation: copy manifests first, build dummy binary
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release 2>&1 || true
RUN rm -f src/main.rs

# Build real binary
COPY src ./src
RUN touch src/main.rs
RUN cargo build --release

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/release/media-service ./media-service
RUN mkdir -p /tmp/media-service

EXPOSE 8001
CMD ["./media-service"]
```

### ✅ VERIFY Phase 8

```bash
grep "FROM\|RUN\|CMD\|EXPOSE" /home/eslam-amr/Documents/web-main/media-service/Dockerfile
# Expected lines (in order):
# FROM rust:1-slim-bookworm AS builder
# RUN apt-get update ... pkg-config libssl-dev
# RUN cargo build --release
# FROM debian:bookworm-slim AS runtime
# RUN apt-get update ... ffmpeg libssl3 ca-certificates
# EXPOSE 8001
# CMD ["./media-service"]
```

```bash
# Full build test (~5 min first time — downloads all Rust deps)
docker build -t media-service-local /home/eslam-amr/Documents/web-main/media-service/ 2>&1 | tail -5
# Expected: Successfully built <hash>  OR  naming to docker.io/library/media-service-local done
```

### 🔁 RETRY Phase 8

If `error: could not find Cargo.lock`:
```bash
cd /home/eslam-amr/Documents/web-main/media-service && cargo generate-lockfile
```

If runtime binary fails with `error while loading shared libraries: libssl.so.3`:
- Confirm `libssl3` (NOT `libssl-dev`) is in the runtime stage `apt-get install` line.

---

## Phase 9 — Docker Compose (10 min)

> **Confirmed by Claude Code review:** MinIO in this repo DOES have a healthcheck
> (`mc ready local` at lines 51–56 of docker-compose.yml). Use `service_healthy` for minio.
> The pre-check step has been removed — the correct value is hardcoded below.

- [ ] Add `media-service` after the `backend:` block and before `frontend:`:

```yaml
  # Media Microservice (Rust + Axum)
  media-service:
    build:
      context: ./media-service
      dockerfile: Dockerfile
    container_name: dabljaar_media_service
    environment:
      DATABASE_URL: postgres://postgres:postgres@postgres:5432/dabljaar
      AWS_ENDPOINT_URL: http://minio:9000
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
      AWS_DEFAULT_REGION: us-east-1
      S3_MEDIA_BUCKET: ${S3_MEDIA_BUCKET:-dablaja-videos}
      PORT: "8001"
      RUST_LOG: info
    ports:
      - "8001:8001"
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - dabljaar_network
```

- [ ] Add `media-service` to `depends_on` of both Celery workers:

```yaml
      media-service:
        condition: service_started
```

### ✅ VERIFY Phase 9

```bash
docker compose -f /home/eslam-amr/Documents/web-main/docker-compose.yml config --services 2>&1 | sort
# Expected list includes: backend, celery-worker-ai, celery-worker-media,
#   flower, frontend, media-service, minio, postgres, redis

grep -n "MEDIA_SERVICE_URL" /home/eslam-amr/Documents/web-main/docker-compose.yml
# Expected: 2 lines — one under celery-worker-ai, one under celery-worker-media

python3 -c "
import yaml
yaml.safe_load(open('/home/eslam-amr/Documents/web-main/docker-compose.yml'))
print('YAML valid')
"
# Expected: YAML valid
```

### 🔁 RETRY Phase 9

If YAML parse error:
```bash
python3 -c "
import yaml
try:
    yaml.safe_load(open('/home/eslam-amr/Documents/web-main/docker-compose.yml'))
    print('YAML valid')
except yaml.YAMLError as e:
    print(e)
"
# Shows exact line number — fix indentation
# Common pitfall: mixing KEY: value and - KEY=value in the same environment: block
# Use only KEY: value format (matches existing services)
```

---

## Phase 10 — Full End-to-End Test (15 min)

### 10a — Start services

```bash
cd /home/eslam-amr/Documents/web-main
docker compose up -d --build media-service
```

Wait for build (~3–5 min first time). Then:

```bash
docker compose logs media-service --tail 20
# Expected — must contain all three lines:
# "Starting media-service on port 8001"
# "Database pool created."
# "S3Storage initialized, bucket = dablaja-videos"
```

### 10b — Health check

```bash
curl -s http://localhost:8001/health
# Expected: {"status":"ok"}
```

### 10c — Database connectivity

```bash
# Export VIDEO_ID so it is available in all subsequent steps
export VIDEO_ID=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -tAc "SELECT id FROM videos LIMIT 1;" 2>/dev/null | tr -d '[:space:]')
echo "VIDEO_ID=${VIDEO_ID}"
# Expected: VIDEO_ID=<some-uuid-string>
# If "VIDEO_ID=" (empty): videos table has no rows → skip to 10f
```

```bash
curl -s http://localhost:8001/videos/${VIDEO_ID}
# Expected: JSON object with id, title, status, media_type, file_path, created_at, etc.
```

### 10d — PATCH /videos/:id/status

```bash
curl -s -X PATCH http://localhost:8001/videos/${VIDEO_ID}/status \
  -H "Content-Type: application/json" \
  -d '{"status":"COMPLETED"}'
# Expected: {"rows_affected":1,"status":"ok","video_id":"<VIDEO_ID>"}
```

```bash
docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "SELECT id, status, updated_at FROM videos WHERE id='${VIDEO_ID}';" 2>/dev/null
# Expected: status = COMPLETED, updated_at within the last minute
```

### 10e — PATCH /videos/:id/paths

```bash
curl -s -X PATCH http://localhost:8001/videos/${VIDEO_ID}/paths \
  -H "Content-Type: application/json" \
  -d '{"dubbed_video_path":"test/dubbed.mp4","dubbing_metadata":{"test":true}}'
# Expected: {"rows_affected":1,"status":"ok","video_id":"<VIDEO_ID>"}
```

```bash
docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "SELECT id, dubbed_video_path, dubbing_metadata FROM videos WHERE id='${VIDEO_ID}';" 2>/dev/null
# Expected: dubbed_video_path = test/dubbed.mp4, dubbing_metadata = {"test": true}
```

### 10f — Presigned URL (requires MinIO running)

```bash
FILE_KEY=$(docker exec dabljaar_postgres psql -U postgres -d dabljaar -tAc \
  "SELECT file_path FROM videos WHERE file_path IS NOT NULL LIMIT 1;" 2>/dev/null | tr -d '[:space:]')

if [ -n "$FILE_KEY" ]; then
  curl -s -X POST http://localhost:8001/storage/presign \
    -H "Content-Type: application/json" \
    -d "{\"key\": \"${FILE_KEY}\", \"expires_secs\": 3600}"
  # Expected: {"url":"http://localhost:9000/dablaja-videos/<key>?X-Amz-..."}
else
  echo "No files in storage yet — skip this step"
fi
```

### 10g — Confirm Python backend unaffected

```bash
docker compose ps
# Expected: all services show "running" or "Up"

curl -s http://localhost:8000/health 2>/dev/null || \
  curl -s http://localhost:8000/api/health 2>/dev/null
# Expected: 200 JSON response from Python backend

docker compose logs celery-worker-ai --tail 10 | grep -i "error\|exception" | head -5
# Expected: no critical errors
```

### ✅ VERIFY Phase 10

```bash
curl -sf http://localhost:8001/health && echo " ← media-service OK"
# Expected: {"status":"ok"} ← media-service OK
echo "Exit code: $?"
# Expected: 0
```

### 🔁 RETRY Phase 10

If container exits immediately:
```bash
docker compose logs media-service 2>&1 | head -30
# "DATABASE_URL must be set"  → missing env var in docker-compose.yml
# "connection refused" postgres → wait 10s, retry
# "Failed to create bucket"  → minio not reachable: docker compose ps minio
```

If PATCH returns `invalid input value for enum videostatus`:
```bash
docker exec dabljaar_postgres psql -U postgres -d dabljaar \
  -c "SELECT enum_range(NULL::videostatus);"
# Valid values are uppercase: PENDING, PROCESSING, COMPLETED, FAILED
# Send uppercase in PATCH payload
```

If PATCH returns 404 for a known good video ID:
- Confirm the ID includes all hyphens — the column is VARCHAR(36), not a native UUID.

---

## Phase 11 — Cleanup (5 min)

- [ ] Check if `MediaVideo` import is still needed in `pipeline.py`:

```bash
grep -n "MediaVideo" /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# If lines remain OTHER THAN the import: leave it
# stt_transcribe still reads video.file_path/audio_path — read-only, no change needed
```

- [ ] Confirm `aioboto3` stays in backend requirements:

```bash
grep -rn "aioboto3\|get_storage_service" \
  /home/eslam-amr/Documents/web-main/backend/app/dubbing/service.py | head -5
# Expected: lines showing aioboto3/get_storage_service usage
# Do NOT remove aioboto3 — dubbing still needs it
```

- [ ] Future cleanup (after full migration — NOT tonight):

```
- backend/app/media/ffmpeg_service.py    → remove when Python callers use /ffmpeg/* endpoints
- backend/app/media/storage.py           → remove when Python callers use /storage/* endpoints
- aioboto3, botocore in pyproject.toml → remove when storage.py is gone
- engine_v / SessionLocal_v reads in pipeline.py → replace with GET /videos/:id calls
  (note: after Phase 7 the write block using engine_u is gone; the remaining read block uses engine_v)
```

- [ ] Final git status check:

```bash
cd /home/eslam-amr/Documents/web-main
git status 2>/dev/null
# Expected:
#   modified: docker-compose.yml
#   modified: backend/app/jobs/tasks/pipeline.py
#   untracked: media-service/
```

### ✅ VERIFY Phase 11

```bash
docker compose -f /home/eslam-amr/Documents/web-main/docker-compose.yml ps
# Expected: all services Up, none Exited

curl -sf http://localhost:8001/health && echo " — media-service OK"
# Expected: {"status":"ok"} — media-service OK

find /home/eslam-amr/Documents/web-main/backend/app -name "*.py" \
  -exec python3 -m py_compile {} \; 2>&1 | head -10
# Expected: no output (all Python files parse cleanly)
```

### 🔁 RETRY Phase 11

If `py_compile` errors on `pipeline.py`:
```bash
python3 -m py_compile /home/eslam-amr/Documents/web-main/backend/app/jobs/tasks/pipeline.py
# Fix the indentation at the shown line number (Phase 7 replacement block)
```

---

## Appendix — File Tree After Completion

```
/home/eslam-amr/Documents/web-main/
├── backend/                                 (modified)
│   └── app/jobs/tasks/pipeline.py           ← PATCH call replaces direct ORM write
├── media-service/                           (NEW)
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── Dockerfile
│   ├── .env                                 (local dev only, not committed)
│   └── src/
│       ├── main.rs
│       ├── config/mod.rs
│       ├── db/mod.rs
│       ├── ffmpeg/mod.rs
│       ├── routes/
│       │   ├── mod.rs
│       │   ├── health.rs
│       │   ├── videos.rs
│       │   └── ffmpeg_ops.rs
│       └── storage/mod.rs
└── docker-compose.yml                       ← media-service added, workers updated
```

## Appendix — API Contract

| Method | Path | Caller | Purpose |
|--------|------|--------|---------|
| GET | `/health` | monitoring | liveness check |
| GET | `/videos/:id` | debugging | read video row |
| PATCH | `/videos/:id/paths` | celery-worker-ai | write `dubbed_video_path`, `dubbing_metadata` |
| PATCH | `/videos/:id/status` | celery-worker-media | write `status`, `duration`, `width`, etc. |
| GET | `/ffmpeg/metadata?path=` | future Python callers | probe file via ffprobe |
| POST | `/ffmpeg/extract-audio` | future Python callers | extract MP3 audio |
| POST | `/ffmpeg/thumbnail` | future Python callers | generate JPEG thumbnail |
| POST | `/storage/presign` | future Python callers | generate presigned URL |

## Appendix — What Was Fixed vs Original Plan

| Issue | Where | Fix Applied |
|-------|-------|-------------|
| A — runtime smoke test crashes if DB not on host | Phase 6 VERIFY | Added `pg_isready` check before `cargo run`; skip instruction if DB unreachable |
| B — duration/frame_rate could be NUMERIC not FLOAT8 | Phase 3 db/mod.rs | Added `::FLOAT8` casts in `get_video()` SELECT (harmless for `double precision` too) |
| C — multiple `engine_u` blocks may exist in pipeline.py | Phase 7 | Added Pre-check 7.0 to count blocks before editing; RETRY confirms count reaches 0 |
| D — Phase 7b tried to write `requirements.txt` which does not exist | Phase 7b | **REMOVED** — backend uses `pyproject.toml`; `httpx>=0.28.1` already present |
| E — Phase 9 minio condition was `service_started` but minio has a healthcheck | Phase 9 | Changed to `service_healthy`; pre-check step removed |
| F — Phase 11 cleanup note referenced `requirements.txt` | Phase 11 | Changed to `pyproject.toml` |
| G — Phase 11 cleanup note said `engine_u` for the remaining read block | Phase 11 | Corrected to `engine_v` — the write block (engine_u) is removed in Phase 7; the leftover read block uses engine_v |
| H — Phase 9 media-service depends_on included redis unnecessarily | Phase 9 | Removed redis dependency — the Rust service has no Redis client |
| I — dubbing_metadata column is JSON not JSONB; sqlx binds as JSONB causing type mismatch | Phase 3 db/mod.rs | Used jsonb merge pattern: `COALESCE((COALESCE(dubbing_metadata::jsonb,'{}'::jsonb) \|\| $3::jsonb)::json, dubbing_metadata)` — preserves existing keys AND handles the JSON/JSONB type difference |
| J — Dockerfile pinned to `rust:1.78` which is below MSRV of aws-sdk transitive deps | Phase 8 Dockerfile | Changed to `rust:1-slim-bookworm` to always track latest stable |
