from collections import deque
from typing import List

from core.logging import LogRecord


class RingBuffer:
    """
    Lock-free ring buffer for log messages.

    Optimized for single producer (logging calls) and single consumer (dispatch task).
    """

    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self._buffer = deque(maxlen=maxsize)
        self._dropped_count = 0

    def put_nowait(self, item: LogRecord) -> bool:
        """
        Add item to buffer without blocking.

        Returns True if added, False if buffer full (item dropped).
        """
        try:
            if len(self._buffer) >= self.maxsize:
                self._dropped_count += 1
                return False

            self._buffer.append(item)
            return True
        except Exception:
            # Should never happen, but handle gracefully
            self._dropped_count += 1
            return False

    def get_batch(self, batch_size: int = 100) -> List[LogRecord]:
        """Get batch of items from buffer."""
        batch = []
        for _ in range(min(batch_size, len(self._buffer))):
            if self._buffer:
                batch.append(self._buffer.popleft())
        return batch

    def size(self) -> int:
        """Current buffer size."""
        return len(self._buffer)

    def dropped_count(self) -> int:
        """Number of dropped messages (buffer full)."""
        return self._dropped_count
