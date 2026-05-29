use axum::{http::StatusCode, response::Json};
use serde_json::{json, Value};

pub async fn health_check() -> (StatusCode, Json<Value>) {
    (StatusCode::OK, Json(json!({"status": "ok"})))
}
