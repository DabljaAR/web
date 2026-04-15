"""Dubbing merge service."""

from __future__ import annotations
from app.config import settings
import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from .schemas import DubbingMergeResponse, SegmentTimingInfo

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[float, str], Awaitable[None]]]


class DubbingMergeService:
    def __init__(self) -> None:
        from app.media.ffmpeg_service import FFmpegService
        from app.media.storage import get_storage_service

        self.ffmpeg = FFmpegService()
        self.storage = get_storage_service()
        self.max_stretch = 1.2
        self.min_stretch = 0.8
        self.silence_threshold = 0.1
        self.temp_dir = Path(settings.DUBBING_MERGE_PATH)
        self._tts_sample_rate = 44100
        self._tts_channels = 2

    async def merge_segments(
        self,
        video_id: str,
        segments: List[SegmentTimingInfo],
        job_id: Optional[str] = None,
        progress_callback: ProgressCallback = None,
        *,
        media_type: str = "video",
        output_key_prefix: str = "dubbed",
        original_media_key: Optional[str] = None,
        combined_audio_key: Optional[str] = None,
    ) -> DubbingMergeResponse:
        run_id = job_id or str(uuid4())
        session_dir = self.temp_dir / run_id
        session_dir.mkdir(parents=True, exist_ok=True)
        started = time.time()

        try:
            valid_segments = await self._validate_segments(segments)
            if not valid_segments:
                raise ValueError("No valid segments to merge.")

            downloaded = await self._download_tts_segments(valid_segments, session_dir, progress_callback)
            if not downloaded:
                raise RuntimeError("No TTS segment files could be downloaded.")

            stretch_info = await self._calculate_stretch_factors(downloaded)
            processed = await self._process_audio_segments(stretch_info, session_dir, progress_callback)
            if not processed:
                raise RuntimeError("No processed audio segments available after stretch/trim.")

            merged_audio = await self._merge_audio_segments(processed, session_dir)

            combined_key = combined_audio_key or f"tts/{run_id}/combined_{run_id}.wav"
            combined_key = await self._upload_output(merged_audio, combined_key, content_type="audio/wav")
            combined_url = await self.storage.get_url(combined_key)

            normalized_media_type = self._normalize_media_type(media_type)
            output_key = combined_key
            output_url = combined_url

            if normalized_media_type == "video":
                if not original_media_key:
                    raise ValueError("original_media_key is required for video mux output.")

                muxed_video = await self._merge_with_video(
                    original_media_key=original_media_key,
                    audio_path=merged_audio,
                    session_dir=session_dir,
                )
                dubbed_key = f"{output_key_prefix.strip('/')}/{run_id}.mp4"
                output_key = await self._upload_output(muxed_video, dubbed_key, content_type="video/mp4")
                output_url = await self.storage.get_url(output_key)

            return DubbingMergeResponse(
                job_id=run_id,
                video_id=video_id,
                output_key=output_key,
                output_url=output_url,
                metadata={
                    "processing_time": round(time.time() - started, 3),
                    "segments_total": len(valid_segments),
                    "segments_processed": len(processed),
                    "media_type": normalized_media_type,
                    "combined_audio_key": combined_key,
                    "combined_audio_url": combined_url,
                },
            )
        finally:
            self._cleanup_temp_files(session_dir)

    async def _validate_segments(self, segments: List[SegmentTimingInfo]) -> List[SegmentTimingInfo]:
        valid: List[SegmentTimingInfo] = []
        for segment in segments:
            if not segment.tts_audio_key:
                logger.warning("Skipping segment %s: missing TTS key", segment.segment_id)
                continue
            if segment.end <= segment.start:
                logger.warning("Skipping segment %s: invalid timing", segment.segment_id)
                continue
            valid.append(segment)

        valid.sort(key=lambda item: item.start)
        return valid

    async def _download_tts_segments(
        self,
        segments: List[SegmentTimingInfo],
        session_dir: Path,
        progress_callback: ProgressCallback = None,
    ) -> List[Tuple[SegmentTimingInfo, Path]]:
        session_dir.mkdir(parents=True, exist_ok=True)
        downloaded: List[Tuple[SegmentTimingInfo, Path]] = []
        format_detected = False

        for index, segment in enumerate(segments):
            if not segment.tts_audio_key:
                continue

            ext = Path(segment.tts_audio_key).suffix or ".wav"
            local_path = session_dir / f"segment_{segment.segment_id}{ext}"
            ok = await self.storage.download(segment.tts_audio_key, str(local_path))
            if not ok or not local_path.exists():
                logger.warning("Failed to download segment %s", segment.segment_id)
                continue

            get_audio_duration = getattr(self.ffmpeg, "get_audio_duration", None)
            if callable(get_audio_duration):
                duration = await get_audio_duration(str(local_path))
                if duration:
                    segment.tts_duration = duration

            if not format_detected:
                self._tts_sample_rate, self._tts_channels = await self._detect_audio_format(str(local_path))
                format_detected = True

            downloaded.append((segment, local_path))

            if progress_callback:
                await progress_callback((index + 1) / max(len(segments), 1), "download")

        return downloaded

    async def _detect_audio_format(self, audio_path: str) -> Tuple[int, int]:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            audio_path,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return self._tts_sample_rate, self._tts_channels

        raw = stdout.decode().strip()
        try:
            rate, channels = raw.split(",", maxsplit=1)
            return int(rate), int(channels)
        except Exception:
            return self._tts_sample_rate, self._tts_channels

    async def _calculate_stretch_factors(
        self, segments: List[Tuple[SegmentTimingInfo, Path]]
    ) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for segment, path in segments:
            target_duration = max(segment.end - segment.start, 0.001)
            actual_duration = float(segment.tts_duration or target_duration)
            raw_factor = actual_duration / target_duration
            stretch_factor = max(self.min_stretch, min(self.max_stretch, raw_factor))
            stretched_duration = actual_duration / max(stretch_factor, 0.001)
            mismatch_percent = abs(actual_duration - target_duration) / target_duration * 100

            output.append(
                {
                    "segment_id": segment.segment_id,
                    "segment_info": segment,
                    "audio_path": path,
                    "target_duration": target_duration,
                    "actual_duration": actual_duration,
                    "stretch_factor": stretch_factor,
                    "stretched_duration": stretched_duration,
                    "mismatch_percent": mismatch_percent,
                    "will_trim": stretched_duration > target_duration + 0.01,
                }
            )
        return output

    async def _process_audio_segments(
        self,
        stretch_info: List[Dict[str, Any]],
        session_dir: Path,
        progress_callback: ProgressCallback = None,
    ) -> List[Dict[str, Any]]:
        session_dir.mkdir(parents=True, exist_ok=True)
        processed: List[Dict[str, Any]] = []

        for index, info in enumerate(stretch_info):
            segment_id = int(info["segment_id"])
            input_path = str(info["audio_path"])
            stretched_path = session_dir / f"segment_{segment_id}_processed.wav"
            ok = await self._apply_time_stretch(
                input_path=input_path,
                output_path=str(stretched_path),
                stretch_factor=float(info["stretch_factor"]),
            )
            if not ok:
                continue

            final_path = stretched_path
            if bool(info["will_trim"]):
                trimmed_path = session_dir / f"segment_{segment_id}_trimmed.wav"
                trimmed = await self._trim_audio(
                    input_path=str(stretched_path),
                    output_path=str(trimmed_path),
                    duration=float(info["target_duration"]),
                )
                if trimmed:
                    final_path = trimmed_path

            processed.append(
                {
                    "segment_id": segment_id,
                    "segment_info": info["segment_info"],
                    "output_path": final_path,
                    "stretch_factor": info["stretch_factor"],
                    "mismatch_percent": info["mismatch_percent"],
                }
            )

            if progress_callback:
                await progress_callback((index + 1) / max(len(stretch_info), 1), "process")

        return processed

    async def _apply_time_stretch(self, input_path: str, output_path: str, stretch_factor: float) -> bool:
        duration = 0.0
        get_audio_duration = getattr(self.ffmpeg, "get_audio_duration", None)
        if callable(get_audio_duration):
            duration = float(await get_audio_duration(input_path) or 0.0)

        remaining = max(stretch_factor, 0.01)
        filter_parts: List[str] = []
        while remaining > 2.0:
            filter_parts.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filter_parts.append("atempo=0.5")
            remaining /= 0.5
        filter_parts.append(f"atempo={remaining:.3f}")

        stretched_duration = duration / max(stretch_factor, 0.01) if duration > 0 else 0.0
        fade_duration = min(max(stretched_duration * 0.08, 0.08), stretched_duration or 0.08)
        fade_start = max(stretched_duration - fade_duration, 0.0)
        filter_parts.append(f"afade=t=out:st={fade_start:.4f}:d={fade_duration:.4f}")
        filter_arg = ",".join(filter_parts)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-filter:a",
            filter_arg,
            output_path,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return process.returncode == 0 and Path(output_path).exists()

    async def _trim_audio(self, input_path: str, output_path: str, duration: float) -> bool:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-t",
            f"{max(duration, 0.001):.6f}",
            output_path,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return process.returncode == 0 and Path(output_path).exists()

    async def _prepare_audio_timeline(
        self, processed_segments: List[Dict[str, Any]]
    ) -> Tuple[List[Tuple[Path, float]], float]:
        ordered = sorted(processed_segments, key=lambda item: item["segment_info"].start)
        leading_silence = max(float(ordered[0]["segment_info"].start), 0.0)

        timeline: List[Tuple[Path, float]] = []
        for index, segment in enumerate(ordered):
            info: SegmentTimingInfo = segment["segment_info"]
            gap_after = 0.0
            if index < len(ordered) - 1:
                next_info: SegmentTimingInfo = ordered[index + 1]["segment_info"]
                gap_after = max(next_info.start - info.end, 0.0)
                if gap_after < self.silence_threshold:
                    gap_after = 0.0
            timeline.append((Path(segment["output_path"]), gap_after))

        return timeline, leading_silence

    async def _merge_audio_segments(self, processed_segments: List[Dict[str, Any]], session_dir: Path) -> Path:
        if not processed_segments:
            raise ValueError("No processed segments to merge")

        timeline, leading_silence = await self._prepare_audio_timeline(processed_segments)

        input_paths: List[Path] = []
        if leading_silence > 0:
            lead_path = session_dir / "leading_silence.wav"
            if not await self._generate_silence(lead_path, leading_silence):
                raise RuntimeError("Failed to generate leading silence")
            input_paths.append(lead_path)

        for index, (audio_path, gap_after) in enumerate(timeline):
            input_paths.append(audio_path)
            if gap_after > 0:
                gap_path = session_dir / f"silence_gap_{index:04d}.wav"
                if not await self._generate_silence(gap_path, gap_after):
                    raise RuntimeError("Failed to generate gap silence")
                input_paths.append(gap_path)

        out_path = session_dir / "merged_audio.wav"
        cmd = ["ffmpeg", "-y"]
        for path in input_paths:
            cmd.extend(["-i", str(path)])

        concat_refs = "".join(f"[{idx}:a]" for idx in range(len(input_paths)))
        filter_complex = f"{concat_refs}concat=n={len(input_paths)}:v=0:a=1[out]"
        cmd.extend(["-filter_complex", filter_complex, "-map", "[out]", str(out_path)])

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"Failed to merge processed audio segments: {stderr.decode().strip()}")
        return out_path

    async def _generate_silence(self, output_path: Path, duration: float) -> bool:
        channel_layout = "mono" if self._tts_channels == 1 else "stereo"
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={self._tts_sample_rate}:cl={channel_layout}",
            "-t",
            f"{max(duration, 0.001):.6f}",
            "-f",
            "wav",
            str(output_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return process.returncode == 0 and output_path.exists()

    async def _merge_with_video(self, original_media_key: str, audio_path: Path, session_dir: Path) -> Path:
        ext = Path(original_media_key).suffix or ".mp4"
        source_video = session_dir / f"source_video{ext}"
        downloaded = await self.storage.download(original_media_key, str(source_video))
        if not downloaded or not source_video.exists():
            raise RuntimeError(f"Failed to download original media for mux: {original_media_key}")

        final_audio_for_mux = audio_path
        try:
            # 1) Extract original soundtrack.
            original_audio = session_dir / "original_audio.wav"
            extract_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(source_video),
                "-vn",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(original_audio),
            ]
            extract_proc = await asyncio.create_subprocess_exec(
                *extract_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await extract_proc.communicate()
            if extract_proc.returncode == 0 and original_audio.exists():
                # 2) Try to isolate background/music (no vocals) via Demucs.
                demucs_out = session_dir / "demucs_out"
                demucs_cmd = [
                    "demucs",
                    "--two-stems",
                    "vocals",
                    "--out",
                    str(demucs_out),
                    "--name",
                    "htdemucs",
                    str(original_audio),
                ]
                demucs_proc = await asyncio.create_subprocess_exec(
                    *demucs_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await demucs_proc.communicate()

                no_vocals_candidates = list(demucs_out.rglob("no_vocals.wav"))
                if demucs_proc.returncode == 0 and no_vocals_candidates:
                    # 3) Mix dubbed speech timeline with background/music bed.
                    mixed_audio = session_dir / "dubbed_with_background.wav"
                    mix_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(audio_path),
                        "-i",
                        str(no_vocals_candidates[0]),
                        "-filter_complex",
                        "[0:a]volume=1.0[dub];[1:a]aresample=44100,volume=0.75[bg];[dub][bg]amix=inputs=2:duration=first:normalize=0[out]",
                        "-map",
                        "[out]",
                        "-ar",
                        "44100",
                        "-ac",
                        "2",
                        str(mixed_audio),
                    ]
                    mix_proc = await asyncio.create_subprocess_exec(
                        *mix_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    await mix_proc.communicate()
                    if mix_proc.returncode == 0 and mixed_audio.exists():
                        final_audio_for_mux = mixed_audio
                else:
                    logger.warning("Demucs unavailable/failed; muxing with dubbed audio only.")
        except FileNotFoundError:
            logger.warning("Demucs binary not found; muxing with dubbed audio only.")
        except Exception as exc:
            logger.warning("Background track mix failed, falling back to dubbed-only audio: %s", exc)

        output_path = session_dir / "dubbed_output.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video),
            "-i",
            str(final_audio_for_mux),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"Video mux failed: {stderr.decode().strip()}")
        return output_path

    async def _upload_output(
        self, local_path: Path, output_key: str, content_type: Optional[str] = None
    ) -> str:
        resolved_content_type = content_type or self._resolve_content_type(local_path)
        return await self.storage.upload_file(str(local_path), output_key, resolved_content_type)

    def _resolve_content_type(self, local_path: Path) -> str:
        suffix = local_path.suffix.lower()
        if suffix == ".mp4":
            return "video/mp4"
        if suffix in {".wav", ".wave"}:
            return "audio/wav"
        if suffix == ".mp3":
            return "audio/mpeg"
        return "application/octet-stream"

    def _normalize_media_type(self, media_type: str) -> str:
        normalized = (media_type or "video").strip().lower()
        if normalized in {"audio", "text"}:
            return "audio"
        return "video"

    def _cleanup_temp_files(self, session_dir: Path) -> None:
        try:
            if session_dir.exists():
                shutil.rmtree(session_dir)
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logger.warning("Failed to cleanup session dir %s: %s", session_dir, exc)
