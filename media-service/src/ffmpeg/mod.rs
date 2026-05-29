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
pub(crate) struct FfprobeOutput {
    pub(crate) format: Option<FfprobeFormat>,
    pub(crate) streams: Option<Vec<FfprobeStream>>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct FfprobeFormat {
    pub(crate) duration: Option<String>,
    pub(crate) format_name: Option<String>,
    pub(crate) size: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct FfprobeStream {
    pub(crate) codec_type: Option<String>,
    pub(crate) codec_name: Option<String>,
    pub(crate) width: Option<i32>,
    pub(crate) height: Option<i32>,
    pub(crate) duration: Option<String>,
    pub(crate) r_frame_rate: Option<String>,
}

pub(crate) fn parse_ffprobe_output(data: FfprobeOutput, file_path: &str) -> Result<VideoMetadata> {
    let fmt = data.format.unwrap_or(FfprobeFormat {
        duration: None,
        format_name: None,
        size: None,
    });
    let streams = data.streams.unwrap_or_default();

    let video_stream = streams.iter().find(|s| s.codec_type.as_deref() == Some("video"));
    let audio_stream = streams.iter().find(|s| s.codec_type.as_deref() == Some("audio"));

    if video_stream.is_none() && audio_stream.is_none() {
        return Err(anyhow!("No video or audio stream found in {}", file_path));
    }

    let mut duration = fmt
        .duration
        .as_deref()
        .and_then(|d| d.parse::<f64>().ok())
        .unwrap_or(0.0);
    if duration == 0.0 {
        duration = video_stream
            .and_then(|vs| vs.duration.as_deref())
            .and_then(|d| d.parse::<f64>().ok())
            .unwrap_or(0.0);
    }
    if duration == 0.0 {
        duration = audio_stream
            .and_then(|a| a.duration.as_deref())
            .and_then(|d| d.parse::<f64>().ok())
            .unwrap_or(0.0);
    }

    let width = video_stream.and_then(|vs| vs.width);
    let height = video_stream.and_then(|vs| vs.height);
    let codec = video_stream
        .and_then(|vs| vs.codec_name.clone())
        .or_else(|| audio_stream.and_then(|a| a.codec_name.clone()))
        .unwrap_or_else(|| "unknown".to_string());
    let format = fmt.format_name.unwrap_or_else(|| "unknown".to_string());
    let size = fmt
        .size
        .as_deref()
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(0);

    let frame_rate = video_stream
        .and_then(|vs| vs.r_frame_rate.as_deref())
        .map(|r| {
            let parts: Vec<&str> = r.split('/').collect();
            if parts.len() == 2 {
                let num = parts[0].parse::<f64>().unwrap_or(0.0);
                let den = parts[1].parse::<f64>().unwrap_or(0.0);
                if den != 0.0 { num / den } else { 0.0 }
            } else {
                0.0
            }
        })
        .unwrap_or(0.0);

    Ok(VideoMetadata {
        duration,
        width,
        height,
        format,
        codec,
        frame_rate,
        size,
        audio_present: audio_stream.is_some(),
    })
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

        parse_ffprobe_output(data, file_path)
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

    pub async fn stretch_audio(
        &self, input_path: &str, output_path: &str, factor: f64,
    ) -> Result<bool> {
        let mut filters: Vec<String> = Vec::new();
        let mut rem = factor;
        while rem > 2.0 { filters.push("atempo=2.0".to_string()); rem /= 2.0; }
        while rem < 0.5 { filters.push("atempo=0.5".to_string()); rem *= 2.0; }
        filters.push(format!("atempo={rem:.4}"));
        let filter_str = filters.join(",");
        let out = Command::new(&self.ffmpeg_path)
            .args(["-i", input_path, "-filter:a", &filter_str,
                   "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg stretch_audio spawn failed: {}", e))?;
        if !out.status.success() { return Ok(false); }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }

    pub async fn fit_audio_to_duration(
        &self, input_path: &str, output_path: &str, target: f64,
    ) -> Result<bool> {
        let actual = self.get_audio_duration(input_path).await;
        if actual <= 0.0 {
            return Err(anyhow!("fit_audio: cannot probe duration of {}", input_path));
        }
        let diff = actual - target;
        let mut cmd = Command::new(&self.ffmpeg_path);
        cmd.arg("-i").arg(input_path);
        if diff.abs() <= 0.02 {
            // close enough — normalize format only
        } else if diff > 0.0 {
            cmd.arg("-t").arg(format!("{target:.6}"));
        } else {
            cmd.args([
                "-filter_complex", &format!("[0:a]apad=whole_dur={target:.6}[aout]"),
                "-map", "[aout]",
                "-t", &format!("{target:.6}"),
            ]);
        }
        cmd.args(["-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-y", output_path]);
        let out = cmd.output().await.map_err(|e| anyhow!("ffmpeg fit_audio spawn failed: {}", e))?;
        if !out.status.success() { return Ok(false); }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }

    pub async fn generate_silence(&self, output_path: &str, duration: f64) -> Result<bool> {
        let out = Command::new(&self.ffmpeg_path)
            .args(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                   "-t", &format!("{duration:.6}"),
                   "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg generate_silence spawn failed: {}", e))?;
        if !out.status.success() { return Ok(false); }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }

    pub async fn concat_audio(&self, list_file: &str, output_path: &str) -> Result<bool> {
        let out = Command::new(&self.ffmpeg_path)
            .args(["-f", "concat", "-safe", "0", "-i", list_file,
                   "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg concat_audio spawn failed: {}", e))?;
        if !out.status.success() {
            let stderr = String::from_utf8_lossy(&out.stderr);
            return Err(anyhow!("ffmpeg concat_audio failed: {}", stderr));
        }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }

    pub async fn replace_video_audio(
        &self,
        video_path: &str,
        audio_path: &str,
        output_path: &str,
        video_duration: Option<f64>,
    ) -> Result<bool> {
        let apad = match video_duration {
            Some(d) if d > 0.0 => format!("[1:a]apad=whole_dur={d:.6}[aout]"),
            _ => "[1:a]apad[aout]".to_string(),
        };
        let out = Command::new(&self.ffmpeg_path)
            .args(["-i", video_path, "-i", audio_path,
                   "-filter_complex", &apad,
                   "-map", "0:v:0", "-map", "[aout]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                   "-shortest", "-y", output_path])
            .output().await
            .map_err(|e| anyhow!("ffmpeg replace_video_audio spawn failed: {}", e))?;
        if !out.status.success() {
            let stderr = String::from_utf8_lossy(&out.stderr);
            return Err(anyhow!("ffmpeg replace_video_audio failed: {}", stderr));
        }
        match tokio::fs::metadata(output_path).await {
            Ok(m) if m.len() > 0 => Ok(true),
            _ => Ok(false),
        }
    }
}

#[cfg(test)]
mod tests;
