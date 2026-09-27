"""In-memory per-key sliding-window rate limiter (single process; resets on restart)."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: float = 3600.0) -> None:
        self.window = float(window_seconds)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self, key: str, limit: int, now: Optional[float] = None
    ) -> Tuple[bool, int]:
        """Record a hit if allowed. Returns (allowed, retry_after_seconds)."""
        if limit <= 0:
            return True, 0
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - now))
                return False, retry_after
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
