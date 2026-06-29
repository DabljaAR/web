"""Unit tests for stt-service worker.py.

Tests all consumer-layer invariants without any real infrastructure.
Design doc references verified:
  §10.3 — idempotency (COMPLETED skip)
  D8    — cooperative cancellation
  §10.2 — transient nack vs permanent ack+FAILED
  §15   — WorkerResultPayload contract (Claim Check)
"""
import json
from unittest.mock import MagicMock, patch, call

import pytest


# ── Helpers to build a fake pika message ──────────────────────────────────────

def _make_channel():
    ch = MagicMock()
    ch.basic_ack = MagicMock()
    ch.basic_nack = MagicMock()
    ch.basic_publish = MagicMock()
    return ch


def _make_method(delivery_tag=1):
    m = MagicMock()
    m.delivery_tag = delivery_tag
    return m


def _body(job_id="test-job-1"):
    return json.dumps({"job_id": job_id}).encode()


# ── Bad message handling ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_on_message_bad_json_acks_and_discards():
    """Malformed JSON must be acked and discarded (routes to DLQ via DLX)."""
    from app.worker import on_message

    ch = _make_channel()
    on_message(ch, _make_method(), None, b"not-json")

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_nack.assert_not_called()
    ch.basic_publish.assert_not_called()


@pytest.mark.unit
def test_on_message_missing_job_id_acks_and_discards():
    """Message with no job_id must be acked and discarded."""
    from app.worker import on_message

    ch = _make_channel()
    on_message(ch, _make_method(), None, json.dumps({"other": "field"}).encode())

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_publish.assert_not_called()


# ── Cancellation (D8) ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_on_message_cancelled_job_acks_without_processing():
    """A CANCELLED job must be acked without calling process_stt_job."""
    from app.worker import on_message

    ch = _make_channel()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.worker._SessionLocal", return_value=mock_session),
        patch("app.worker._is_cancelled", return_value=True) as mock_cancel,
        patch("app.worker.process_stt_job") as mock_process,
    ):
        on_message(ch, _make_method(), None, _body("job-cancelled"))

    mock_cancel.assert_called_once()
    mock_process.assert_not_called()
    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_publish.assert_not_called()


@pytest.mark.unit
def test_on_message_transient_db_error_on_cancel_check_nacks_with_requeue():
    """Transient DB error during cancel check must nack with requeue=True."""
    from app.worker import on_message
    from sqlalchemy.exc import OperationalError

    ch = _make_channel()

    with patch("app.worker._SessionLocal") as mock_sl:
        mock_sl.return_value.__enter__ = MagicMock(
            side_effect=OperationalError("stmt", {}, Exception("connection lost"))
        )
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)

        on_message(ch, _make_method(), None, _body("job-transient"))

    ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)
    ch.basic_ack.assert_not_called()


@pytest.mark.unit
def test_on_message_permanent_db_error_on_cancel_check_acks():
    """Non-transient DB error during cancel check must ack (not loop forever)."""
    from app.worker import on_message

    ch = _make_channel()

    with patch("app.worker._SessionLocal") as mock_sl:
        # ValueError is a permanent error (not in transient list)
        mock_sl.return_value.__enter__ = MagicMock(
            side_effect=ValueError("bad column")
        )
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)

        on_message(ch, _make_method(), None, _body("job-perm"))

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_nack.assert_not_called()


# ── Idempotency (§10.3) ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_process_stt_job_returns_early_when_already_completed():
    """If job status is COMPLETED on load, return cached output_data immediately."""
    from app.worker import process_stt_job

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    cached_output = {"segment_count": 5, "language": "en", "duration": 60.0}

    with (
        patch("app.worker._make_db", return_value=(MagicMock(), MagicMock(return_value=mock_session))),
        patch("app.worker._load_job", return_value={
            "id": "job-1", "video_id": "vid-1",
            "input_data": {}, "status": "COMPLETED",
            "output_data": cached_output,
        }),
        patch("app.worker.download_file") as mock_dl,
    ):
        result = process_stt_job("job-1")

    assert result == cached_output
    mock_dl.assert_not_called()


# ── Successful processing ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_on_message_successful_job_publishes_completed_and_acks():
    """Happy path: process → COMPLETED result → ack."""
    from app.worker import on_message

    ch = _make_channel()
    ch.connection = MagicMock()
    summary = {"segment_count": 3, "language": "en", "duration": 10.0}

    with (
        patch("app.worker._SessionLocal") as mock_sl,
        patch("app.worker._is_cancelled", return_value=False),
        patch("dablja_worker.ack.run_with_heartbeat", side_effect=lambda _c, fn: fn()),
        patch("app.worker.process_stt_job", return_value=summary),
        patch("dablja_worker.ack.publish_result_reliable") as mock_publish,
    ):
        on_message(ch, _make_method(), None, _body("job-ok"))

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_nack.assert_not_called()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    assert mock_publish.call_args.kwargs["output_data"] == summary


