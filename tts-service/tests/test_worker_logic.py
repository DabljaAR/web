"""Unit tests for TTS worker logic (no DB, RabbitMQ, or model)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.worker import on_message, process_tts_job


def _make_channel():
    ch = MagicMock()
    ch.basic_ack = MagicMock()
    ch.basic_nack = MagicMock()
    ch.is_open = True
    ch.connection = MagicMock()
    return ch


def _make_method(delivery_tag=1):
    m = MagicMock()
    m.delivery_tag = delivery_tag
    return m


def _job_context(task_id="task-1"):
    return {
        "id": "job-abc",
        "video_id": "vid-1",
        "input_data": {"task_id": task_id},
        "status": "QUEUED",
        "output_data": {},
    }


def test_process_tts_job_idempotency_skip():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    cached = {"status": "completed", "combined_audio_key": "tts/vid-1/combined_j1.wav", "video_id": "v1"}

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value={"id": "j1", "status": "COMPLETED", "output_data": cached},
    ), patch("app.worker.OmniVoiceManager.synthesize") as mock_synth:
        result = process_tts_job("j1", [False])

    assert result == cached
    mock_synth.assert_not_called()


def test_process_tts_job_cancel_before_processing():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value=_job_context(),
    ), patch("app.worker._load_video_task_segments", return_value=[{"translated_text": "hi"}]), patch(
        "app.worker._is_cancelled", return_value=True
    ), patch("app.worker.mark_processing") as mock_processing, patch(
        "app.worker.mark_completed"
    ) as mock_completed, patch("app.worker.OmniVoiceManager.synthesize") as mock_synth:
        result = process_tts_job("j1", [False])

    assert result["status"] == "cancelled"
    mock_processing.assert_not_called()
    mock_synth.assert_not_called()
    mock_completed.assert_called_once()


def test_process_tts_job_empty_segments_raises():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value=_job_context(),
    ), patch("app.worker._load_video_task_segments", return_value=[]), patch(
        "app.worker._is_cancelled", return_value=False
    ):
        with pytest.raises(ValueError, match="no segments to synthesize"):
            process_tts_job("job-abc", [False])


def test_process_tts_job_all_segments_failed_raises():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    segments = [{"translated_text": "hello", "start": 0.0, "end": 1.0}]

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value=_job_context(),
    ), patch("app.worker._load_video_task_segments", return_value=segments), patch(
        "app.worker._is_cancelled", return_value=False
    ), patch("app.worker.mark_processing"), patch(
        "app.worker.OmniVoiceManager.synthesize", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(ValueError, match="all segment syntheses failed"):
            process_tts_job("job-abc", [False])


def test_process_tts_job_synthesizes_and_writes_combined_audio_key():
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    segments = [{"translated_text": "hello", "start": 0.0, "end": 1.0}]
    combined_path = MagicMock(spec=Path)
    combined_path.read_bytes.return_value = b"combined-wav"

    with patch("app.worker._SessionLocal", return_value=mock_db), patch(
        "app.worker._load_job",
        return_value=_job_context(task_id="task-99"),
    ), patch("app.worker._load_video_task_segments", return_value=segments), patch(
        "app.worker._is_cancelled", return_value=False
    ), patch("app.worker.mark_processing"), patch(
        "app.worker.mark_completed"
    ) as mock_completed, patch(
        "app.worker._update_video_task_combined_audio"
    ) as mock_update_task, patch(
        "app.worker.OmniVoiceManager.synthesize", return_value=[b"\x00" * 100]
    ), patch("app.worker.upload_audio", return_value="https://example/audio.wav") as mock_upload, patch(
        "app.worker.sf.write"
    ), patch(
        "app.worker.combine_segment_wavs", return_value=combined_path
    ) as mock_combine:
        summary = process_tts_job("job-abc", [False])

    assert summary["combined_audio_key"] == "tts/vid-1/combined_job-abc.wav"
    assert summary["segment_count"] == 1
    mock_combine.assert_called_once()
    mock_upload.assert_called()
    mock_update_task.assert_called_once_with(mock_db, "task-99", "tts/vid-1/combined_job-abc.wav")
    mock_completed.assert_called_once()


def test_on_message_completed_job_republishes_result_only():
    ch = _make_channel()
    method = _make_method(7)
    body = json.dumps({"job_id": "job-redeliver"}).encode()
    summary = {"status": "completed", "video_id": "v1", "combined_audio_key": "k"}

    with patch("app.worker._SessionLocal"), patch(
        "app.worker._is_cancelled", return_value=False
    ), patch("dablja_worker.ack.is_completed", return_value=True), patch(
        "dablja_worker.ack._load_completed_output", return_value=summary
    ), patch("app.worker.process_tts_job") as mock_process, patch(
        "dablja_worker.ack.publish_result_reliable"
    ) as mock_publish:
        on_message(ch, method, None, body)

    mock_process.assert_not_called()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    assert mock_publish.call_args.kwargs["output_data"] == summary
    ch.basic_ack.assert_called_once_with(delivery_tag=7)


def test_on_message_failed_job_publishes_failed_and_acks():
    ch = _make_channel()
    method = _make_method(1)
    body = json.dumps({"job_id": "job-fail"}).encode()

    with patch("app.worker._SessionLocal"), patch(
        "app.worker._is_cancelled", return_value=False
    ), patch("dablja_worker.ack.is_completed", return_value=False), patch(
        "dablja_worker.ack.run_with_heartbeat", side_effect=lambda _c, fn: fn()
    ), patch(
        "app.worker.process_tts_job", side_effect=RuntimeError("synthesis crash")
    ), patch("app.worker._handle_failure") as mock_fail_db, patch(
        "dablja_worker.ack.publish_result_reliable"
    ) as mock_publish:
        on_message(ch, method, None, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_nack.assert_not_called()
    mock_fail_db.assert_called_once()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "FAILED"
    assert "synthesis crash" in mock_publish.call_args.kwargs["error"]
