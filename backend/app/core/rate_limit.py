"""Rate limiting.

Default backend is an in-process counter (memory).  When
``RATE_LIMIT_BACKEND=redis`` a shared Redis counter is used so limits hold
across multiple API workers.  Both paths are atomic per key.

Rate-limit decisions are returned via ``Retry-After`` and the standard
``429`` envelope so the frontend can react.
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.errors import RateLimitedError


@dataclass(frozen=True)
class Limit:
    """A sliding-window limit definition."""

    key: str
    per: int
    unit: str  # "second" | "minute" | "hour" | "day"

    @property
    def ttl_seconds(self) -> int:
        return {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }[self.unit]

    def __str__(self) -> str:
        return f"{self.per}/{self.unit}"


class MemoryRateLimiter:
    """Process-local counter used when Redis is unavailable."""

    def __init__(self) -> None:
        self._counts: dict[str, list[float]] = {}
        self._lock = functools.partial(time.sleep, 0)
        self._mutex = __import__("threading").Lock()

    def hit(self, key: str, limit: Limit) -> bool:
        now = time.monotonic()
        window = limit.ttl_seconds
        with self._mutex:
            stamps = [s for s in self._counts.get(key, []) if now - s < window]
            stamps.append(now)
            self._counts[key] = stamps
            return len(stamps) <= limit.per


class RateLimiter:
    """Unified limiter decoupling 'where the counter lives' from callers."""

    def __init__(self) -> None:
        self._memory = MemoryRateLimiter()
        self._cache: Any = None
        if settings.rate_limit_backend == "redis":
            from app.core.redis import get_cache

            self._cache = get_cache()

    def key_for(self, scope: str, identity: str) -> str:
        return f"rl:{scope}:{identity}"

    async def check(self, scope: str, identity: str, limit: Limit) -> None:
        """Raise :class:`RateLimitedError` when the limit is exceeded."""
        if not settings.rate_limit_enabled:
            return
        key = self.key_for(scope, identity)
        if self._cache is not None:
            used = await self._cache.incr(key, ttl=limit.ttl_seconds)
            allowed = used <= limit.per
        else:
            allowed = self._memory.hit(key, limit)
        if not allowed:
            raise RateLimitedError(code="RATE_LIMITED", message="Too many requests, slow down.")


@functools.lru_cache(maxsize=1)
def get_limiter() -> RateLimiter:
    return RateLimiter()


def default_identity(request: Any) -> str:
    """Rate-limit identity: authenticated user id, else client IP."""
    user = getattr(request.state, "user_id", None)
    if user:
        return f"user:{user}"
    client = getattr(request.state, "client_ip", None) or (
        request.client.host if request.client else "unknown"
    )
    return f"ip:{client}"


__all__ = ["Limit", "MemoryRateLimiter", "RateLimiter", "default_identity", "get_limiter"]
