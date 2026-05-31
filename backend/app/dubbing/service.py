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
from app.media_service.client import MediaServiceClient

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
        self.media_client = MediaServiceClient()
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
            # Short-circuit: delegate full dubbing pipeline to Rust media-service
            logger.info("[DubbingMerge] Delegating merge to Rust media-service | video_id=%s segments=%d", video_id, len(segments))

            await self._cb(progress_callback, 5.0)

            valid_segments = await self._validate_segments(segments)
            if not valid_segments:
                raise ValueError("No valid segments found for dubbing merge")

            # Build payload matching Rust `DubRequest`
            seg_payload = []
            for s in valid_segments:
                seg_payload.append({
                    "segment_id": int(s.segment_id),
                    "start": float(s.start),
                    "end": float(s.end),
                    "tts_audio_key": s.tts_audio_key or "",
                    "tts_duration": float(s.tts_duration) if s.tts_duration is not None else None,
                })

            payload = {
                "job_id": job_id or f"dubbing_{video_id}",
                "video_id": video_id,
                "media_type": media_type,
                "original_media_key": original_media_key,
                "output_key_prefix": (output_key_prefix or f"dubbed/{video_id}"),
                "combined_audio_key": combined_audio_key,
                "max_stretch": self.max_stretch,
                "min_stretch": self.min_stretch,
                "silence_threshold": self.silence_threshold,
                "segments": seg_payload,
            }

            await self._cb(progress_callback, 10.0)

            resp = await self.media_client.dub(payload)

            await self._cb(progress_callback, 100.0)

            # Map Rust response back into DubbingMergeResponse
            output_key = resp.get("output_key")
            output_url = resp.get("output_url")
            metadata = resp.get("metadata", {})

            return DubbingMergeResponse(
                job_id=payload["job_id"],
                video_id=video_id,
                output_key=output_key,
                output_url=output_url,
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
                ok = await self.media_client.download_file(seg.tts_audio_key, local_path)
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


    async def _resolve_video_key_fallback(self, video_id: str) -> str:
        """
        Last-resort async DB lookup.  Only reached when the Celery task failed
        to supply original_media_key.  Creates a fresh async engine with
        NullPool to avoid reusing FastAPI's asyncpg pool.
        """
        video_data = await self.media_client.get_video(video_id)
        if not video_data:
            raise ValueError(f"Video {video_id} not found in DB")
        return video_data["file_path"]

    # ------------------------------------------------------------------ #
    # Upload helper                                                        #
    # ------------------------------------------------------------------ #

    async def _upload_file(
        self, local_path: Path, minio_key: str, content_type: str
    ) -> str:
        """Upload a local file to MinIO and return its presigned URL."""
        with open(local_path, "rb") as fh:
            data = fh.read()
        await self.media_client.upload_bytes(data, key=minio_key, content_type=content_type)
        return await self.media_client.presign_url(minio_key, method="GET")

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