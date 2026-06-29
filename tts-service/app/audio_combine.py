"""Audio-only combine pipeline: stretch, fit, and concatenate TTS segment WAVs.

Extracted from backend/app/dubbing/service.py (phases 3–5) as a sync ffmpeg helper.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SegmentInfo:
    segment_id: int
    start: float
    end: float
    tts_duration: Optional[float] = None


def get_audio_duration(file_path: str) -> float:
    """Return duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return 0.0
        return float(result.stdout.strip() or 0.0)
    except (ValueError, OSError) as exc:
        logger.warning("[audio_combine] duration probe failed for %s: %s", file_path, exc)
        return 0.0


def calculate_stretch_factor(
    target_duration: float,
    actual_duration: float,
    *,
    min_stretch: float | None = None,
    max_stretch: float | None = None,
) -> float:
    """Compute clamped atempo stretch factor (actual/target)."""
    min_stretch = min_stretch if min_stretch is not None else settings.DUBBING_MIN_STRETCH_RATIO
    max_stretch = max_stretch if max_stretch is not None else settings.DUBBING_MAX_STRETCH_RATIO
    if target_duration <= 0:
        return 1.0
    required = actual_duration / target_duration
    return max(min_stretch, min(max_stretch, required))


def _run_ffmpeg(cmd: List[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            logger.error("[audio_combine] ffmpeg failed: %s", result.stderr.decode()[-500:])
            return False
        return True
    except OSError as exc:
        logger.error("[audio_combine] ffmpeg error: %s", exc)
        return False


def apply_time_stretch(input_path: str, output_path: str, stretch_factor: float) -> bool:
    """Chain atempo filters (each must be in [0.5, 2.0])."""
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
    cmd = [
        "ffmpeg",
        "-i",
        input_path,
        "-filter:a",
        filter_str,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-acodec",
        "pcm_s16le",
        "-y",
        output_path,
    ]
    if not _run_ffmpeg(cmd):
        return False
    return Path(output_path).exists()


def fit_audio_to_duration(input_path: str, output_path: str, target_duration: float) -> bool:
    """Pad or trim audio to exactly target_duration seconds."""
    actual = get_audio_duration(input_path)
    if actual <= 0:
        return False

    diff = actual - target_duration
    if abs(diff) <= 0.02:
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-ar",
            "44100",
            "-ac",
            "2",
            "-acodec",
            "pcm_s16le",
            "-y",
            output_path,
        ]
    elif diff > 0:
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-t",
            f"{target_duration:.6f}",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-acodec",
            "pcm_s16le",
            "-y",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-filter_complex",
            f"[0:a]apad=whole_dur={target_duration:.6f}[aout]",
            "-map",
            "[aout]",
            "-t",
            f"{target_duration:.6f}",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-acodec",
            "pcm_s16le",
            "-y",
            output_path,
        ]
    if not _run_ffmpeg(cmd):
        return False
    return Path(output_path).exists()


def generate_silence(output_path: Path, duration: float) -> bool:
    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        f"{duration:.6f}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-acodec",
        "pcm_s16le",
        "-y",
        str(output_path),
    ]
    if not _run_ffmpeg(cmd):
        return False
    return output_path.exists()


def prepare_audio_timeline(
    processed: List[dict],
    silence_threshold: float | None = None,
) -> List[Tuple[Path, float]]:
    """Return list of (audio_path, gap_after_seconds)."""
    threshold = (
        silence_threshold
        if silence_threshold is not None
        else settings.DUBBING_SILENCE_THRESHOLD
    )
    timeline: List[Tuple[Path, float]] = []
    for i, seg in enumerate(processed):
        if i < len(processed) - 1:
            current_end = seg["segment_info"].end
            next_start = processed[i + 1]["segment_info"].start
            gap = max(0.0, next_start - current_end)
            if gap < threshold:
                gap = 0.0
        else:
            gap = 0.0
        timeline.append((seg["output_path"], gap))
    return timeline


def merge_audio_segments(processed: List[dict], session_dir: Path) -> Path:
    """Concatenate processed segments with leading silence and inter-segment gaps."""
    concat_file = session_dir / "concat_list.txt"
    final_audio = session_dir / "final_audio.wav"
    timeline = prepare_audio_timeline(processed)

    with open(concat_file, "w", encoding="utf-8") as f:
        first_start = processed[0]["segment_info"].start if processed else 0.0
        if first_start > 0.001:
            leading_path = session_dir / "silence_leading.wav"
            if generate_silence(leading_path, first_start):
                f.write(f"file '{leading_path}'\n")

        for i, (audio_path, gap) in enumerate(timeline):
            f.write(f"file '{audio_path}'\n")
            if gap > 0.0:
                silence_path = session_dir / f"silence_{i}.wav"
                if generate_silence(silence_path, gap):
                    f.write(f"file '{silence_path}'\n")

    cmd = [
        "ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-ar",
        "44100",
        "-ac",
        "2",
        "-acodec",
        "pcm_s16le",
        "-y",
        str(final_audio),
    ]
    if not _run_ffmpeg(cmd):
        raise RuntimeError("Audio concatenation failed")
    if not final_audio.exists():
        raise RuntimeError("Concat succeeded but final_audio.wav was not created")
    return final_audio


def process_segment_audio(
    seg_info: SegmentInfo,
    audio_path: Path,
    session_dir: Path,
) -> dict:
    """Stretch and fit one segment WAV to its target slot duration."""
    target = seg_info.end - seg_info.start
    actual = seg_info.tts_duration or get_audio_duration(str(audio_path)) or target
    stretch = calculate_stretch_factor(target, actual)

    processed_dir = session_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    stretched_path = processed_dir / f"segment_{seg_info.segment_id}_stretched.wav"
    if abs(stretch - 1.0) > 0.01:
        if not apply_time_stretch(str(audio_path), str(stretched_path), stretch):
            stretched_path = audio_path
    else:
        stretched_path = audio_path

    final_path = processed_dir / f"segment_{seg_info.segment_id}_processed.wav"
    if not fit_audio_to_duration(str(stretched_path), str(final_path), target):
        final_path = stretched_path

    return {
        "segment_id": seg_info.segment_id,
        "segment_info": seg_info,
        "output_path": final_path,
        "target_duration": target,
        "stretch_factor": stretch,
    }


def combine_segment_wavs(
    segments: List[dict],
    local_wav_paths: List[Path],
    session_dir: Path,
) -> bytes:
    """Combine in-memory segment WAVs using timing metadata. Returns combined WAV bytes."""
    if not segments or not local_wav_paths:
        raise ValueError("No segments to combine")

    processed: List[dict] = []
    for idx, (seg, wav_path) in enumerate(zip(segments, local_wav_paths)):
        seg_info = SegmentInfo(
            segment_id=idx,
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            tts_duration=get_audio_duration(str(wav_path)),
        )
        processed.append(process_segment_audio(seg_info, wav_path, session_dir))

    combined_path = merge_audio_segments(processed, session_dir)
    return combined_path.read_bytes()
