use anyhow::Result;
use async_trait::async_trait;
use axum::{
    body::Body,
    http::{Request, StatusCode},
    routing::{get, post},
    Router,
};
use http_body_util::BodyExt;
use std::{path::Path, sync::Arc};
use tower::ServiceExt;

use crate::{
    config::AppConfig,
    ffmpeg::FFmpegService,
    routes::ffmpeg_ops::{
        extract_audio_handler, generate_thumbnail_handler,
        get_metadata_handler, get_presigned_url_handler,
    },
    storage::{PresignMethod, StorageBackend},
    AppState,
};

// ── Mock StorageBackend ───────────────────────────────────────────────────────

struct MockStorage {
    download_ok: bool,
    download_err: Option<String>,
    upload_key: String,
    presign_url: String,
    presign_err: Option<String>,
}

impl MockStorage {
    fn always_ok(presign_url: &str) -> Self {
        Self {
            download_ok: true,
            download_err: None,
            upload_key: "uploaded-key".into(),
            presign_url: presign_url.into(),
            presign_err: None,
        }
    }

    fn download_io_error(msg: &str) -> Self {
        Self {
            download_ok: false,
            download_err: Some(msg.into()),
            upload_key: "".into(),
            presign_url: "".into(),
            presign_err: None,
        }
    }

    fn file_not_in_storage() -> Self {
        Self {
            download_ok: false,
            download_err: None,
            upload_key: "".into(),
            presign_url: "".into(),
            presign_err: None,
        }
    }

    fn presign_io_error(msg: &str) -> Self {
        Self {
            download_ok: true,
            download_err: None,
            upload_key: "".into(),
            presign_url: "".into(),
            presign_err: Some(msg.into()),
        }
    }
}

#[async_trait]
impl StorageBackend for MockStorage {
    async fn upload_file(&self, _path: &Path, _key: &str, _ct: &str) -> Result<String> {
        Ok(self.upload_key.clone())
    }

    async fn download_file(&self, _key: &str, _local: &Path) -> Result<bool> {
        if let Some(ref e) = self.download_err {
            return Err(anyhow::anyhow!("{}", e));
        }
        Ok(self.download_ok)
    }

    async fn list_prefix(&self, _prefix: &str) -> Result<Vec<String>> {
        Ok(vec![])
    }

    async fn delete_object(&self, _key: &str) -> Result<bool> {
        Ok(true)
    }

    async fn delete_prefix(&self, _prefix: &str) -> Result<u64> {
        Ok(0)
    }

    async fn get_presigned_url(
        &self,
        _key: &str,
        _expires: u64,
        _method: PresignMethod,
        _content_type: Option<&str>,
    ) -> Result<String> {
        if let Some(ref e) = self.presign_err {
            return Err(anyhow::anyhow!("{}", e));
        }
        Ok(self.presign_url.clone())
    }
}

// ── Test helpers ──────────────────────────────────────────────────────────────

fn test_config() -> AppConfig {
    AppConfig {
        database_url: "postgres://fake@localhost/fake".into(),
        aws_endpoint_url: "http://localhost:9000".into(),
        aws_access_key_id: "test".into(),
        aws_secret_access_key: "test".into(),
        aws_default_region: "us-east-1".into(),
        s3_media_bucket: "test-bucket".into(),
        port: 8001,
    }
}

fn make_state(storage: MockStorage) -> Arc<AppState> {
    // connect_lazy builds the pool without actually connecting — safe for
    // handlers that never execute a DB query.
    let pool = sqlx::postgres::PgPoolOptions::new()
        .connect_lazy("postgres://fake@localhost/fakedb")
        .expect("lazy pool construction must not fail");
    Arc::new(AppState {
        pool,
        storage: Arc::new(storage),
        ffmpeg: FFmpegService::new(),
        config: test_config(),
    })
}

async fn body_json(resp: axum::response::Response) -> serde_json::Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

// ── /storage/presign ──────────────────────────────────────────────────────────