@pytest.mark.unit
def test_on_message_redelivery_republishes_completed_without_rerun():
    """When job is already COMPLETED, on_message must republish and ack without processing."""
    from app.worker import on_message

    ch = _make_channel()
    ch.is_open = True
    ch.connection = MagicMock()
    cached = {"segment_count": 5, "language": "en", "duration": 20.0}

    with (
        patch("app.worker._SessionLocal"),
        patch("app.worker._is_cancelled", return_value=False),
        patch("dablja_worker.ack.is_completed", return_value=True),
        patch("dablja_worker.ack._load_completed_output", return_value=cached),
        patch("app.worker.process_stt_job") as mock_process,
        patch("dablja_worker.ack.publish_result_reliable") as mock_publish,
    ):
        on_message(ch, _make_method(), None, _body("job-redeliver"))

    mock_process.assert_not_called()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    assert mock_publish.call_args.kwargs["output_data"] == cached
    ch.basic_ack.assert_called_once_with(delivery_tag=1)


# ── Failure handling ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_on_message_failed_job_publishes_failed_and_acks():
    """On exception: mark_failed + publish FAILED result + ack (no nack)."""
    from app.worker import on_message

    ch = _make_channel()
    ch.connection = MagicMock()

    with (
        patch("app.worker._SessionLocal"),
        patch("app.worker._is_cancelled", return_value=False),
        patch("dablja_worker.ack.run_with_heartbeat", side_effect=lambda _c, fn: fn()),
        patch("app.worker.process_stt_job", side_effect=RuntimeError("whisper crash")),
        patch("app.worker._handle_failure") as mock_fail_db,
        patch("dablja_worker.ack.publish_result_reliable") as mock_publish,
    ):
        on_message(ch, _make_method(), None, _body("job-fail"))

    ch.basic_ack.assert_called_once_with(delivery_tag=1)
    ch.basic_nack.assert_not_called()
    mock_fail_db.assert_called_once()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "FAILED"
    assert "whisper crash" in mock_publish.call_args.kwargs["error"]


# ── Result payload shape (§15 / Claim Check) ─────────────────────────────────

@pytest.mark.unit
def test_publish_result_completed_shape():
    """publish_result COMPLETED must emit all required WorkerResultPayload fields."""
    from dablja_worker import publish_result

    ch = _make_channel()
    summary = {"segment_count": 10, "language": "en", "duration": 30.5}

    publish_result(ch, "job.results.stt", "job-1", "STT_TRANSCRIBE", "COMPLETED", output_data=summary)

    ch.basic_publish.assert_called_once()
    body = json.loads(ch.basic_publish.call_args.kwargs["body"])
    assert body["job_id"] == "job-1"
    assert body["job_type"] == "STT_TRANSCRIBE"
    assert body["status"] == "COMPLETED"
    assert body["output_data"] == summary
    assert "error" not in body


@pytest.mark.unit
def test_publish_result_failed_shape():
    """publish_result FAILED must include 'error' key."""
    from dablja_worker import publish_result

    ch = _make_channel()
    publish_result(ch, "job.results.stt", "job-2", "STT_TRANSCRIBE", "FAILED", error="model not loaded")

    body = json.loads(ch.basic_publish.call_args.kwargs["body"])
    assert body["status"] == "FAILED"
    assert body["error"] == "model not loaded"
    assert body["output_data"] == {}


@pytest.mark.unit
def test_publish_result_uses_correct_routing_key():
    """Result must be published to job.results.stt."""
    from dablja_worker import publish_result

    ch = _make_channel()
    routing_key = "job.results.stt"
    publish_result(ch, routing_key, "job-3", "STT_TRANSCRIBE", "COMPLETED")

    assert ch.basic_publish.call_args.kwargs["routing_key"] == routing_key


@pytest.mark.unit
def test_publish_result_is_persistent():
    """Messages must be persistent (delivery_mode=2)."""
    from dablja_worker import publish_result
    import pika

    ch = _make_channel()
    publish_result(ch, "job.results.stt", "job-4", "STT_TRANSCRIBE", "COMPLETED")

    props = ch.basic_publish.call_args.kwargs["properties"]
    assert props.delivery_mode == 2
