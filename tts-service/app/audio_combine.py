"""Stretch, fit, and concatenate per-segment TTS WAVs into one combined track.

Audio-only port of backend DubbingMergeService phases 3–6 (no video mux).
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from app.storage import download_audio

logger = logging.getLogger(__name__)

OUTPUT_SAMPLE_RATE = 44100
OUTPUT_CHANNELS = 2


@dataclass
class SegmentInfo:
    segment_id: int
    start: float
    end: float
    tts_duration: Optional[float] = None


def calculate_stretch_factor(
    target: float,
    actual: float,
    *,
    max_stretch: float = 1.2,
    min_stretch: float = 0.8,
) -> float:
    """Return clamped stretch factor (actual/target) for atempo."""
    if target <= 0:
        return 1.0
    required = actual / target
    return max(min_stretch, min(max_stretch, required))


def prepare_audio_timeline(
    processed: List[dict],
    silence_threshold: float = 0.1,
) -> List[Tuple[Path, float]]:
    """Return list of (audio_path, gap_after_seconds)."""
    timeline: List[Tuple[Path, float]] = []
    for i, seg in enumerate(processed):
        if i < len(processed) - 1:
            current_end = seg["segment_info"].end
            next_start = processed[i + 1]["segment_info"].start
            gap = max(0.0, next_start - current_end)
            if gap < silence_threshold:
                gap = 0.0
        else:
            gap = 0.0
        timeline.append((seg["output_path"], gap))
    return timeline


def _run_ffmpeg(args: List[str]) -> None:
    cmd = ["ffmpeg", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")


def _get_audio_duration(path: str) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0.0
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return 0.0
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or 0)
    if duration > 0:
        return duration
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            d = float(stream.get("duration") or 0)
            if d > 0:
                return d
    return 0.0


def _apply_time_stretch(input_path: str, output_path: str, stretch_factor: float) -> bool:
    filters: List[str] = []
    rem = stretch_factor
    while rem > 2.0:
        filters.append("atempo=2.0")
        rem /= 2.0
    while rem < 0.5:
        filters.append("atempo=0.5")
        rem *= 2.0
    filters.append(f"atempo={rem:.4f}")
    filter_str = ",".join(filters)
    try:
        _run_ffmpeg([
            "-i", input_path,
            "-filter:a", filter_str,
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-acodec", "pcm_s16le",
            output_path,
        ])
        return Path(output_path).exists()
    except RuntimeError as exc:
        logger.warning("[audio_combine] time-stretch failed: %s", exc)
        return False


def _fit_audio_to_duration(input_path: str, output_path: str, target_duration: float) -> bool:
    actual = _get_audio_duration(input_path)
    if actual <= 0:
        logger.warning("[audio_combine] could not read duration of %s", input_path)
        return False

    diff = actual - target_duration
    if abs(diff) <= 0.02:
        args = [
            "-i", input_path,
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-acodec", "pcm_s16le",
            output_path,
        ]
    elif diff > 0:
        args = [
            "-i", input_path,
            "-t", f"{target_duration:.6f}",
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-acodec", "pcm_s16le",
            output_path,
        ]
    else:
        args = [
            "-i", input_path,
            "-filter_complex", f"[0:a]apad=whole_dur={target_duration:.6f}[aout]",
            "-map", "[aout]",
            "-t", f"{target_duration:.6f}",
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-acodec", "pcm_s16le",
            output_path,
        ]

    try:
        _run_ffmpeg(args)
        return Path(output_path).exists()
    except RuntimeError as exc:
        logger.warning("[audio_combine] fit_audio failed: %s", exc)
        return False


def _generate_silence(output_path: Path, duration: float) -> bool:
    try:
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"anullsrc=r={OUTPUT_SAMPLE_RATE}:cl=stereo",
            "-t", f"{duration:.6f}",
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-acodec", "pcm_s16le",
            str(output_path),
        ])
        return output_path.exists()
    except RuntimeError as exc:
        logger.warning("[audio_combine] silence gen failed: %s", exc)
        return False


def _validate_segments(segments: List[dict]) -> List[Tuple[SegmentInfo, str]]:
    """Return (SegmentInfo, tts_key) pairs sorted by start time."""
    valid: List[Tuple[SegmentInfo, str]] = []
    for seg in segments:
        tts_key = seg.get("tts_key")
        if not tts_key or seg.get("tts_error"):
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or 0.0)
        if end <= start:
            logger.warning(
                "[audio_combine] segment %s invalid timing start=%.3f end=%.3f — skipping",
                seg.get("segment_id"), start, end,
            )
            continue
        seg_id = int(seg.get("segment_id", len(valid)))
        valid.append((SegmentInfo(segment_id=seg_id, start=start, end=end), tts_key))
    valid.sort(key=lambda pair: pair[0].start)
    return valid


def _download_segments(
    validated: List[Tuple[SegmentInfo, str]],
    session_dir: Path,
) -> List[Tuple[SegmentInfo, Path]]:
    audio_dir = session_dir / "audio_segments"
    audio_dir.mkdir(exist_ok=True)
    downloaded: List[Tuple[SegmentInfo, Path]] = []

    for seg_info, tts_key in validated:
        local_path = audio_dir / f"segment_{seg_info.segment_id}.wav"
        wav_bytes = download_audio(tts_key)
        if not wav_bytes:
            logger.error("[audio_combine] failed to download segment %s from %s", seg_info.segment_id, tts_key)
            continue
        local_path.write_bytes(wav_bytes)
        dur = _get_audio_duration(str(local_path))
        if dur > 0:
            seg_info.tts_duration = dur
        downloaded.append((seg_info, local_path))

    if not downloaded:
        raise ValueError("Failed to download any TTS segments from S3")
    return downloaded


def _process_segments(
    downloaded: List[Tuple[SegmentInfo, Path]],
    session_dir: Path,
    max_stretch: float,
    min_stretch: float,
) -> List[dict]:
    processed_dir = session_dir / "processed"
    processed_dir.mkdir(exist_ok=True)
    processed: List[dict] = []

    for seg_info, audio_path in downloaded:
        target = seg_info.end - seg_info.start
        actual = seg_info.tts_duration or target
        stretch = calculate_stretch_factor(target, actual, max_stretch=max_stretch, min_stretch=min_stretch)
        seg_id = seg_info.segment_id

        stretched_path = processed_dir / f"segment_{seg_id}_stretched.wav"
        if abs(stretch - 1.0) > 0.01:
            ok = _apply_time_stretch(str(audio_path), str(stretched_path), stretch)
            if not ok:
                stretched_path = audio_path
        else:
            stretched_path = audio_path

        final_path = processed_dir / f"segment_{seg_id}_processed.wav"
        ok = _fit_audio_to_duration(str(stretched_path), str(final_path), target)
        if not ok:
            final_path = stretched_path

        processed.append({
            "segment_id": seg_id,
            "segment_info": seg_info,
            "output_path": final_path,
        })

    return processed


def _concat_segments(processed: List[dict], session_dir: Path, silence_threshold: float) -> Path:
    concat_file = session_dir / "concat_list.txt"
    final_audio = session_dir / "final_audio.wav"
    timeline = prepare_audio_timeline(processed, silence_threshold=silence_threshold)

    with open(concat_file, "w", encoding="utf-8") as f:
        first_start = processed[0]["segment_info"].start if processed else 0.0
        if first_start > 0.001:
            leading_path = session_dir / "silence_leading.wav"
            if _generate_silence(leading_path, first_start):
                f.write(f"file '{leading_path}'\n")

        for i, (audio_path, gap) in enumerate(timeline):
            f.write(f"file '{audio_path}'\n")
            if gap > 0.0:
                silence_path = session_dir / f"silence_{i}.wav"
                if _generate_silence(silence_path, gap):
                    f.write(f"file '{silence_path}'\n")

    _run_ffmpeg([
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-ar", str(OUTPUT_SAMPLE_RATE),
        "-ac", str(OUTPUT_CHANNELS),
        "-acodec", "pcm_s16le",
        str(final_audio),
    ])
    if not final_audio.exists():
        raise RuntimeError("Audio concatenation succeeded but final_audio.wav was not created")
    return final_audio


def combine_segment_wavs(
    segments: List[dict],
    temp_dir: Optional[Path] = None,
    *,
    max_stretch: float = 1.2,
    min_stretch: float = 0.8,
    silence_threshold: float = 0.1,
) -> Path:
    """Download segment WAVs from S3, stretch/fit to timing, return local combined WAV."""
    validated = _validate_segments(segments)
    if not validated:
        raise ValueError("No valid TTS segments with tts_key to combine")

    session_dir = temp_dir or Path(tempfile.mkdtemp(prefix="tts_combine_"))
    session_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[audio_combine] combining %d segments in %s", len(validated), session_dir)
    downloaded = _download_segments(validated, session_dir)
    processed = _process_segments(downloaded, session_dir, max_stretch, min_stretch)
    combined = _concat_segments(processed, session_dir, silence_threshold)
    logger.info("[audio_combine] combined WAV ready: %s (%.1f KB)", combined, combined.stat().st_size / 1024)
    return combined
