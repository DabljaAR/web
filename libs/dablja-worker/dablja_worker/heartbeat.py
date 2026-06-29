"""Keep AMQP connections alive during long-running blocking consumer work."""
from __future__ import annotations

import logging
import threading
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_with_heartbeat(
    connection,
    fn: Callable[[], T],
    poll_interval_s: float = 1.0,
) -> T:
    """Run *fn* in a worker thread while servicing AMQP heartbeats on *connection*.

    Blocking pika consumers cannot send heartbeats while the user callback runs.
    Long jobs (multi-hour TTS) otherwise lose the RabbitMQ connection.
    """
    result: list[T] = []
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            result.append(fn())
        except BaseException as exc:  # noqa: BLE001 — propagate job failures unchanged
            error.append(exc)

    thread = threading.Thread(target=_worker, name="job-worker", daemon=True)
    thread.start()

    while thread.is_alive():
        try:
            connection.process_data_events(time_limit=poll_interval_s)
        except Exception as exc:
            logger.debug("process_data_events while job running: %s", exc)
        thread.join(timeout=poll_interval_s)

    thread.join()

    if error:
        raise error[0]
    return result[0]
