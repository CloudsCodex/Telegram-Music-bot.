# Developer by : Mr_Manas_Op
"""Small in-memory sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import deque

ALLOWED = 0
FIRST_BLOCK = 1   # blocked now; the caller may send one "slow down" notice
BLOCKED = 2       # blocked; stay silent


class RateLimiter:
    def __init__(self, count: int, window: int) -> None:
        self._count = count
        self._window = window
        self._hits: dict[int, deque[float]] = {}
        self._warned: dict[int, float] = {}

    def check(self, key: int) -> int:
        now = time.monotonic()
        if len(self._hits) > 5000:
            self._purge(now)

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self._window:
            hits.popleft()

        if len(hits) >= self._count:
            if now - self._warned.get(key, 0.0) > self._window:
                self._warned[key] = now
                return FIRST_BLOCK
            return BLOCKED

        hits.append(now)
        return ALLOWED

    def _purge(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self._window]:
            self._hits.pop(key, None)
            self._warned.pop(key, None)