#[tokio::test]
async fn test_presign_returns_200_with_url_field() {
    let expected = "https://s3.example.com/presigned/video.mp4?sig=abc";
    let app = Router::new()
        .route("/storage/presign", post(get_presigned_url_handler))
        .with_state(make_state(MockStorage::always_ok(expected)));

    let req = Request::builder()
        .method("POST")
        .uri("/storage/presign")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"key":"videos/clip.mp4","expires_secs":3600}"#))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["url"], expected);
}

#[tokio::test]
async fn test_presign_accepts_request_without_expires_secs() {
    // expires_secs is optional — its absence must not produce 422
    let app = Router::new()
        .route("/storage/presign", post(get_presigned_url_handler))
        .with_state(make_state(MockStorage::always_ok("https://default-expiry.example.com")));

    let req = Request::builder()
        .method("POST")
        .uri("/storage/presign")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"key":"videos/clip.mp4"}"#))
        .unwrap();

    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::OK);
}

#[tokio::test]
async fn test_presign_returns_500_and_propagates_error_message() {
    let app = Router::new()
        .route("/storage/presign", post(get_presigned_url_handler))
        .with_state(make_state(MockStorage::presign_io_error("S3 connection refused")));

    let req = Request::builder()
        .method("POST")
        .uri("/storage/presign")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"key":"videos/clip.mp4"}"#))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    let body = body_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("S3 connection refused"));
}

#[tokio::test]
async fn test_presign_returns_422_when_key_field_absent() {
    let app = Router::new()
        .route("/storage/presign", post(get_presigned_url_handler))
        .with_state(make_state(MockStorage::always_ok("http://x.com")));

    let req = Request::builder()
        .method("POST")
        .uri("/storage/presign")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"expires_secs":60}"#)) // "key" is required but absent
        .unwrap();

    assert_eq!(
        app.oneshot(req).await.unwrap().status(),
        StatusCode::UNPROCESSABLE_ENTITY
    );
}

// ── /ffmpeg/metadata ──────────────────────────────────────────────────────────

#[tokio::test]
async fn test_metadata_returns_404_when_storage_reports_file_missing() {
    let app = Router::new()
        .route("/ffmpeg/metadata", get(get_metadata_handler))
        .with_state(make_state(MockStorage::file_not_in_storage()));

    let req = Request::builder()
        .method("GET")
        .uri("/ffmpeg/metadata?path=videos/ghost.mp4")
        .body(Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    assert_eq!(body_json(resp).await["error"], "File not found in storage");
}

#[tokio::test]
async fn test_metadata_returns_500_on_storage_io_error() {
    let app = Router::new()
        .route("/ffmpeg/metadata", get(get_metadata_handler))
        .with_state(make_state(MockStorage::download_io_error("Network timeout")));

    let req = Request::builder()
        .method("GET")
        .uri("/ffmpeg/metadata?path=videos/test.mp4")
        .body(Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(body_json(resp).await["error"].as_str().unwrap().contains("Network timeout"));
}

#[tokio::test]
async fn test_metadata_returns_400_when_path_query_param_absent() {
    let app = Router::new()
        .route("/ffmpeg/metadata", get(get_metadata_handler))
        .with_state(make_state(MockStorage::always_ok("http://x.com")));

    let req = Request::builder()
        .method("GET")
        .uri("/ffmpeg/metadata") // no ?path= param
        .body(Body::empty())
        .unwrap();

    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::BAD_REQUEST);
}

// ── /ffmpeg/extract-audio ─────────────────────────────────────────────────────

#[tokio::test]
async fn test_extract_audio_returns_404_when_input_file_missing() {
    let app = Router::new()
        .route("/ffmpeg/extract-audio", post(extract_audio_handler))
        .with_state(make_state(MockStorage::file_not_in_storage()));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/extract-audio")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"videos/missing.mp4","output_key":"audio/out.mp3"}"#,
        ))
        .unwrap();

    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_extract_audio_returns_500_on_download_io_error() {
    let app = Router::new()
        .route("/ffmpeg/extract-audio", post(extract_audio_handler))
        .with_state(make_state(MockStorage::download_io_error("S3 access denied")));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/extract-audio")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"videos/test.mp4","output_key":"audio/out.mp3"}"#,
        ))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(body_json(resp).await["error"].as_str().unwrap().contains("S3 access denied"));
}

