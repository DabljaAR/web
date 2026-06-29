"""Unit tests for TTS worker logic (no DB, RabbitMQ, or model)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.worker import _update_video_task_tts, process_tts_job


def test_update_video_task_tts_translationAndTTS_terminal():
    db = MagicMock()
    _update_video_task_tts(db, "task-1", [], "combined.wav", "translationAndTTS")
    params = db.execute.call_args[0][1]
    assert params["status"] == "COMPLETED"
    assert params["progress"] == 100.0
    assert params["combined_key"] == "combined.wav"
    assert params["terminal"] is True


def test_update_video_task_tts_fullDubbing_processing():
    db = MagicMock()
    _update_video_task_tts(db, "task-1", [], "combined.wav", "fullDubbing")
    params = db.execute.call_args[0][1]
    assert params["status"] == "PROCESSING"
    assert params["progress"] == 75.0
    assert params["terminal"] is False


def test_process_tts_job_idempotency_skip():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={"id": "j1", "status": "COMPLETED", "output_data": {"combined_audio_key": "k"}},
    ), patch("app.worker.is_completed", return_value=True):
        result = process_tts_job("j1", [False])
    assert result == {"combined_audio_key": "k"}


def test_process_tts_job_cancel_mid_loop():
    cancelled_flag = [False]

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    segments = [
        {"translated_text": "hello", "start": 0.0, "end": 1.0},
        {"translated_text": "world", "start": 1.0, "end": 2.0},
    ]

    call_count = [0]

    def fake_synthesize(**_kwargs):
        call_count[0] += 1
        if call_count[0] >= 1:
            cancelled_flag[0] = True
        return b"wav"

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={
            "id": "j1",
            "video_id": "v1",
            "input_data": {"task_id": "t1"},
            "status": "QUEUED",
            "output_data": {},
        },
    ), patch("app.worker.is_completed", return_value=False), patch(
        "app.worker._load_video_task",
        return_value={"segments": segments, "output_type": "translationAndTTS"},
    ), patch("app.worker.mark_processing"), patch(
        "app.worker._tts.synthesize", side_effect=fake_synthesize
    ), patch("app.worker.upload_wav"):
        with pytest.raises(RuntimeError, match="cancelled"):
            process_tts_job("j1", cancelled_flag)


def test_process_tts_job_summary_includes_combined_key():
    cancelled_flag = [False]
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    segments = [{"translated_text": "مرحبا", "start": 0.0, "end": 1.0}]

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={
            "id": "job-abc",
            "video_id": "vid-1",
            "input_data": {"task_id": "task-1"},
            "status": "QUEUED",
            "output_data": {},
        },
    ), patch("app.worker.is_completed", return_value=False), patch(
        "app.worker._load_video_task",
        return_value={"segments": segments, "output_type": "translationAndTTS"},
    ), patch("app.worker.mark_processing"), patch(
        "app.worker._tts.synthesize", return_value=b"fake-wav"
    ), patch("app.worker.upload_wav"), patch(
        "app.worker.combine_segment_wavs", return_value=b"combined-wav"
    ), patch("app.worker._update_video_task_tts"), patch(
        "app.worker.mark_completed"
    ):
        summary = process_tts_job("job-abc", cancelled_flag)

    assert summary["combined_audio_key"] == "tts/vid-1/combined_job-abc.wav"
    assert summary["segment_count"] == 1
    assert summary["tts_segments"] == 1


def test_on_message_completed_job_republishes_result_only():
    from app.worker import on_message

    ch = MagicMock()
    ch.is_open = True
    ch.connection = MagicMock()
    method = MagicMock()
    method.delivery_tag = 7
    body = json.dumps({"job_id": "job-redeliver"}).encode()

    summary = {"combined_audio_key": "tts/v1/combined.wav", "segment_count": 5}

    with patch("app.worker._SessionLocal") as mock_sl, patch(
        "app.worker.check_cancelled", return_value=False
    ), patch("dablja_worker.ack.run_with_heartbeat", side_effect=lambda _c, fn: fn()), patch(
        "app.worker.process_tts_job", return_value=summary
    ), patch("dablja_worker.ack.publish_result_reliable") as mock_publish, patch(
        "app.worker._watch_cancel"
    ):
        on_message(ch, method, None, body)

    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    assert mock_publish.call_args.kwargs["output_data"] == summary
    ch.basic_ack.assert_called_once_with(delivery_tag=7)
