use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use chrono::{Datelike, Duration, Utc};
use sqlx::QueryBuilder;

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

#[derive(Debug, Deserialize)]
pub struct CreateVideoPayload {
    pub id: Option<String>,
    pub user_id: i32,
    pub title: String,
    pub original_filename: String,
    pub media_type: Option<String>,
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
    pub status: Option<String>,
    pub error_message: Option<String>,
}

#[derive(Debug)]
pub struct ListVideosParams {
    pub user_id: i32,
    pub page: i64,
    pub limit: i64,
    pub search: Option<String>,
    pub sort_by: Option<String>,
    pub date_range: Option<String>,
    pub status: Option<String>,
    pub media_type: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct PaginatedVideos {
    pub items: Vec<Video>,
    pub total: i64,
    pub page: i64,
    pub size: i64,
    pub pages: i64,
    pub total_completed: i64,
    pub total_failed: i64,
}

/// Payload for PATCH /videos/:id/paths
#[derive(Debug, Deserialize)]
pub struct PatchPathsPayload {
    pub dubbed_video_path: Option<String>,
    pub dubbing_metadata: Option<serde_json::Value>,
    pub audio_path: Option<String>,
    pub thumbnail_path: Option<String>,
    pub file_path: Option<String>,
}

/// Payload for PATCH /videos/:id/status
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

pub async fn create_video(
    pool: &PgPool,
    payload: &CreateVideoPayload,
) -> Result<Video, sqlx::Error> {
    let id = payload
        .id
        .clone()
        .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
    let media_type = payload
        .media_type
        .clone()
        .unwrap_or_else(|| "VIDEO".to_string())
        .to_uppercase();
    let status = payload
        .status
        .clone()
        .unwrap_or_else(|| "PENDING".to_string())
        .to_uppercase();

    sqlx::query_as::<_, Video>(
        r#"INSERT INTO videos (
                id, user_id, title, original_filename, media_type, file_path,
                thumbnail_path, audio_path, dubbed_video_path, dubbing_metadata,
                duration, width, height, size_bytes, format, codec, frame_rate,
                status, error_message
            ) VALUES (
                $1, $2, $3, $4, $5::mediatype, $6,
                $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17,
                $18::videostatus, $19
            )
            RETURNING
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
                updated_at"#,
    )
    .bind(id)
    .bind(payload.user_id)
    .bind(&payload.title)
    .bind(&payload.original_filename)
    .bind(&media_type)
    .bind(&payload.file_path)
    .bind(&payload.thumbnail_path)
    .bind(&payload.audio_path)
    .bind(&payload.dubbed_video_path)
    .bind(&payload.dubbing_metadata)
    .bind(payload.duration)
    .bind(payload.width)
    .bind(payload.height)
    .bind(payload.size_bytes)
    .bind(&payload.format)
    .bind(&payload.codec)
    .bind(payload.frame_rate)
    .bind(&status)
    .bind(&payload.error_message)
    .fetch_one(pool)
    .await
}

pub async fn delete_video_row(pool: &PgPool, video_id: &str) -> Result<u64, sqlx::Error> {
    let result = sqlx::query("DELETE FROM videos WHERE id = $1")
        .bind(video_id)
        .execute(pool)
        .await?;
    Ok(result.rows_affected())
}

