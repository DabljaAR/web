use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::Arc;
use tempfile::TempDir;

use crate::storage::PresignMethod;
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
    match state.storage.download_file(&req.input_key, &input_local).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({"error": "Input file not found in storage"}))),
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
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
    match state.storage.download_file(&req.input_key, &input_local).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({"error": "Input file not found in storage"}))),
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
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
    pub method: Option<String>,
    pub content_type: Option<String>,
}

pub async fn get_presigned_url_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<PresignRequest>,
) -> (StatusCode, Json<Value>) {
    let expires = req.expires_secs.unwrap_or(3600);
    let method = match req.method.as_deref().unwrap_or("GET").to_uppercase().as_str() {
        "PUT" => PresignMethod::Put,
        _ => PresignMethod::Get,
    };

    match state
        .storage
        .get_presigned_url(&req.key, expires, method, req.content_type.as_deref())
        .await
    {
        Ok(url) => (StatusCode::OK, Json(json!({"url": url}))),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }
}

// ─── HLS ─────────────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct HlsRequest {
    pub input_key: String,
    pub output_prefix: String,
    pub segment_time: Option<u32>,
}

pub async fn hls_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<HlsRequest>,
) -> (StatusCode, Json<Value>) {
    let segment_time = req.segment_time.unwrap_or(10);

    let tmp = match TempDir::new() {
        Ok(t) => t,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    };

    let input_local = tmp.path().join("input");
    let hls_dir = tmp.path().join("hls");

    if let Err(e) = tokio::fs::create_dir_all(&hls_dir).await {
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("mkdir hls: {e}")})));
    }

    match state.storage.download_file(&req.input_key, &input_local).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({"error": "Input file not found in storage"}))),
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }

    match state.ffmpeg.generate_hls(
        input_local.to_str().unwrap_or(""),
        hls_dir.to_str().unwrap_or(""),
        segment_time,
    ).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": "HLS generation failed"}))),
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    }

    let prefix = req.output_prefix.trim_end_matches('/');
    let mut segment_count = 0u32;

    let mut entries = match tokio::fs::read_dir(&hls_dir).await {
        Ok(rd) => rd,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("read_dir: {e}")}))),
    };

    while let Ok(Some(entry)) = entries.next_entry().await {
        let name: String = entry.file_name().to_string_lossy().into_owned();
        let (mime, is_seg) = if name.ends_with(".m3u8") {
            ("application/x-mpegURL", false)
        } else if name.ends_with(".ts") {
            ("video/mp2t", true)
        } else {
            continue;
        };
        let s3_key = format!("{prefix}/{name}");
        if let Err(e) = state.storage.upload_file(&entry.path(), &s3_key, mime).await {
            return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("upload {name}: {e}")})));
        }
        if is_seg {
            segment_count += 1;
        }
    }

    (StatusCode::OK, Json(json!({
        "status": "ok",
        "playlist_key": format!("{prefix}/index.m3u8"),
        "segment_count": segment_count,
    })))
}

// ─── DUB ─────────────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct DubSegment {
    pub segment_id: i64,
    pub start: f64,
    pub end: f64,
    pub tts_audio_key: String,
    pub tts_duration: Option<f64>,
}

#[derive(Deserialize)]
pub struct DubRequest {
    pub job_id: String,
    #[allow(dead_code)]
    pub video_id: String,
    pub media_type: String,
    pub original_media_key: Option<String>,
    pub output_key_prefix: String,
    pub combined_audio_key: Option<String>,
    pub max_stretch: Option<f64>,
    pub min_stretch: Option<f64>,
    pub silence_threshold: Option<f64>,
    pub segments: Vec<DubSegment>,
}

