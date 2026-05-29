use super::{
    parse_ffprobe_output, FFmpegService, FfprobeFormat, FfprobeOutput, FfprobeStream,
    VideoMetadata,
};

// ── Stream / format builders ─────────────────────────────────────────────────

fn video_stream(codec: &str, w: i32, h: i32, fps: &str, dur: Option<&str>) -> FfprobeStream {
    FfprobeStream {
        codec_type: Some("video".into()),
        codec_name: Some(codec.into()),
        width: Some(w),
        height: Some(h),
        duration: dur.map(|d| d.into()),
        r_frame_rate: Some(fps.into()),
    }
}

fn audio_stream(codec: &str, dur: Option<&str>) -> FfprobeStream {
    FfprobeStream {
        codec_type: Some("audio".into()),
        codec_name: Some(codec.into()),
        width: None,
        height: None,
        duration: dur.map(|d| d.into()),
        r_frame_rate: None,
    }
}

fn fmt(dur: Option<&str>, name: Option<&str>, size: Option<&str>) -> FfprobeFormat {
    FfprobeFormat {
        duration: dur.map(|d| d.into()),
        format_name: name.map(|n| n.into()),
        size: size.map(|s| s.into()),
    }
}

// ── parse_ffprobe_output — stream combinations ───────────────────────────────

#[test]
fn test_full_video_with_audio() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("120.5"), Some("mp4"), Some("10485760"))),
        streams: Some(vec![
            video_stream("h264", 1920, 1080, "30/1", None),
            audio_stream("aac", None),
        ]),
    };
    let meta = parse_ffprobe_output(data, "test.mp4").unwrap();
    assert_eq!(meta.duration, 120.5);
    assert_eq!(meta.width, Some(1920));
    assert_eq!(meta.height, Some(1080));
    assert_eq!(meta.codec, "h264");
    assert_eq!(meta.format, "mp4");
    assert_eq!(meta.frame_rate, 30.0);
    assert_eq!(meta.size, 10485760);
    assert!(meta.audio_present);
}

#[test]
fn test_video_only_no_audio() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("60.0"), Some("avi"), Some("5000000"))),
        streams: Some(vec![video_stream("mpeg4", 1280, 720, "25/1", None)]),
    };
    let meta = parse_ffprobe_output(data, "test.avi").unwrap();
    assert_eq!(meta.width, Some(1280));
    assert_eq!(meta.height, Some(720));
    assert_eq!(meta.codec, "mpeg4");
    assert_eq!(meta.format, "avi");
    assert!(!meta.audio_present);
}

#[test]
fn test_audio_only_stream() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("300.0"), Some("mp3"), Some("12000000"))),
        streams: Some(vec![audio_stream("mp3", None)]),
    };
    let meta = parse_ffprobe_output(data, "audio.mp3").unwrap();
    assert_eq!(meta.duration, 300.0);
    assert_eq!(meta.codec, "mp3");
    assert_eq!(meta.width, None);
    assert_eq!(meta.height, None);
    assert_eq!(meta.frame_rate, 0.0);
    assert!(meta.audio_present);
}

#[test]
fn test_empty_streams_list_returns_error() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![]),
    };
    let err = parse_ffprobe_output(data, "empty.mp4").unwrap_err();
    assert!(err.to_string().contains("No video or audio stream found"));
}

#[test]
fn test_null_streams_and_format_returns_error() {
    let data = FfprobeOutput {
        format: None,
        streams: None,
    };
    assert!(parse_ffprobe_output(data, "null.mp4").is_err());
}

#[test]
fn test_multiple_video_streams_uses_first() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("5000"))),
        streams: Some(vec![
            video_stream("h264", 1920, 1080, "30/1", None),
            video_stream("vp9", 640, 480, "25/1", None),
        ]),
    };
    let meta = parse_ffprobe_output(data, "multi.mp4").unwrap();
    assert_eq!(meta.width, Some(1920));
    assert_eq!(meta.codec, "h264");
}

// ── parse_ffprobe_output — frame rate ────────────────────────────────────────

