use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::Json,
};
use serde_json::{json, Value};
use std::sync::Arc;

use crate::db::{
    create_video, delete_video_row, get_video, list_videos, patch_video_paths,
    patch_video_status, CreateVideoPayload, ListVideosParams, PatchPathsPayload, PatchStatusPayload,
};
use crate::AppState;

#[derive(serde::Deserialize)]
pub struct ListVideosQuery {
    pub user_id: i32,
    pub page: Option<i64>,
    pub limit: Option<i64>,
    pub search: Option<String>,
    pub sort_by: Option<String>,
    pub date_range: Option<String>,
    pub status: Option<String>,
    pub media_type: Option<String>,
}

pub async fn list_videos_handler(
    State(state): State<Arc<AppState>>,
    Query(params): Query<ListVideosQuery>,
) -> (StatusCode, Json<Value>) {
    let list_params = ListVideosParams {
        user_id: params.user_id,
        page: params.page.unwrap_or(1),
        limit: params.limit.unwrap_or(10),
        search: params.search,
        sort_by: params.sort_by,
        date_range: params.date_range,
        status: params.status,
        media_type: params.media_type,
    };

    match list_videos(&state.pool, &list_params).await {
        Ok(result) => (StatusCode::OK, Json(json!(result))),
        Err(e) => {
            tracing::error!("list_videos DB error for user {}: {}", list_params.user_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        }
    }
}

pub async fn create_video_handler(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<CreateVideoPayload>,
) -> (StatusCode, Json<Value>) {
    match create_video(&state.pool, &payload).await {
        Ok(video) => (StatusCode::CREATED, Json(json!(video))),
        Err(e) => {
            tracing::error!("create_video DB error for user {}: {}", payload.user_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        }
    }
}

pub async fn delete_video_handler(
    State(state): State<Arc<AppState>>,
    Path(video_id): Path<String>,
) -> (StatusCode, Json<Value>) {
    let video = match get_video(&state.pool, &video_id).await {
        Ok(Some(v)) => v,
        Ok(None) => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"status": "error", "message": "Video not found"})),
            )
        }
        Err(e) => {
            tracing::error!("get_video DB error for {}: {}", video_id, e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            );
        }
    };

    let mut deletes: Vec<String> = Vec::new();
    if !video.file_path.is_empty() {
        deletes.push(video.file_path.clone());
    }
    if let Some(key) = video.thumbnail_path.as_ref() {
        deletes.push(key.clone());
    }
    if let Some(key) = video.audio_path.as_ref() {
        deletes.push(key.clone());
    }
    if let Some(key) = video.dubbed_video_path.as_ref() {
        deletes.push(key.clone());
    }

    if let Some(hls_prefix) = video
        .file_path
        .rfind('/')
        .map(|idx| video.file_path[..idx].to_string())
        .filter(|_prefix| video.file_path.contains("/hls/") && video.file_path.ends_with("index.m3u8"))
    {
        if let Err(e) = state.storage.delete_prefix(&hls_prefix).await {
            tracing::error!("delete_prefix failed for {}: {}", hls_prefix, e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            );
        }
    }

    for key in deletes {
        if let Err(e) = state.storage.delete_object(&key).await {
            tracing::error!("delete_object failed for {}: {}", key, e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            );
        }
    }

    match delete_video_row(&state.pool, &video_id).await {
        Ok(rows) if rows > 0 => (
            StatusCode::OK,
            Json(json!({"status": "ok", "video_id": video_id})),
        ),
        Ok(_) => (
            StatusCode::NOT_FOUND,
            Json(json!({"status": "error", "message": "Video not found"})),
        ),
        Err(e) => {
            tracing::error!("delete_video DB error for {}: {}", video_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": e.to_string()})),
            )
        }
    }
}

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