pub async fn dub_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<DubRequest>,
) -> (StatusCode, Json<Value>) {
    let max_stretch = req.max_stretch.unwrap_or(2.0_f64);
    let min_stretch = req.min_stretch.unwrap_or(0.5_f64);
    let silence_threshold = req.silence_threshold.unwrap_or(0.05_f64);
    let media_type = req.media_type.to_lowercase();

    let tmp = match TempDir::new() {
        Ok(t) => t,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e.to_string()}))),
    };

    let audio_dir = tmp.path().join("audio");
    let proc_dir  = tmp.path().join("proc");
    for d in [&audio_dir, &proc_dir] {
        if let Err(e) = tokio::fs::create_dir_all(d).await {
            return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("mkdir: {e}")})));
        }
    }

    // Phase 1: validate & sort
    let mut segs: Vec<&DubSegment> = req.segments.iter()
        .filter(|s| s.start >= 0.0 && s.end > s.start)
        .collect();
    segs.sort_by(|a, b| a.start.partial_cmp(&b.start).unwrap_or(std::cmp::Ordering::Equal));

    if segs.is_empty() {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": "No valid segments provided"})));
    }

    // Phases 2-4: download → probe → stretch → fit
    // processed entries: (start, end, fitted_wav_path, stretch_factor)
    let mut processed: Vec<(f64, f64, PathBuf, f64)> = Vec::new();
    let mut stretched_count = 0usize;
    let mut stretch_sum = 0.0_f64;

    for seg in &segs {
        let wav = audio_dir.join(format!("s{}.wav", seg.segment_id));

        match state.storage.download_file(&seg.tts_audio_key, &wav).await {
            Ok(true) => {}
            Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({
                "error": format!("Segment {} not found: {}", seg.segment_id, seg.tts_audio_key)
            }))),
            Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({
                "error": format!("Download seg {}: {e}", seg.segment_id)
            }))),
        }

        let actual = if let Some(d) = seg.tts_duration {
            d
        } else {
            state.ffmpeg.get_audio_duration(wav.to_str().unwrap_or("")).await
        };

        let target = seg.end - seg.start;
        let actual = if actual > 0.0 { actual } else { target };
        let required = if target > 0.0 { actual / target } else { 1.0 };
        let clamped = required.clamp(min_stretch, max_stretch);

        stretch_sum += clamped;
        if (clamped - 1.0).abs() > 0.01 {
            stretched_count += 1;
        }

        let after_stretch: PathBuf = if (clamped - 1.0).abs() > 0.01 {
            let sp = proc_dir.join(format!("s{}_st.wav", seg.segment_id));
            match state.ffmpeg.stretch_audio(wav.to_str().unwrap_or(""), sp.to_str().unwrap_or(""), clamped).await {
                Ok(true) => sp,
                _ => wav.clone(),
            }
        } else {
            wav.clone()
        };

        let fitted = proc_dir.join(format!("s{}_fit.wav", seg.segment_id));
        match state.ffmpeg.fit_audio_to_duration(
            after_stretch.to_str().unwrap_or(""),
            fitted.to_str().unwrap_or(""),
            target,
        ).await {
            Ok(true) => {}
            _ => {
                if let Err(e) = tokio::fs::copy(&after_stretch, &fitted).await {
                    return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("fit fallback: {e}")})));
                }
            }
        }

        processed.push((seg.start, seg.end, fitted, clamped));
    }

    // Phase 5: build concat list and concatenate
    let concat_file = tmp.path().join("concat.txt");
    let combined    = tmp.path().join("combined.wav");
    let mut lines   = String::new();

    let first_start = processed.first().map(|p| p.0).unwrap_or(0.0);
    if first_start > 0.001 {
        let sil = tmp.path().join("sil_lead.wav");
        if let Ok(true) = state.ffmpeg.generate_silence(sil.to_str().unwrap_or(""), first_start).await {
            lines.push_str(&format!("file '{}'\n", sil.display()));
        }
    }

    let n = processed.len();
    for i in 0..n {
        lines.push_str(&format!("file '{}'\n", processed[i].2.display()));
        if i + 1 < n {
            let gap = (processed[i + 1].0 - processed[i].1).max(0.0);
            if gap >= silence_threshold {
                let sil = tmp.path().join(format!("sil_{i}.wav"));
                if let Ok(true) = state.ffmpeg.generate_silence(sil.to_str().unwrap_or(""), gap).await {
                    lines.push_str(&format!("file '{}'\n", sil.display()));
                }
            }
        }
    }

    if let Err(e) = tokio::fs::write(&concat_file, &lines).await {
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("write concat: {e}")})));
    }

    match state.ffmpeg.concat_audio(concat_file.to_str().unwrap_or(""), combined.to_str().unwrap_or("")).await {
        Ok(true) => {}
        Ok(false) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": "concat returned no output"}))),
        Err(e)   => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("concat: {e}")}))),
    }

    // Phase 6: upload combined WAV
    let wav_key = req.combined_audio_key
        .as_deref().filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or_else(|| format!("tts/{}/combined_{}.wav", req.job_id, req.job_id));

    let wav_key = match state.storage.upload_file(&combined, &wav_key, "audio/wav").await {
        Ok(k) => k,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("upload combined WAV: {e}")}))),
    };
    let combined_url = state.storage.get_presigned_url(&wav_key, 3600, PresignMethod::Get, None).await.unwrap_or_default();

    // Phases 7-8: mux with video (video media type only)
    let mut output_key: Option<String> = None;
    let mut output_url: Option<String> = None;

    if media_type == "video" {
        let orig_key = match req.original_media_key.as_deref().filter(|s| !s.is_empty()) {
            Some(k) => k.to_string(),
            None => return (StatusCode::BAD_REQUEST, Json(json!({"error": "original_media_key required for video"}))),
        };

        let orig_video = tmp.path().join("original.mp4");
        match state.storage.download_file(&orig_key, &orig_video).await {
            Ok(true) => {}
            Ok(false) => return (StatusCode::NOT_FOUND, Json(json!({"error": "Original video not found"}))),
            Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("download original: {e}")}))),
        }

        let vid_dur = state.ffmpeg.get_audio_duration(orig_video.to_str().unwrap_or("")).await;
        let vid_dur_opt = if vid_dur > 0.0 { Some(vid_dur) } else { None };

        let dubbed = tmp.path().join("dubbed.mp4");
        match state.ffmpeg.replace_video_audio(
            orig_video.to_str().unwrap_or(""),
            combined.to_str().unwrap_or(""),
            dubbed.to_str().unwrap_or(""),
            vid_dur_opt,
        ).await {
            Ok(true) => {}
            Ok(false) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": "replace_video_audio produced no output"}))),
            Err(e)   => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("replace_video_audio: {e}")}))),
        }

        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default().as_secs();
        let vid_key = format!("{}/{}_dubbed.mp4", req.output_key_prefix.trim_end_matches('/'), ts);

        let uploaded = match state.storage.upload_file(&dubbed, &vid_key, "video/mp4").await {
            Ok(k) => k,
            Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("upload dubbed video: {e}")}))),
        };
        let vid_url = state.storage.get_presigned_url(&uploaded, 3600, PresignMethod::Get, None).await.unwrap_or_default();

        output_key = Some(uploaded);
        output_url = Some(vid_url);
    }

    let avg_stretch = if n > 0 { stretch_sum / n as f64 } else { 1.0 };

    (StatusCode::OK, Json(json!({
        "status": "ok",
        "output_key": output_key,
        "output_url": output_url,
        "combined_audio_key": wav_key,
        "combined_audio_url": combined_url,
        "metadata": {
            "total_segments": n,
            "segments_stretched": stretched_count,
            "avg_stretch_factor": (avg_stretch * 1000.0).round() / 1000.0,
        }
    })))
}
