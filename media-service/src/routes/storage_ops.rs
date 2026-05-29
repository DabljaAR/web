use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
};
use serde_json::{json, Value};
use std::sync::Arc;

use crate::AppState;

pub async fn delete_file_handler(
    State(state): State<Arc<AppState>>,
    Path(key): Path<String>,
) -> (StatusCode, Json<Value>) {
    match state.storage.delete_object(&key).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ok", "key": key}))),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        ),
    }
}
