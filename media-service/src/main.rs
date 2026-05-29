mod config;
mod db;
mod ffmpeg;
mod routes;
mod storage;

use std::sync::Arc;

use axum::{
    routing::{delete, get, patch, post},
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
        .route("/videos",              get(routes::videos::list_videos_handler))
        .route("/videos",              post(routes::videos::create_video_handler))
        .route("/videos/:id/paths",     patch(routes::videos::patch_video_paths_handler))
        .route("/videos/:id/status",    patch(routes::videos::patch_video_status_handler))
        .route("/videos/:id",           get(routes::videos::get_video_handler))
        .route("/videos/:id",           delete(routes::videos::delete_video_handler))
        .route("/ffmpeg/metadata",      get(routes::ffmpeg_ops::get_metadata_handler))
        .route("/ffmpeg/extract-audio", post(routes::ffmpeg_ops::extract_audio_handler))
        .route("/ffmpeg/thumbnail",     post(routes::ffmpeg_ops::generate_thumbnail_handler))
        .route("/ffmpeg/hls",           post(routes::ffmpeg_ops::hls_handler))
        .route("/ffmpeg/dub",           post(routes::ffmpeg_ops::dub_handler))
        .route("/storage/presign",      post(routes::ffmpeg_ops::get_presigned_url_handler))
        .route("/storage/*key",         delete(routes::storage_ops::delete_file_handler))
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive())
        .with_state(state);

    let bind_addr = format!("0.0.0.0:{}", cfg.port);
    tracing::info!("Listening on {}", bind_addr);
    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
