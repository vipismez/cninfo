from __future__ import annotations

import random
import threading
import time


class RateLimiter:
    def __init__(self, min_interval: float = 0.8, jitter: tuple[float, float] = (0.1, 0.6)) -> None:
        self.min_interval = min_interval
        self.jitter = jitter
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            target = self._last + self.min_interval + random.uniform(*self.jitter)
            if target > now:
                time.sleep(target - now)
            self._last = time.monotonic()
