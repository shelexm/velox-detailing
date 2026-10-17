"""In-process sliding-window rate limiter.

The API runs as a single process, so memory is a correct shared store. Running several API replicas would
need a shared store (for example Redis); see docs/security.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.core.errors import RateLimitedError


@dataclass
class RateLimiter:
    limit: int
    window_seconds: float
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
            for idle in [k for k, v in self._hits.items() if not v and k != key]:
                del self._hits[idle]
        return hits

    def is_blocked(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return len(self._prune(key, now)) >= self.limit

    def hit(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._prune(key, now).append(now)

    def check(self, key: str, now: float | None = None) -> None:
        """Count a request and refuse it once the limit is reached within the window."""
        if self.is_blocked(key, now):
            raise RateLimitedError()
        self.hit(key, now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


@dataclass
class Limiters:
    login_by_email: RateLimiter = field(default_factory=lambda: RateLimiter(5, 15 * 60))
    login_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(20, 15 * 60))
    booking_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(10, 10 * 60))
    public_read_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(240, 60))
