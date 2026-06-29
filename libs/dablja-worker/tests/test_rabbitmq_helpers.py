"""Unit tests for dablja-worker RabbitMQ helpers."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LIBS = Path(__file__).resolve().parents[1]
if str(_LIBS) not in sys.path:
    sys.path.insert(0, str(_LIBS))


def test_run_with_heartbeat_services_connection_while_job_runs():
    import threading
    import time

    from dablja_worker.heartbeat import run_with_heartbeat

    connection = MagicMock()
    connection.process_data_events = MagicMock()
    started = threading.Event()

    def slow_job():
        started.set()
        time.sleep(0.05)
        return "done"

    result = run_with_heartbeat(connection, slow_job, poll_interval_s=0.01)

    assert result == "done"
    started.wait(timeout=1)
    assert connection.process_data_events.called


def test_run_with_heartbeat_propagates_job_errors():
    from dablja_worker.heartbeat import run_with_heartbeat

    connection = MagicMock()
    connection.process_data_events = MagicMock()

    with pytest.raises(ValueError, match="boom"):
        run_with_heartbeat(connection, lambda: (_ for _ in ()).throw(ValueError("boom")))


@patch("dablja_worker.results.pika.BlockingConnection")
def test_publish_result_reliable_retries_on_connection_loss(mock_connect):
    from pika.exceptions import AMQPConnectionError

    from dablja_worker.results import publish_result_reliable

    failing = MagicMock()
    failing.channel.side_effect = AMQPConnectionError("down")
    mock_connect.side_effect = [failing, failing, MagicMock()]

    with patch("dablja_worker.results.publish_result") as mock_publish, patch(
        "dablja_worker.results.time.sleep"
    ):
        publish_result_reliable(
            "amqp://guest:guest@localhost/",
            "job.results.tts",
            "job-1",
            "TTS_SYNTHESIZE",
            "COMPLETED",
            output_data={"ok": True},
            max_attempts=3,
        )

    assert mock_connect.call_count == 3
    mock_publish.assert_called_once()


@patch("dablja_worker.ack.publish_result_reliable")
@patch("dablja_worker.ack.run_with_heartbeat")
def test_finish_job_message_preflight_idempotency_skips_process_fn(
    mock_run, mock_publish
):
    from dablja_worker.ack import finish_job_message

    channel = MagicMock()
    channel.is_open = True
    channel.connection = MagicMock()

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("dablja_worker.ack.is_completed", return_value=True), patch(
        "dablja_worker.ack._load_completed_output", return_value={"segment_count": 3}
    ):
        finish_job_message(
            channel=channel,
            delivery_tag=1,
            rabbitmq_url="amqp://guest:guest@localhost/",
            result_routing_key="job.results.stt",
            job_id="job-1",
            job_type="STT_TRANSCRIBE",
            session_factory=lambda: session,
            process_fn=lambda: (_ for _ in ()).throw(AssertionError("must not run")),
            service_name="STT",
        )

    mock_run.assert_not_called()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    channel.basic_ack.assert_called_once_with(delivery_tag=1)


@patch("dablja_worker.ack.publish_result_reliable")
@patch("dablja_worker.ack.run_with_heartbeat")
def test_finish_job_message_does_not_mark_failed_when_already_completed(
    mock_run, mock_publish
):
    from dablja_worker.ack import finish_job_message

    mock_run.side_effect = RuntimeError("publish blew up")

    channel = MagicMock()
    channel.is_open = True
    channel.connection = MagicMock()

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("dablja_worker.ack.is_completed", return_value=True), patch(
        "dablja_worker.ack._load_completed_output", return_value={"segment_count": 5}
    ), patch("dablja_worker.ack.mark_failed") as mock_mark_failed:
        finish_job_message(
            channel=channel,
            delivery_tag=1,
            rabbitmq_url="amqp://guest:guest@localhost/",
            result_routing_key="job.results.tts",
            job_id="job-1",
            job_type="TTS_SYNTHESIZE",
            session_factory=lambda: session,
            process_fn=lambda: {"ignored": True},
            service_name="TTS",
        )

    mock_mark_failed.assert_not_called()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[4] == "COMPLETED"
    channel.basic_ack.assert_called_once_with(delivery_tag=1)
