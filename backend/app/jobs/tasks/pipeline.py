"""Segment processing helpers (legacy Celery pipeline utilities).

TTS synthesis is handled by tts-service via RabbitMQ. These helpers remain
for processing_mode normalization used in tests and legacy code paths.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _apply_processing_mode(
    *,
    segments: list[dict],
    words: Optional[list[dict]],
    transcript: str,
    duration: Optional[float],
    processing_mode: str,
) -> list[dict]:
    """Normalize STT segments according to the selected processing mode."""
    requested_mode = str(processing_mode or "").strip().lower()
    legacy_aliases = {
        "single_chunk": "single",
        "segmented": "stt_focused",
        "true": "single",
        "false": "stt_focused",
    }
    mode = legacy_aliases.get(requested_mode, requested_mode)
    if mode != requested_mode:
        logger.warning(
            "Legacy processing_mode=%r normalized to %r",
            processing_mode,
            mode,
        )

    if mode not in {"stt_focused", "single", "tts_focused"}:
        logger.warning(
            "Unknown processing_mode=%r. Falling back to 'single'.",
            processing_mode,
        )
        mode = "single"

    if mode == "tts_focused":
        rebuilt = _rebuild_segments_from_words(words or [])
        if rebuilt:
            return rebuilt
        return segments

    if mode != "single":
        return segments

    if not segments or not transcript.strip():
        return segments

    end = duration
    if end is None:
        end = segments[-1].get("end")

    try:
        end_value = round(float(end if end is not None else 0.0), 2)
    except (TypeError, ValueError):
        end_value = 0.0

    return [{"start": 0.0, "end": max(0.0, end_value), "text": transcript.strip()}]


def _rebuild_segments_from_words(
    words: list[dict],
    *,
    min_words: int = 10,
    max_words: int = 30,
) -> list[dict]:
    """Rebuild segments from word timestamps using punctuation-aware boundaries."""
    if not words:
        return []

    rebuilt_segments: list[dict] = []
    current_words: list[dict] = []

    for word_item in words:
        current_words.append(word_item)
        word_count = len(current_words)
        last_word = str(current_words[-1].get("word") or "")

        if word_count >= min_words and re.search(r"[.]", last_word):
            rebuilt_segments.append(
                {
                    "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                    "start": float(current_words[0].get("start") or 0.0),
                    "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
                }
            )
            current_words = []
        elif word_count >= max_words:
            rebuilt_segments.append(
                {
                    "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                    "start": float(current_words[0].get("start") or 0.0),
                    "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
                }
            )
            current_words = []

    if current_words:
        rebuilt_segments.append(
            {
                "text": " ".join(str(x.get("word") or "") for x in current_words).strip(),
                "start": float(current_words[0].get("start") or 0.0),
                "end": float(current_words[-1].get("end") or current_words[0].get("start") or 0.0),
            }
        )

    return rebuilt_segments
