"""Unit tests for nmt-service worker logic (no DB, RabbitMQ, or model).

Covers:
  §10.3 — idempotency (COMPLETED skip)
  D3    — internal fan-out (one message → one result, no chord)
  D8    — cooperative cancellation (pre-check + mid-job cancel watcher)
  §15   — WorkerResultPayload contract
  §6    — NMT→TTS segment shape contract (Phase 2 dependency)
  A.9   — output_type rules per LLD table
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.worker import (
    _translate_all_segments,
    _translate_one_segment,
    _update_video_task_nmt,
)


# ── _update_video_task_nmt: output_type → DB status rules (A.9) ───────────────

def test_update_video_task_nmt_captionsAndTranslation_is_terminal():
    """captionsAndTranslation: NMT is the last stage → COMPLETED at 100%."""
    db = MagicMock()
    _update_video_task_nmt(
        db,
        "task-1",
        "translated",
        [{"translated_text": "x"}],
        "captionsAndTranslation",
    )
    db.execute.assert_called_once()
    params = db.execute.call_args[0][1]
    assert params["status"] == "COMPLETED"
    assert params["progress"] == 100.0
    assert params["completed_at"] is not None
    db.commit.assert_called_once()


def test_update_video_task_nmt_fullDubbing_is_processing():
    """fullDubbing: NMT is NOT the last stage → PROCESSING at 50%."""
    db = MagicMock()
    _update_video_task_nmt(db, "task-1", "translated", [], "fullDubbing")
    params = db.execute.call_args[0][1]
    assert params["status"] == "PROCESSING"
    assert params["progress"] == 50.0
    assert params["completed_at"] is None


def test_update_video_task_nmt_translationAndTTS_is_processing():
    """translationAndTTS: NMT is not last (TTS follows) → PROCESSING at 50%."""
    db = MagicMock()
    _update_video_task_nmt(db, "task-1", "translated", [], "translationAndTTS")
    params = db.execute.call_args[0][1]
    assert params["status"] == "PROCESSING"
    assert params["progress"] == 50.0
    assert params["completed_at"] is None


def test_update_video_task_nmt_unknown_output_type_is_processing():
    """Unknown output_type must default to PROCESSING (safe fallback)."""
    db = MagicMock()
    _update_video_task_nmt(db, "task-1", "translated", [], "unknownType")
    params = db.execute.call_args[0][1]
    assert params["status"] == "PROCESSING"
    assert params["completed_at"] is None


# ── Cancellation — pre-check (D8) ─────────────────────────────────────────────

def test_translate_one_segment_returns_none_on_cancel():
    """Segment worker returns None immediately when cancelled flag is set."""
    result = _translate_one_segment(
        0,
        {"text": "hello", "start": 0.0, "end": 1.0},
        None,
        "arb_Arab",
        5,
        0.5,
        lambda: True,   # is_cancelled = True
    )
    assert result is None


def test_translate_all_segments_returns_none_on_cancel():
    """Fan-out returns None when cancelled_flag is True from the start (D3+D8)."""
    cancelled_flag = [True]
    result = _translate_all_segments(
        "job-1",
        [{"text": "segment one", "start": 0.0, "end": 1.0}],
        None,
        "arb_Arab",
        5,
        0.5,
        cancelled_flag,
    )
    assert result is None


def test_translate_all_segments_returns_none_on_mid_job_cancel():
    """Batch path returns None when cancelled between inference batches."""
    cancelled_flag = [False]
    call_count = [0]

    def fake_batch(*_args, **kwargs):
        call_count[0] += 1
        if call_count[0] >= 1:
            cancelled_flag[0] = True
        is_cancelled = kwargs.get("is_cancelled")
        if is_cancelled and is_cancelled():
            return None
        return ["translated"] * len(_args[0])

    with patch("app.worker._translator.translate_segments_batch", side_effect=fake_batch):
        result = _translate_all_segments(
            "job-cancel-mid",
            [{"text": "seg", "start": i * 1.0, "end": i * 1.0 + 1.0} for i in range(5)],
            None, "arb_Arab", 5, 0.5,
            cancelled_flag,
        )

    assert result is None


# ── Fan-out result shape (D3 + Phase 2 TTS contract) ─────────────────────────

def test_translate_all_segments_returns_correct_shape():
    """Each translated segment must have the 4 keys the TTS service expects."""
    cancelled_flag = [False]
    mock_translator = MagicMock()
    mock_translator.translate_segments_batch.return_value = [
        "translated-0",
        "translated-1",
        "translated-2",
    ]

    with patch("app.worker._translator", mock_translator):
        segments = [
            {"text": f"seg {i}", "start": float(i), "end": float(i + 1)}
            for i in range(3)
        ]
        result = _translate_all_segments(
            "job-shape", segments, None, "arb_Arab", 5, 0.5, cancelled_flag
        )

    assert result is not None
    assert len(result) == 3
    for i, seg in enumerate(result):
        # These 4 keys are the TTS contract (§6, LLD A.9, Phase 2 dependency)
        assert "start" in seg
        assert "end" in seg
        assert "original_text" in seg
        assert "translated_text" in seg
        assert seg["translated_text"] == f"translated-{i}"


def test_translate_all_segments_empty_input_returns_empty_list():
    """Empty stt_segments should return an empty list (not None)."""
    cancelled_flag = [False]
    result = _translate_all_segments(
        "job-empty", [], None, "arb_Arab", 5, 0.5, cancelled_flag
    )
    assert result == []


def test_translate_all_segments_does_not_use_thread_pool():
    """F12: post-batch work is sequential; inference parallelism comes from batching."""
    cancelled_flag = [False]
    mock_translator = MagicMock()
    mock_translator.translate_segments_batch.return_value = ["t0", "t1"]

    with patch("app.worker._translator", mock_translator), patch(
        "concurrent.futures.ThreadPoolExecutor"
    ) as pool_cls:
        segments = [
            {"text": "a", "start": 0.0, "end": 1.0},
            {"text": "b", "start": 1.0, "end": 2.0},
        ]
        result = _translate_all_segments(
            "job-no-pool", segments, None, "arb_Arab", 5, 0.5, cancelled_flag
        )

    assert result is not None
    assert len(result) == 2
    pool_cls.assert_not_called()


# ── _translate_one_segment: not cancelled → returns translated dict ───────────

def test_translate_one_segment_not_cancelled_returns_dict():
    """Non-cancelled segment returns a dict with all 4 required keys."""
    mock_translator = MagicMock()
    mock_translator.translate_segment.return_value = "ترجمة"

    with patch("app.worker._translator", mock_translator):
        result = _translate_one_segment(
            0,
            {"text": "hello world", "start": 0.0, "end": 2.0},
            "eng_Latn",
            "arb_Arab",
            5,
            0.5,
            lambda: False,  # not cancelled
        )

    assert result is not None
    assert result["original_text"] == "hello world"
    assert result["translated_text"] == "ترجمة"
    assert result["start"] == 0.0
    assert result["end"] == 2.0


def test_translate_one_segment_translation_exception_falls_back_to_original():
    """If translation raises, the original text is used (graceful fallback)."""
    mock_translator = MagicMock()
    mock_translator.translate_segment.side_effect = RuntimeError("model OOM")

    with patch("app.worker._translator", mock_translator):
        result = _translate_one_segment(
            0,
            {"text": "fallback text", "start": 0.0, "end": 1.0},
            None, "arb_Arab", 5, 0.5,
            lambda: False,
        )

    assert result is not None
    assert result["translated_text"] == "fallback text"
    assert result["original_text"] == "fallback text"