fn apply_list_filters<'a>(
    qb: &mut QueryBuilder<'a, sqlx::Postgres>,
    params: &ListVideosParams,
) {
    qb.push(" WHERE user_id = ");
    qb.push_bind(params.user_id);

    if let Some(search) = params.search.as_ref().map(|s| s.trim()).filter(|s| !s.is_empty()) {
        let pattern = format!("%{}%", search);
        qb.push(" AND (title ILIKE ");
        qb.push_bind(pattern.clone());
        qb.push(" OR original_filename ILIKE ");
        qb.push_bind(pattern);
        qb.push(")");
    }

    if let Some(media_type) = params.media_type.as_ref().map(|s| s.trim()).filter(|s| !s.is_empty()) {
        qb.push(" AND media_type::TEXT = ");
        qb.push_bind(media_type.to_uppercase());
    }

    if let Some(status) = params
        .status
        .as_ref()
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
    {
        let statuses: Vec<String> = status
            .split(',')
            .map(|s| s.trim().to_uppercase())
            .filter(|s| !s.is_empty())
            .collect();
        if !statuses.is_empty() {
            qb.push(" AND status::TEXT IN (");
            let mut separated = qb.separated(", ");
            for st in statuses {
                separated.push_bind(st);
            }
            qb.push(")");
        }
    }

    if let Some(range) = params.date_range.as_ref().map(|s| s.trim()).filter(|s| !s.is_empty()) {
        let now = Utc::now().naive_utc();
        let today_start = now
            .date()
            .and_hms_opt(0, 0, 0)
            .unwrap_or_else(|| now);
        match range {
            "today" => {
                qb.push(" AND created_at >= ");
                qb.push_bind(today_start);
            }
            "yesterday" => {
                let start = today_start - Duration::days(1);
                qb.push(" AND created_at >= ");
                qb.push_bind(start);
                qb.push(" AND created_at < ");
                qb.push_bind(today_start);
            }
            "thisWeek" => {
                let weekday = today_start.date().weekday().num_days_from_monday() as i64;
                let start = today_start - Duration::days(weekday);
                qb.push(" AND created_at >= ");
                qb.push_bind(start);
            }
            "thisMonth" => {
                let start = today_start
                    .date()
                    .with_day(1)
                    .unwrap_or(today_start.date())
                    .and_hms_opt(0, 0, 0)
                    .unwrap_or(today_start);
                qb.push(" AND created_at >= ");
                qb.push_bind(start);
            }
            "lastMonth" => {
                let this_month_start = today_start
                    .date()
                    .with_day(1)
                    .unwrap_or(today_start.date())
                    .and_hms_opt(0, 0, 0)
                    .unwrap_or(today_start);
                let last_month_end = this_month_start - Duration::days(1);
                let last_month_start = last_month_end
                    .date()
                    .with_day(1)
                    .unwrap_or(last_month_end.date())
                    .and_hms_opt(0, 0, 0)
                    .unwrap_or(last_month_end);
                qb.push(" AND created_at >= ");
                qb.push_bind(last_month_start);
                qb.push(" AND created_at < ");
                qb.push_bind(this_month_start);
            }
            "last7Days" => {
                qb.push(" AND created_at >= ");
                qb.push_bind(now - Duration::days(7));
            }
            "last30Days" => {
                qb.push(" AND created_at >= ");
                qb.push_bind(now - Duration::days(30));
            }
            "last90Days" => {
                qb.push(" AND created_at >= ");
                qb.push_bind(now - Duration::days(90));
            }
            _ => {}
        }
    }
}

pub async fn list_videos(
    pool: &PgPool,
    params: &ListVideosParams,
) -> Result<PaginatedVideos, sqlx::Error> {
    let limit = if params.limit <= 0 { 10 } else { params.limit };
    let page = if params.page <= 0 { 1 } else { params.page };
    let offset = (page - 1) * limit;

    let sort_by = params.sort_by.as_deref().unwrap_or("date-desc");
    let order_clause = match sort_by {
        "date-asc" | "dateOldest" => "created_at ASC",
        "size-desc" => "size_bytes DESC NULLS LAST",
        "size-asc" => "size_bytes ASC NULLS LAST",
        "duration-desc" => "duration DESC NULLS LAST",
        "duration-asc" => "duration ASC NULLS LAST",
        "name-asc" | "nameAZ" => "title ASC",
        "name-desc" | "nameZA" => "title DESC",
        _ => "created_at DESC",
    };

    let mut list_qb = QueryBuilder::<sqlx::Postgres>::new(
        "SELECT id, user_id, title, original_filename, media_type::TEXT AS media_type, file_path, thumbnail_path, audio_path, dubbed_video_path, dubbing_metadata, duration::FLOAT8 AS duration, width, height, size_bytes, format, codec, frame_rate::FLOAT8 AS frame_rate, status::TEXT AS status, error_message, created_at, updated_at FROM videos",
    );
    apply_list_filters(&mut list_qb, params);
    list_qb.push(" ORDER BY ");
    list_qb.push(order_clause);
    list_qb.push(" LIMIT ");
    list_qb.push_bind(limit);
    list_qb.push(" OFFSET ");
    list_qb.push_bind(offset);

    let items: Vec<Video> = list_qb.build_query_as().fetch_all(pool).await?;

    let mut count_qb = QueryBuilder::<sqlx::Postgres>::new("SELECT COUNT(*) FROM videos");
    apply_list_filters(&mut count_qb, params);
    let total: i64 = count_qb.build_query_scalar().fetch_one(pool).await?;

    let mut completed_qb = QueryBuilder::<sqlx::Postgres>::new("SELECT COUNT(*) FROM videos");
    apply_list_filters(&mut completed_qb, params);
    completed_qb.push(" AND status::TEXT = ");
    completed_qb.push_bind("COMPLETED");
    let total_completed: i64 = completed_qb.build_query_scalar().fetch_one(pool).await?;

    let mut failed_qb = QueryBuilder::<sqlx::Postgres>::new("SELECT COUNT(*) FROM videos");
    apply_list_filters(&mut failed_qb, params);
    failed_qb.push(" AND status::TEXT = ");
    failed_qb.push_bind("FAILED");
    let total_failed: i64 = failed_qb.build_query_scalar().fetch_one(pool).await?;

    let pages = if total == 0 {
        0
    } else {
        ((total as f64) / (limit as f64)).ceil() as i64
    };

    Ok(PaginatedVideos {
        items,
        total,
        page,
        size: limit,
        pages,
        total_completed,
        total_failed,
    })
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

#[cfg(test)]
mod tests;
