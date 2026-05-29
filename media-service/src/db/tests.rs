use super::{PatchPathsPayload, PatchStatusPayload, Video};
use chrono::NaiveDateTime;
use serde_json::json;

// ── PatchPathsPayload deserialization ─────────────────────────────────────────

#[test]
fn test_patch_paths_payload_all_fields() {
    let json = json!({
        "dubbed_video_path": "videos/dubbed.mp4",
        "dubbing_metadata": {"lang": "ar", "segments": 42},
        "audio_path": "audio/track.mp3",
        "thumbnail_path": "thumbs/cover.jpg",
        "file_path": "videos/original.mp4"
    });
    let p: PatchPathsPayload = serde_json::from_value(json).unwrap();
    assert_eq!(p.dubbed_video_path.as_deref(), Some("videos/dubbed.mp4"));
    assert_eq!(p.audio_path.as_deref(), Some("audio/track.mp3"));
    assert_eq!(p.thumbnail_path.as_deref(), Some("thumbs/cover.jpg"));
    assert_eq!(p.file_path.as_deref(), Some("videos/original.mp4"));
    assert!(p.dubbing_metadata.is_some());
}

#[test]
fn test_patch_paths_payload_all_optional_fields_can_be_absent() {
    let p: PatchPathsPayload = serde_json::from_value(json!({})).unwrap();
    assert!(p.dubbed_video_path.is_none());
    assert!(p.dubbing_metadata.is_none());
    assert!(p.audio_path.is_none());
    assert!(p.thumbnail_path.is_none());
    assert!(p.file_path.is_none());
}

#[test]
fn test_patch_paths_payload_partial_fields() {
    let p: PatchPathsPayload = serde_json::from_value(json!({"audio_path": "audio/test.mp3"})).unwrap();
    assert_eq!(p.audio_path.as_deref(), Some("audio/test.mp3"));
    assert!(p.dubbed_video_path.is_none());
    assert!(p.thumbnail_path.is_none());
}

#[test]
fn test_patch_paths_dubbing_metadata_accepts_complex_json() {
    let meta = json!({"provider": "openai", "voices": ["en-US", "ar-SA"], "cost_usd": 1.23});
    let p: PatchPathsPayload = serde_json::from_value(json!({"dubbing_metadata": meta})).unwrap();
    let stored = p.dubbing_metadata.unwrap();
    assert_eq!(stored["provider"], "openai");
    assert_eq!(stored["cost_usd"], 1.23);
}

// ── PatchStatusPayload deserialization ────────────────────────────────────────

#[test]
fn test_patch_status_payload_status_is_required() {
    let p: PatchStatusPayload = serde_json::from_value(json!({"status": "ready"})).unwrap();
    assert_eq!(p.status, "ready");
}

#[test]
fn test_patch_status_payload_all_optional_fields() {
    let json = json!({
        "status": "processing",
        "error_message": null,
        "duration": 123.45,
        "width": 1920,
        "height": 1080,
        "size_bytes": 52428800,
        "format": "mp4",
        "codec": "h264",
        "frame_rate": 29.97
    });
    let p: PatchStatusPayload = serde_json::from_value(json).unwrap();
    assert_eq!(p.status, "processing");
    assert_eq!(p.duration, Some(123.45));
    assert_eq!(p.width, Some(1920));
    assert_eq!(p.height, Some(1080));
    assert_eq!(p.size_bytes, Some(52_428_800_i64));
    assert_eq!(p.format.as_deref(), Some("mp4"));
    assert_eq!(p.codec.as_deref(), Some("h264"));
    assert!((p.frame_rate.unwrap() - 29.97).abs() < 0.001);
    assert!(p.error_message.is_none());
}

#[test]
fn test_patch_status_payload_optional_fields_default_to_none() {
    let p: PatchStatusPayload = serde_json::from_value(json!({"status": "failed"})).unwrap();
    assert_eq!(p.status, "failed");
    assert!(p.error_message.is_none());
    assert!(p.duration.is_none());
    assert!(p.width.is_none());
    assert!(p.height.is_none());
    assert!(p.size_bytes.is_none());
    assert!(p.format.is_none());
    assert!(p.codec.is_none());
    assert!(p.frame_rate.is_none());
}

#[test]
fn test_patch_status_payload_with_error_message() {
    let p: PatchStatusPayload = serde_json::from_value(
        json!({"status": "failed", "error_message": "ffmpeg process killed"}),
    )
    .unwrap();
    assert_eq!(p.status, "failed");
    assert_eq!(p.error_message.as_deref(), Some("ffmpeg process killed"));
}

// ── Video struct serialization ────────────────────────────────────────────────

fn ts(s: &str) -> NaiveDateTime {
    NaiveDateTime::parse_from_str(s, "%Y-%m-%d %H:%M:%S").unwrap()
}

#[test]
fn test_video_struct_serializes_to_json() {
    let video = Video {
        id: "uuid-1234".into(),
        user_id: 42,
        title: "Test Video".into(),
        original_filename: "upload.mp4".into(),
        media_type: "video".into(),
        file_path: "videos/uuid-1234.mp4".into(),
        thumbnail_path: Some("thumbs/uuid-1234.jpg".into()),
        audio_path: None,
        dubbed_video_path: None,
        dubbing_metadata: None,
        duration: Some(95.3),
        width: Some(1920),
        height: Some(1080),
        size_bytes: Some(10_485_760),
        format: Some("mp4".into()),
        codec: Some("h264".into()),
        frame_rate: Some(30.0),
        status: "ready".into(),
        error_message: None,
        created_at: ts("2024-01-01 12:00:00"),
        updated_at: ts("2024-01-01 12:05:00"),
    };
    let json = serde_json::to_value(&video).unwrap();
    assert_eq!(json["id"], "uuid-1234");
    assert_eq!(json["user_id"], 42);
    assert_eq!(json["title"], "Test Video");
    assert_eq!(json["status"], "ready");
    assert_eq!(json["width"], 1920);
    assert_eq!(json["audio_path"], serde_json::Value::Null);
    assert_eq!(json["thumbnail_path"], "thumbs/uuid-1234.jpg");
}

#[test]
fn test_video_struct_optional_media_fields_serialize_as_null() {
    let t = ts("2024-06-01 00:00:00");
    let video = Video {
        id: "abc".into(),
        user_id: 1,
        title: "No Media Metadata".into(),
        original_filename: "raw.mp4".into(),
        media_type: "video".into(),
        file_path: "videos/abc.mp4".into(),
        thumbnail_path: None,
        audio_path: None,
        dubbed_video_path: None,
        dubbing_metadata: None,
        duration: None,
        width: None,
        height: None,
        size_bytes: None,
        format: None,
        codec: None,
        frame_rate: None,
        status: "pending".into(),
        error_message: None,
        created_at: t,
        updated_at: t,
    };
    let json = serde_json::to_value(&video).unwrap();
    assert_eq!(json["duration"], serde_json::Value::Null);
    assert_eq!(json["width"], serde_json::Value::Null);
    assert_eq!(json["codec"], serde_json::Value::Null);
}
