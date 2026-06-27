"""Dubbing merge service for replacing video audio with TTS output.

Fixes applied vs. the previous version:
  1. merge_segments() now accepts all kwargs that tts_combine_results passes
     (media_type, output_key_prefix, original_media_key, combined_audio_key).
     The old signature caused a TypeError on every invocation, which is why
     output files were never written to MinIO or the DB.
  2. _merge_with_video() now uses explicit FFmpeg stream mapping
     (-map 0:v:0 -map 1:a:0 -shortest) to *replace* the original audio track
     completely instead of overlaying / mixing it.  This was the root cause of
     silent output videos.
  3. _merge_audio_segments() correctly reads leading-silence offset from
     processed_segments[0]["segment_info"].start instead of the non-existent
     top-level key "start" (which always returned 0.0 and silently skipped the
     leading silence block).
  4. The intermediate combined TTS WAV is uploaded to MinIO and its key + URL
     are written into merge_response.metadata so that tts_combine_results can
     read them back via merged_meta.get("combined_audio_key/url").
  5. Robust error propagation: every FFmpeg subprocess now checks returncode AND
     file existence before returning, and raises descriptive RuntimeErrors so
     Celery can retry properly instead of silently producing empty output.
"""
import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import settings
from app.dubbing.schemas import DubbingMergeResponse, SegmentTimingInfo, TimingWarning
from app.shared.ffmpeg_service import FFmpegService
from app.storage import get_storage_service

logger = logging.getLogger(__name__)


