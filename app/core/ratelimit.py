"""In-process sliding-window rate limiter.

The API runs as a single process, so memory is a correct shared store. Running several API replicas would
need a shared store (for example Redis); see docs/security.md.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from app.core.errors import RateLimitedError


@dataclass
class RateLimiter:
    limit: int
    window_seconds: float
    _hits: dict[str, deque[float]] = field(default_factory=dict)
    _last_sweep: float = 0.0
    max_keys: int = 10_000

    def _recent(self, key: str, now: float) -> deque[float] | None:
        """The live hits of a key; an expired key is dropped. Reading never creates a key."""
        hits = self._hits.get(key)
        if hits is None:
            return None
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return None
        return hits

    def _sweep(self, now: float) -> None:
        """Forget every idle key, at most once per window, so a stream of unique keys cannot grow memory."""
        if len(self._hits) <= self.max_keys or now - self._last_sweep < self.window_seconds / 4:
            return
        self._last_sweep = now
        for key in list(self._hits):
            self._recent(key, now)

    def is_blocked(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._recent(key, now)
        return hits is not None and len(hits) >= self.limit

    def hit(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._sweep(now)
        hits = self._recent(key, now)
        if hits is None:
            hits = self._hits[key] = deque()
        hits.append(now)

    def check(self, key: str, now: float | None = None) -> None:
        """Count a request and refuse it once the limit is reached within the window."""
        if self.is_blocked(key, now):
            raise RateLimitedError()
        self.hit(key, now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


@dataclass
class Limiters:
    # Locking an account by e-mail alone lets anyone lock the owner out: the tight limit is per e-mail and
    # address together, the account-wide one is higher and only stops attacks spread over many addresses.
    login_by_email_and_ip: RateLimiter = field(default_factory=lambda: RateLimiter(5, 15 * 60))
    login_by_email: RateLimiter = field(default_factory=lambda: RateLimiter(40, 15 * 60))
    login_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(20, 15 * 60))
    booking_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(10, 10 * 60))
    public_read_by_ip: RateLimiter = field(default_factory=lambda: RateLimiter(240, 60))