#[test]
fn test_ntsc_frame_rate_30000_over_1001() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1920, 1080, "30000/1001", None)]),
    };
    let meta = parse_ffprobe_output(data, "ntsc.mp4").unwrap();
    let expected = 30000.0 / 1001.0;
    assert!((meta.frame_rate - expected).abs() < 0.001, "expected ≈{expected}, got {}", meta.frame_rate);
}

#[test]
fn test_frame_rate_zero_denominator_yields_zero() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1920, 1080, "30/0", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().frame_rate, 0.0);
}

#[test]
fn test_frame_rate_invalid_string_yields_zero() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1920, 1080, "not-a-rate", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().frame_rate, 0.0);
}

#[test]
fn test_frame_rate_plain_integer_without_slash_yields_zero() {
    // ffprobe always uses "num/den" — a plain integer has no slash → 0.0
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1920, 1080, "60", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().frame_rate, 0.0);
}

// ── parse_ffprobe_output — duration fallback chain ────────────────────────────

#[test]
fn test_duration_taken_from_format_section() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("99.5"), Some("mkv"), Some("2000000"))),
        streams: Some(vec![video_stream("hevc", 3840, 2160, "60/1", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "4k.mkv").unwrap().duration, 99.5);
}

#[test]
fn test_duration_fallback_to_video_stream_when_format_missing() {
    let data = FfprobeOutput {
        format: Some(fmt(None, Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1280, 720, "24/1", Some("45.5"))]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().duration, 45.5);
}

#[test]
fn test_duration_fallback_to_audio_when_no_video_duration() {
    let data = FfprobeOutput {
        format: Some(fmt(None, Some("m4a"), Some("1000"))),
        streams: Some(vec![audio_stream("aac", Some("88.2"))]),
    };
    assert_eq!(parse_ffprobe_output(data, "audio.m4a").unwrap().duration, 88.2);
}