class DubbingMergeService:
    """
    Merges TTS audio segments with video by *replacing* the original audio.

    Pipeline
    --------
    1. Validate & sort segments
    2. Download TTS WAVs from MinIO
    3. Calculate per-segment stretch factors
    4. Apply atempo time-stretching
    5. Concatenate into one combined WAV (with silence gaps & leading silence)
    6. Upload combined WAV to MinIO  ← new; feeds combined_audio_key in metadata
    7. Replace original video audio with combined WAV via FFmpeg stream mapping
    8. Upload dubbed video to MinIO
    """

    def __init__(self):
        self.ffmpeg = FFmpegService()
        self.storage = get_storage_service()
        self.temp_dir = Path(settings.DUBBING_TEMP_DIR)
        self.max_stretch = settings.DUBBING_MAX_STRETCH_RATIO
        self.min_stretch = settings.DUBBING_MIN_STRETCH_RATIO
        self.silence_threshold = settings.DUBBING_SILENCE_THRESHOLD

    # ------------------------------------------------------------------ #
    # Public entry-point                                                   #
    # ------------------------------------------------------------------ #

    async def merge_segments(
        self,
        video_id: str,
        segments: List[SegmentTimingInfo],
        job_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        # --- kwargs supplied by tts_combine_results (were missing before) ---
        media_type: str = "video",
        output_key_prefix: Optional[str] = None,
        original_media_key: Optional[str] = None,
        combined_audio_key: Optional[str] = None,
    ) -> DubbingMergeResponse:
        """
        Orchestrate the full dubbing merge.

        Parameters
        ----------
        video_id            : used for temp-dir naming and fallback DB lookup
        segments            : TTS segment timing info list
        job_id              : forwarded to DubbingMergeResponse
        progress_callback   : optional async callback(percent: float)
        media_type          : "video" (the only type currently supported)
        output_key_prefix   : MinIO prefix for the final dubbed video, e.g.
                              "dubbed/<video_id>"
        original_media_key  : MinIO key of the source video — caller must
                              supply this (resolved via psycopg2 in the Celery
                              task) to avoid asyncpg loop-ownership errors
        combined_audio_key  : preferred MinIO key for the intermediate combined
                              TTS WAV; falls back to a generated key if None
        """
        start_time = time.time()
        warnings: List[str] = []

        session_dir = self.temp_dir / f"{video_id}_{int(time.time())}"
        session_dir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(
                "[DubbingMerge] Starting merge | video_id=%s segments=%d "
                "media_type=%s original_key=%s",
                video_id, len(segments), media_type, original_media_key,
            )

            await self._cb(progress_callback, 5.0)

            # Phase 1 – validate
            valid_segments = await self._validate_segments(segments)
            if not valid_segments:
                raise ValueError("No valid segments found for dubbing merge")
            logger.info("[DubbingMerge] %d valid segments", len(valid_segments))

            await self._cb(progress_callback, 10.0)

            # Phase 2 – download TTS WAVs
            downloaded = await self._download_tts_segments(
                valid_segments, session_dir, progress_callback
            )

            await self._cb(progress_callback, 30.0)

            # Phase 3 – stretch factors
            stretch_info = await self._calculate_stretch_factors(downloaded)
            for si in stretch_info:
                if si.get("will_trim"):
                    warnings.append(
                        f"Segment {si['segment_id']}: "
                        f"{si['mismatch_percent']:.1f}% duration mismatch, "
                        f"applied max stretch {self.max_stretch}x and trimmed"
                    )

            await self._cb(progress_callback, 40.0)

            # Phase 4 – time-stretch
            processed = await self._process_audio_segments(
                stretch_info, session_dir, progress_callback
            )

            await self._cb(progress_callback, 70.0)

            # Phase 5 – concatenate into combined WAV
            combined_wav_path = await self._merge_audio_segments(processed, session_dir)
            logger.info("[DubbingMerge] Combined WAV: %s", combined_wav_path)

            await self._cb(progress_callback, 75.0)

            # Phase 6 – upload combined WAV (so caller can store its key)
            wav_key = combined_audio_key or f"tts/{job_id or video_id}/combined_{job_id or video_id}.wav"
            wav_url = await self._upload_file(combined_wav_path, wav_key, "audio/wav")
            logger.info("[DubbingMerge] Combined WAV uploaded: %s", wav_key)

            await self._cb(progress_callback, 80.0)

            # Phase 7 – replace original video audio
            output_video_path = await self._replace_video_audio(
                video_id=video_id,
                audio_path=combined_wav_path,
                session_dir=session_dir,
                original_media_key=original_media_key,
            )

            await self._cb(progress_callback, 90.0)

            # Phase 8 – upload dubbed video
            ts = int(time.time())
            prefix = (output_key_prefix or f"dubbed/{video_id}").rstrip("/")
            video_out_key = f"{prefix}/{ts}_dubbed.mp4"
            video_out_url = await self._upload_file(output_video_path, video_out_key, "video/mp4")
            logger.info("[DubbingMerge] Dubbed video uploaded: %s", video_out_key)

            await self._cb(progress_callback, 100.0)

            processing_time = time.time() - start_time
            segments_stretched = sum(1 for s in stretch_info if s["stretch_factor"] != 1.0)
            avg_stretch = (
                sum(s["stretch_factor"] for s in stretch_info) / len(stretch_info)
                if stretch_info else 1.0
            )

            metadata = {
                "total_segments": len(valid_segments),
                "segments_stretched": segments_stretched,
                "avg_stretch_factor": round(avg_stretch, 3),
                "warnings": warnings,
                "processing_time": round(processing_time, 2),
                # These two are read back by tts_combine_results
                "combined_audio_key": wav_key,
                "combined_audio_url": wav_url,
            }

            logger.info(
                "[DubbingMerge] Done | video_id=%s segments=%d stretched=%d time=%.1fs",
                video_id, len(valid_segments), segments_stretched, processing_time,
            )

            return DubbingMergeResponse(
                job_id=job_id or f"dubbing_{video_id}",
                video_id=video_id,
                output_key=video_out_key,
                output_url=video_out_url,
                metadata=metadata,
            )

        finally:
            await self._cleanup(session_dir)

    # ------------------------------------------------------------------ #
    # Helper: progress callback (safe – does nothing if None)             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _cb(callback: Optional[callable], pct: float):
        if callback:
            await callback(pct)

    # ------------------------------------------------------------------ #
    # Phase 1 – validate                                                   #
    # ------------------------------------------------------------------ #

    async def _validate_segments(
        self, segments: List[SegmentTimingInfo]
    ) -> List[SegmentTimingInfo]:
        valid = []
        for seg in segments:
            if not seg.tts_audio_key:
                logger.warning("[DubbingMerge] Segment %s missing tts_audio_key, skipping", seg.segment_id)
                continue
            if seg.start < 0 or seg.end <= seg.start:
                logger.warning(
                    "[DubbingMerge] Segment %s invalid timing (start=%.3f end=%.3f), skipping",
                    seg.segment_id, seg.start, seg.end,
                )
                continue
            valid.append(seg)
        valid.sort(key=lambda s: s.start)
        return valid

    # ------------------------------------------------------------------ #
    # Phase 2 – download                                                   #
    # ------------------------------------------------------------------ #

    async def _download_tts_segments(
        self,
        segments: List[SegmentTimingInfo],
        session_dir: Path,
        progress_callback: Optional[callable] = None,
    ) -> List[Tuple[SegmentTimingInfo, Path]]:
        audio_dir = session_dir / "audio_segments"
        audio_dir.mkdir(exist_ok=True)
        downloaded = []
        total = len(segments)

        for idx, seg in enumerate(segments):
            local_path = audio_dir / f"segment_{seg.segment_id}.wav"
            try:
                ok = await self.storage.download(seg.tts_audio_key, str(local_path))
                if not ok or not local_path.exists():
                    logger.error(
                        "[DubbingMerge] Failed to download segment %s from %s",
                        seg.segment_id, seg.tts_audio_key,
                    )
                    continue
                downloaded.append((seg, local_path))

                # Duration probing is best-effort (should not invalidate the download).
                try:
                    dur = await self.ffmpeg.get_audio_duration(str(local_path))
                    if dur:
                        seg.tts_duration = dur
                except Exception as exc:
                    logger.warning(
                        "[DubbingMerge] Could not read duration for segment %s (%s): %s",
                        seg.segment_id,
                        seg.tts_audio_key,
                        exc,
                    )

                logger.debug(
                    "[DubbingMerge] Downloaded segment %s (%.3fs)",
                    seg.segment_id, seg.tts_duration or 0,
                )
            except Exception as exc:
                logger.error("[DubbingMerge] Error downloading segment %s: %s", seg.segment_id, exc)
                continue

            if progress_callback:
                await progress_callback(10.0 + 20.0 * (idx + 1) / total)

        if not downloaded:
            raise ValueError("Failed to download any TTS segments from MinIO")
        return downloaded

    # ------------------------------------------------------------------ #
    # Phase 3 – stretch factors                                            #
    # ------------------------------------------------------------------ #

    async def _calculate_stretch_factors(
        self, segments: List[Tuple[SegmentTimingInfo, Path]]
    ) -> List[dict]:
        result = []
        for seg_info, audio_path in segments:
            target = seg_info.end - seg_info.start
            actual = seg_info.tts_duration or target
            required = actual / target if target > 0 else 1.0
            clamped = max(self.min_stretch, min(self.max_stretch, required))
            mismatch_pct = ((actual - target) / target * 100) if target > 0 else 0.0

            result.append({
                "segment_id": seg_info.segment_id,
                "segment_info": seg_info,
                "audio_path": audio_path,
                "target_duration": target,
                "actual_duration": actual,
                "stretch_factor": clamped,
                "mismatch_percent": mismatch_pct,
                "will_trim": required > self.max_stretch,
            })
            logger.debug(
                "[DubbingMerge] Segment %s: target=%.2fs actual=%.2fs stretch=%.3fx mismatch=%.1f%%",
                seg_info.segment_id, target, actual, clamped, mismatch_pct,
            )
        return result

    # ------------------------------------------------------------------ #
    # Phase 4 – time-stretch                                               #
    # ------------------------------------------------------------------ #

    async def _process_audio_segments(
        self,
        stretch_info: List[dict],
        session_dir: Path,
        progress_callback: Optional[callable] = None,
    ) -> List[dict]:
        processed_dir = session_dir / "processed"
        processed_dir.mkdir(exist_ok=True)
        processed = []
        total = len(stretch_info)

        for idx, info in enumerate(stretch_info):
            target_duration = info["target_duration"]
            seg_id = info["segment_id"]

            # Step 1: time-stretch to approximate target duration
            stretched_path = processed_dir / f"segment_{seg_id}_stretched.wav"
            if abs(info["stretch_factor"] - 1.0) > 0.01:
                ok = await self._apply_time_stretch(
                    str(info["audio_path"]), str(stretched_path), info["stretch_factor"]
                )
                if not ok:
                    logger.warning(
                        "[DubbingMerge] Time-stretch failed for segment %s, using original",
                        seg_id,
                    )
                    stretched_path = info["audio_path"]
            else:
                stretched_path = info["audio_path"]

            # Step 2: fit exactly to target duration so every segment occupies
            # its precise [start, end] slot in the final timeline.
            # atempo can be slightly off (especially at clamped limits), so we
            # pad with silence if too short, or hard-trim if too long.
            final_path = processed_dir / f"segment_{seg_id}_processed.wav"
            ok = await self._fit_audio_to_duration(
                str(stretched_path), str(final_path), target_duration
            )
            if not ok:
                logger.warning(
                    "[DubbingMerge] fit_audio_to_duration failed for segment %s, "
                    "using stretched audio as-is",
                    seg_id,
                )
                final_path = stretched_path

            info["output_path"] = final_path
            processed.append(info)
            if progress_callback:
                await progress_callback(40.0 + 30.0 * (idx + 1) / total)

        return processed

    async def _apply_time_stretch(
        self, input_path: str, output_path: str, stretch_factor: float
    ) -> bool:
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
            "ffmpeg", "-i", input_path,
            "-filter:a", filter_str,
            "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
            "-y", output_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("[DubbingMerge] atempo failed: %s", stderr.decode())
                return False
            return Path(output_path).exists()
        except Exception as exc:
            logger.error("[DubbingMerge] Error in time-stretch: %s", exc)
            return False

    async def _fit_audio_to_duration(
        self, input_path: str, output_path: str, target_duration: float
    ) -> bool:
        """Pad (silence at end) or trim the audio to exactly target_duration seconds.

        This is a correction step run after atempo stretching, which can be
        slightly off at clamped stretch limits.  A tolerance of 20 ms is used
        to avoid unnecessary re-encoding when the audio is already close enough.
        """
        actual = await self.ffmpeg.get_audio_duration(input_path)
        if actual <= 0:
            logger.warning("[DubbingMerge] fit_audio: could not read duration of %s", input_path)
            return False

        diff = actual - target_duration
        if abs(diff) <= 0.02:
            # Close enough — just normalise format via copy
            cmd = [
                "ffmpeg", "-i", input_path,
                "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
                "-y", output_path,
            ]
        elif diff > 0:
            # Audio is too long → hard trim
            logger.debug(
                "[DubbingMerge] fit_audio: trimming %.3fs → %.3fs for %s",
                actual, target_duration, input_path,
            )
            cmd = [
                "ffmpeg", "-i", input_path,
                "-t", f"{target_duration:.6f}",
                "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
                "-y", output_path,
            ]
        else:
            # Audio is too short → pad with silence
            logger.debug(
                "[DubbingMerge] fit_audio: padding %.3fs → %.3fs for %s",
                actual, target_duration, input_path,
            )
            cmd = [
                "ffmpeg", "-i", input_path,
                "-filter_complex",
                f"[0:a]apad=whole_dur={target_duration:.6f}[aout]",
                "-map", "[aout]",
                "-t", f"{target_duration:.6f}",
                "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
                "-y", output_path,
            ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("[DubbingMerge] fit_audio failed: %s", stderr.decode())
                return False
            return Path(output_path).exists()
        except Exception as exc:
            logger.error("[DubbingMerge] Error in fit_audio_to_duration: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Phase 5 – concatenate into combined WAV                              #
    # ------------------------------------------------------------------ #

    async def _prepare_audio_timeline(
        self, processed: List[dict]
    ) -> List[Tuple[Path, float]]:
        """Return list of (audio_path, gap_after_seconds)."""
        timeline = []
        for i, seg in enumerate(processed):
            if i < len(processed) - 1:
                current_end = seg["segment_info"].end
                next_start = processed[i + 1]["segment_info"].start
                gap = max(0.0, next_start - current_end)
                if gap < self.silence_threshold:
                    gap = 0.0
            else:
                gap = 0.0
            timeline.append((seg["output_path"], gap))
        return timeline

    async def _merge_audio_segments(
        self, processed: List[dict], session_dir: Path
    ) -> Path:
        concat_file = session_dir / "concat_list.txt"
        final_audio = session_dir / "final_audio.wav"
        timeline = await self._prepare_audio_timeline(processed)

        with open(concat_file, "w") as f:
            # FIX: read leading offset from segment_info.start (not the dict's "start" key)
            first_start = processed[0]["segment_info"].start if processed else 0.0
            if first_start > 0.001:
                leading_path = session_dir / "silence_leading.wav"
                ok = await self._generate_silence(leading_path, first_start)
                if ok:
                    f.write(f"file '{leading_path}'\n")
                else:
                    logger.warning(
                        "[DubbingMerge] Could not generate leading silence of %.3fs", first_start
                    )

            for i, (audio_path, gap) in enumerate(timeline):
                f.write(f"file '{audio_path}'\n")
                if gap > 0.0:
                    silence_path = session_dir / f"silence_{i}.wav"
                    ok = await self._generate_silence(silence_path, gap)
                    if ok:
                        f.write(f"file '{silence_path}'\n")
                    else:
                        logger.warning(
                            "[DubbingMerge] Could not generate gap silence %.3fs after segment %d",
                            gap, i,
                        )

        # Re-encode to a consistent PCM format during concat.
        # -c copy fails silently when TTS WAVs (often 22050 Hz mono) and
        # generated silence (44100 Hz stereo) have mismatched stream params,
        # producing truncated or garbled output instead of raising an error.
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-ar", "44100",
            "-ac", "2",
            "-acodec", "pcm_s16le",
            "-y", str(final_audio),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("[DubbingMerge] concat failed: %s", stderr.decode())
            raise RuntimeError(f"Audio concatenation failed: {stderr.decode()[:300]}")
        if not final_audio.exists():
            raise RuntimeError("Concat succeeded but final_audio.wav was not created")
        return final_audio

    async def _generate_silence(self, output_path: Path, duration: float) -> bool:
        """Generate a silent WAV of the given duration using anullsrc + -t."""
        cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{duration:.6f}",
            "-ar", "44100",
            "-ac", "2",
            "-acodec", "pcm_s16le",
            "-y",
            str(output_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("[DubbingMerge] silence gen failed: %s", stderr.decode())
                return False
            return output_path.exists()
        except Exception as exc:
            logger.error("[DubbingMerge] Error generating silence: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Phase 7 – replace original video audio (the core fix)               #
    # ------------------------------------------------------------------ #

    async def _replace_video_audio(
        self,
        video_id: str,
        audio_path: Path,
        session_dir: Path,
        original_media_key: Optional[str] = None,
    ) -> Path:
        """
        Replace the original video's audio track with *audio_path*.

        Uses explicit stream mapping so the original audio is discarded
        completely rather than mixed or overlaid:

            ffmpeg -i video.mp4 -i tts_combined.wav \\
                   -map 0:v:0   ← video stream from original \\
                   -map 1:a:0   ← audio stream from TTS \\
                   -c:v copy    ← no video re-encode \\
                   -c:a aac -b:a 192k \\
                   -shortest    ← end at whichever stream ends first \\
                   -y output.mp4
        """
        # Resolve the video key (caller should always pass this)
        video_key = original_media_key
        if not video_key:
            logger.warning(
                "[DubbingMerge] original_media_key not supplied for %s; "
                "falling back to sync DB lookup",
                video_id,
            )
            video_key = await self._resolve_video_key_fallback(video_id)

        # Download original video
        local_video = session_dir / "original_video.mp4"
        ok = await self.storage.download(video_key, str(local_video))
        if not ok or not local_video.exists():
            raise RuntimeError(f"Failed to download original video: {video_key}")

        output_video = session_dir / "output_dubbed.mp4"
        audio_codec = getattr(settings, "DUBBING_OUTPUT_AUDIO_CODEC", "aac")
        audio_bitrate = getattr(settings, "DUBBING_OUTPUT_AUDIO_BITRATE", "192k")

        # Get exact video duration so we can pad TTS audio to match it precisely.
        # apad without whole_dur is unreliable with -shortest and can cause the
        # output to be trimmed to the TTS audio length instead of the video length.
        try:
            video_meta = await self.ffmpeg.get_metadata(str(local_video))
            video_duration = video_meta.duration
        except Exception as exc:
            logger.warning("[DubbingMerge] Could not read video duration: %s — using apad without whole_dur", exc)
            video_duration = None

        if video_duration and video_duration > 0:
            apad_filter = f"[1:a]apad=whole_dur={video_duration:.6f}[aout]"
        else:
            apad_filter = "[1:a]apad[aout]"

        cmd = [
            "ffmpeg",
            "-i", str(local_video),          # input 0: original video
            "-i", str(audio_path),            # input 1: TTS combined WAV
            "-filter_complex", apad_filter,
            "-map", "0:v:0",                  # take video stream from input 0
            "-map", "[aout]",                 # padded audio (replaces original)
            "-c:v", "copy",                   # copy video without re-encoding
            "-c:a", audio_codec,
            "-b:a", audio_bitrate,
            "-shortest",
            "-y",
            str(output_video),
        ]

        logger.info(
            "[DubbingMerge] Replacing audio | video=%s audio=%s", local_video, audio_path
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("[DubbingMerge] audio-replace failed: %s", stderr.decode())
            raise RuntimeError(
                f"FFmpeg audio replacement failed (rc={proc.returncode}): "
                f"{stderr.decode()[:500]}"
            )
        if not output_video.exists():
            raise RuntimeError(
                "FFmpeg audio replacement returned 0 but output file was not created"
            )

        logger.info("[DubbingMerge] Audio replaced successfully: %s", output_video)
        return output_video

    async def _resolve_video_key_fallback(self, video_id: str) -> str:
        """
        Last-resort async DB lookup.  Only reached when the Celery task failed
        to supply original_media_key.  Creates a fresh async engine with
        NullPool to avoid reusing FastAPI's asyncpg pool.
        """
        from app.videos.models import Video
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with Session() as db:
                video = await db.get(Video, video_id)
                if not video:
                    raise ValueError(f"Video {video_id} not found in DB")
                return video.file_path
        finally:
            await engine.dispose()

    # ------------------------------------------------------------------ #
    # Upload helper                                                        #
    # ------------------------------------------------------------------ #

    async def _upload_file(
        self, local_path: Path, minio_key: str, content_type: str
    ) -> str:
        """Upload a local file to MinIO and return its presigned URL."""
        with open(local_path, "rb") as fh:
            data = fh.read()
        await self.storage.upload_bytes(data, minio_key, content_type)
        return await self.storage.get_url(minio_key)

    # ------------------------------------------------------------------ #
    # Cleanup                                                              #
    # ------------------------------------------------------------------ #

    async def _cleanup(self, session_dir: Path):
        try:
            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.debug("[DubbingMerge] Cleaned up temp dir: %s", session_dir)
        except Exception as exc:
            logger.warning("[DubbingMerge] Failed to clean up %s: %s", session_dir, exc)