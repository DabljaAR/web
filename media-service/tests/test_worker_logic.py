"""Unit tests for merge worker logic (no DB, RabbitMQ, or ffmpeg)."""
from unittest.mock import MagicMock, patch

import pytest

from app.worker import on_message, process_merge_job


def test_process_merge_job_idempotency_skip():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={"id": "j1", "status": "COMPLETED", "output_data": {"dubbed_video_key": "k"}},
    ), patch("app.worker.is_completed", return_value=True):
        result = process_merge_job("j1")
    assert result == {"dubbed_video_key": "k"}


def test_process_merge_job_requires_combined_audio_key():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

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
        return_value={"id": "t1", "video_id": "v1", "combined_audio_key": None},
    ), patch("app.worker.mark_processing"):
        with pytest.raises(ValueError, match="combined_audio_key"):
            process_merge_job("j1")


def test_process_merge_job_video_mux_summary():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

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
        return_value={
            "id": "task-1",
            "video_id": "vid-1",
            "combined_audio_key": "tts/vid-1/combined_tts-job.wav",
        },
    ), patch("app.worker._load_video", return_value={
        "id": "vid-1",
        "file_path": "uploads/vid-1/original.mp4",
        "audio_path": None,
        "media_type": "video",
    }), patch("app.worker.mark_processing"), patch(
        "app.worker.mux_video_with_audio",
        return_value={
            "combined_audio_key": "tts/vid-1/combined_tts-job.wav",
            "dubbed_video_key": "dubbed/vid-1/dubbed_job-abc.mp4",
        },
    ), patch("app.worker._update_video_task_completed"), patch(
        "app.worker._update_video_dubbed"
    ), patch("app.worker.mark_completed"):
        summary = process_merge_job("job-abc")

    assert summary["combined_audio_key"] == "tts/vid-1/combined_tts-job.wav"
    assert summary["dubbed_video_key"] == "dubbed/vid-1/dubbed_job-abc.mp4"


def test_process_merge_job_audio_only_skips_mux():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={
            "id": "job-audio",
            "video_id": "vid-1",
            "input_data": {"task_id": "task-1"},
            "status": "QUEUED",
            "output_data": {},
        },
    ), patch("app.worker.is_completed", return_value=False), patch(
        "app.worker._load_video_task",
        return_value={
            "id": "task-1",
            "video_id": "vid-1",
            "combined_audio_key": "tts/vid-1/combined.wav",
        },
    ), patch("app.worker._load_video", return_value={
        "id": "vid-1",
        "file_path": None,
        "audio_path": "uploads/vid-1/audio.mp3",
        "media_type": "audio",
    }), patch("app.worker.mark_processing"), patch(
        "app.worker.mux_video_with_audio"
    ) as mux_mock, patch("app.worker._update_video_task_completed"), patch(
        "app.worker._update_video_dubbed"
    ), patch("app.worker.mark_completed"):
        summary = process_merge_job("job-audio")

    mux_mock.assert_not_called()
    assert summary["combined_audio_key"] == "tts/vid-1/combined.wav"
    assert summary["dubbed_video_key"] is None


def test_on_message_cancelled_ack_only():
    channel = MagicMock()
    method = MagicMock(delivery_tag=42)

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker.check_cancelled", return_value=True
    ), patch("app.worker.process_merge_job") as proc:
        on_message(channel, method, None, b'{"job_id": "j1"}')

    proc.assert_not_called()
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_on_message_publishes_completed_result():
    channel = MagicMock()
    channel.is_open = True
    channel.connection = MagicMock()
    method = MagicMock(delivery_tag=7)

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    summary = {"combined_audio_key": "k", "dubbed_video_key": "d.mp4"}

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker.check_cancelled", return_value=False
    ), patch("dablja_worker.ack.run_with_heartbeat", side_effect=lambda _c, fn: fn()), patch(
        "app.worker.process_merge_job", return_value=summary
    ), patch("dablja_worker.ack.publish_result_reliable") as pub:
        on_message(channel, method, None, b'{"job_id": "j1"}')

    pub.assert_called_once()
    assert pub.call_args.args[2] == "j1"
    assert pub.call_args.args[4] == "COMPLETED"
    assert pub.call_args.kwargs["output_data"] == summary
    channel.basic_ack.assert_called_once_with(delivery_tag=7)