#[test]
fn test_duration_is_zero_when_all_sources_missing() {
    let data = FfprobeOutput {
        format: Some(fmt(None, Some("mp4"), Some("1000"))),
        streams: Some(vec![video_stream("h264", 1280, 720, "30/1", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().duration, 0.0);
}

// ── parse_ffprobe_output — codec / format / size fallbacks ───────────────────

#[test]
fn test_codec_falls_back_to_audio_when_no_video_stream() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("flac"), Some("5000000"))),
        streams: Some(vec![audio_stream("flac", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "music.flac").unwrap().codec, "flac");
}

#[test]
fn test_codec_is_unknown_when_codec_name_absent() {
    let data = FfprobeOutput {
        format: Some(fmt(Some("10.0"), Some("mp4"), Some("1000"))),
        streams: Some(vec![FfprobeStream {
            codec_type: Some("video".into()),
            codec_name: None,
            width: Some(1280),
            height: Some(720),
            duration: None,
            r_frame_rate: Some("30/1".into()),
        }]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().codec, "unknown");
}

#[test]
fn test_size_zero_when_unparseable() {
    let data = FfprobeOutput {
        format: Some(FfprobeFormat {
            duration: Some("10.0".into()),
            format_name: Some("mp4".into()),
            size: Some("not-a-number".into()),
        }),
        streams: Some(vec![video_stream("h264", 1280, 720, "30/1", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().size, 0);
}

#[test]
fn test_format_is_unknown_when_format_name_absent() {
    let data = FfprobeOutput {
        format: Some(FfprobeFormat {
            duration: Some("10.0".into()),
            format_name: None,
            size: Some("1000".into()),
        }),
        streams: Some(vec![video_stream("h264", 1280, 720, "30/1", None)]),
    };
    assert_eq!(parse_ffprobe_output(data, "test.mp4").unwrap().format, "unknown");
}

// ── parse_ffprobe_output — realistic JSON payloads ───────────────────────────

#[test]
fn test_parse_realistic_ffprobe_json() {
    let json_str = r#"{
        "format": {
            "duration": "63.510000",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "size": "8396954"
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "r_frame_rate": "30000/1001",
                "duration": "63.496500"
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "duration": "63.510000"
            }
        ]
    }"#;
    let data: FfprobeOutput = serde_json::from_str(json_str).unwrap();
    let meta = parse_ffprobe_output(data, "sample.mp4").unwrap();

    assert_eq!(meta.width, Some(1280));
    assert_eq!(meta.height, Some(720));
    assert_eq!(meta.codec, "h264");
    assert!(meta.audio_present);
    assert!((meta.frame_rate - 29.97).abs() < 0.01);
    assert_eq!(meta.size, 8396954);
    assert!((meta.duration - 63.51).abs() < 0.001);
}

#[test]
fn test_parse_audio_only_ffprobe_json() {
    let json_str = r#"{
        "format": {
            "duration": "180.000000",
            "format_name": "mp3",
            "size": "4320000"
        },
        "streams": [
            { "codec_type": "audio", "codec_name": "mp3", "duration": "180.000000" }
        ]
    }"#;
    let data: FfprobeOutput = serde_json::from_str(json_str).unwrap();
    let meta = parse_ffprobe_output(data, "song.mp3").unwrap();

    assert_eq!(meta.codec, "mp3");
    assert_eq!(meta.duration, 180.0);
    assert_eq!(meta.width, None);
    assert_eq!(meta.frame_rate, 0.0);
    assert!(meta.audio_present);
}

#[test]
fn test_json_deserialization_handles_missing_optional_fields() {
    let json_str = r#"{ "streams": [{ "codec_type": "video", "codec_name": "h264" }] }"#;
    let data: FfprobeOutput = serde_json::from_str(json_str).unwrap();
    let meta = parse_ffprobe_output(data, "minimal.mp4").unwrap();
    assert_eq!(meta.codec, "h264");
    assert_eq!(meta.format, "unknown");
    assert_eq!(meta.size, 0);
    assert_eq!(meta.frame_rate, 0.0);
}

#[test]
fn test_invalid_json_fails_deserialization() {
    let result: serde_json::Result<FfprobeOutput> = serde_json::from_str("{invalid json}");
    assert!(result.is_err());
}

// ── FFmpegService construction ───────────────────────────────────────────────

#[test]
fn test_ffmpeg_service_default_binary_paths() {
    let svc = FFmpegService::new();
    assert_eq!(svc.ffprobe_path, "ffprobe");
    assert_eq!(svc.ffmpeg_path, "ffmpeg");
}

#[test]
fn test_ffmpeg_service_default_trait_matches_new() {
    let a = FFmpegService::default();
    let b = FFmpegService::new();
    assert_eq!(a.ffprobe_path, b.ffprobe_path);
    assert_eq!(a.ffmpeg_path, b.ffmpeg_path);
}

// ── VideoMetadata serde ──────────────────────────────────────────────────────

#[test]
fn test_video_metadata_serializes_to_json() {
    let meta = VideoMetadata {
        duration: 42.0,
        width: Some(1920),
        height: Some(1080),
        format: "mp4".into(),
        codec: "h264".into(),
        frame_rate: 29.97,
        size: 123456,
        audio_present: true,
    };
    let json = serde_json::to_value(&meta).unwrap();
    assert_eq!(json["duration"], 42.0);
    assert_eq!(json["width"], 1920);
    assert_eq!(json["codec"], "h264");
    assert_eq!(json["audio_present"], true);
}

#[test]
fn test_video_metadata_round_trips_through_json() {
    let original = VideoMetadata {
        duration: 99.9,
        width: None,
        height: None,
        format: "webm".into(),
        codec: "vp9".into(),
        frame_rate: 60.0,
        size: 0,
        audio_present: false,
    };
    let json = serde_json::to_string(&original).unwrap();
    let restored: VideoMetadata = serde_json::from_str(&json).unwrap();
    assert_eq!(restored.duration, original.duration);
    assert_eq!(restored.codec, original.codec);
    assert_eq!(restored.audio_present, original.audio_present);
    assert_eq!(restored.width, None);
}