#[tokio::test]
async fn test_extract_audio_returns_422_when_input_key_absent() {
    let app = Router::new()
        .route("/ffmpeg/extract-audio", post(extract_audio_handler))
        .with_state(make_state(MockStorage::always_ok("http://x.com")));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/extract-audio")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"output_key":"audio/out.mp3"}"#)) // input_key missing
        .unwrap();

    assert_eq!(
        app.oneshot(req).await.unwrap().status(),
        StatusCode::UNPROCESSABLE_ENTITY
    );
}

#[tokio::test]
async fn test_extract_audio_returns_422_when_output_key_absent() {
    let app = Router::new()
        .route("/ffmpeg/extract-audio", post(extract_audio_handler))
        .with_state(make_state(MockStorage::always_ok("http://x.com")));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/extract-audio")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"input_key":"videos/test.mp4"}"#)) // output_key missing
        .unwrap();

    assert_eq!(
        app.oneshot(req).await.unwrap().status(),
        StatusCode::UNPROCESSABLE_ENTITY
    );
}

// ── /ffmpeg/thumbnail ─────────────────────────────────────────────────────────

#[tokio::test]
async fn test_thumbnail_returns_404_when_input_file_missing() {
    let app = Router::new()
        .route("/ffmpeg/thumbnail", post(generate_thumbnail_handler))
        .with_state(make_state(MockStorage::file_not_in_storage()));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/thumbnail")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"videos/ghost.mp4","output_key":"thumbs/ghost.jpg"}"#,
        ))
        .unwrap();

    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_thumbnail_returns_500_on_download_io_error() {
    let app = Router::new()
        .route("/ffmpeg/thumbnail", post(generate_thumbnail_handler))
        .with_state(make_state(MockStorage::download_io_error("Bucket not found")));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/thumbnail")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"videos/test.mp4","output_key":"thumbs/test.jpg"}"#,
        ))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(body_json(resp).await["error"].as_str().unwrap().contains("Bucket not found"));
}

#[tokio::test]
async fn test_thumbnail_accepts_request_without_time_offset() {
    // time_offset is optional — its absence must not produce 422
    let app = Router::new()
        .route("/ffmpeg/thumbnail", post(generate_thumbnail_handler))
        .with_state(make_state(MockStorage::file_not_in_storage()));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/thumbnail")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"videos/test.mp4","output_key":"thumbs/test.jpg"}"#,
        ))
        .unwrap();

    // 404 from storage — not 422 from a missing field
    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_thumbnail_returns_422_when_output_key_absent() {
    let app = Router::new()
        .route("/ffmpeg/thumbnail", post(generate_thumbnail_handler))
        .with_state(make_state(MockStorage::always_ok("http://x.com")));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/thumbnail")
        .header("Content-Type", "application/json")
        .body(Body::from(r#"{"input_key":"videos/test.mp4"}"#)) // output_key missing
        .unwrap();

    assert_eq!(
        app.oneshot(req).await.unwrap().status(),
        StatusCode::UNPROCESSABLE_ENTITY
    );
}

#[tokio::test]
async fn test_thumbnail_accepts_explicit_time_offset() {
    let app = Router::new()
        .route("/ffmpeg/thumbnail", post(generate_thumbnail_handler))
        .with_state(make_state(MockStorage::file_not_in_storage()));

    let req = Request::builder()
        .method("POST")
        .uri("/ffmpeg/thumbnail")
        .header("Content-Type", "application/json")
        .body(Body::from(
            r#"{"input_key":"v/a.mp4","output_key":"t/a.jpg","time_offset":5.5}"#,
        ))
        .unwrap();

    // 404 because the file doesn't exist — not 422 or 400
    assert_eq!(app.oneshot(req).await.unwrap().status(), StatusCode::NOT_FOUND);
}
