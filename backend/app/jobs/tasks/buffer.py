"""Segment buffer for priority queue-based NMT→TTS processing.

The SegmentBuffer provides thread-safe ordering of out-of-order NMT translation
results, enabling progressive TTS synthesis while NMT is still translating
remaining segments.
"""
import heapq
import threading
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(order=True)
class _SegmentItem:
    """Internal heap item - order by start time."""
    start: float
    segment_id: int = field(compare=False)
    data: dict = field(compare=False)


class SegmentBuffer:
    """
    Thread-safe priority queue for ordering segments by start time.

    Usage:
        buffer = SegmentBuffer()

        # Push results as they arrive (out of order)
        buffer.push(segment_id=5, start=5.0, data={"text": "..."})
        buffer.push(segment_id=2, start=2.0, data={"text": "..."})
        buffer.push(segment_id=8, start=8.0, data={"text": "..."})

        # Pop in sequence order
        while (item := buffer.pop_next(expected_segment_id)) is not None:
            process(item.data)  # 2.0, then 5.0, then 8.0
    """

    def __init__(self):
        self._heap: list[_SegmentItem] = []
        self._lock = threading.Lock()
        self._next_expected = 0

    def push(self, segment_id: int, start: float, data: dict) -> None:
        """Push a segment to the buffer (thread-safe)."""
        item = _SegmentItem(start=start, segment_id=segment_id, data=data)
        with self._lock:
            heapq.heappush(self._heap, item)
            logger.debug(
                "[SegmentBuffer] Pushed segment_id=%d start=%.2f (heap_size=%d)",
                segment_id, start, len(self._heap)
            )

    def pop_next(self, expected_segment_id: int) -> Optional[dict]:
        """
        Pop the next segment if it matches the expected sequence order.

        Returns None if the next available segment doesn't match the expected
        sequence (gaps exist - waiting for earlier segments to arrive).
        """
        with self._lock:
            if not self._heap:
                return None

            # Peek at smallest item
            next_item = self._heap[0]

            if next_item.segment_id != expected_segment_id:
                logger.debug(
                    "[SegmentBuffer] Expected segment_id=%d, got %d (gap - waiting)",
                    expected_segment_id, next_item.segment_id
                )
                return None

            # Pop and return
            heapq.heappop(self._heap)
            self._next_expected = expected_segment_id + 1

            logger.debug(
                "[SegmentBuffer] Popped segment_id=%d start=%.2f (remaining=%d)",
                next_item.segment_id, next_item.start, len(self._heap)
            )
            return next_item.data

    def pop_all_ready(self, expected_segment_id: int) -> list[dict]:
        """Pop all segments ready up to (and including) expected_segment_id."""
        results = []
        while True:
            item = self.pop_next(expected_segment_id)
            if item is None:
                break
            results.append(item)
            expected_segment_id += 1
        return results

    @property
    def pending_count(self) -> int:
        """Number of segments currently in the buffer."""
        with self._lock:
            return len(self._heap)

    def clear(self) -> None:
        """Clear all buffered segments."""
        with self._lock:
            self._heap.clear()
            self._next_expected = 0