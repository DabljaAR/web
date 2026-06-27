"""Unit tests for nmt-service worker logic (no DB, RabbitMQ, or model)."""
from unittest.mock import MagicMock

from app.worker import (
    _translate_all_segments,
    _translate_one_segment,
    _update_video_task_nmt,
)


def test_update_video_task_nmt_captionsAndTranslation_is_terminal():
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
    db = MagicMock()
    _update_video_task_nmt(db, "task-1", "translated", [], "fullDubbing")
    params = db.execute.call_args[0][1]
    assert params["status"] == "PROCESSING"
    assert params["progress"] == 50.0
    assert params["completed_at"] is None


def test_translate_one_segment_returns_none_on_cancel():
    result = _translate_one_segment(
        0,
        {"text": "hello", "start": 0.0, "end": 1.0},
        None,
        "arb_Arab",
        5,
        0.5,
        lambda: True,
    )
    assert result is None


def test_translate_all_segments_returns_none_on_cancel():
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
