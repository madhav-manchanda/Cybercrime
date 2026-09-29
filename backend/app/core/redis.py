"""Redis client wrapper.

Redis is used for:
- response caching (dashboard stats, ATM risk, hotspots, model metadata)
- rate-limit counters
- distributed lock (Celery)
- realtime fan-out channel (optional)

The wrapper degrades gracefully: when Redis is unreachable every call returns a
sentinel value and logs once, so the API never crashes because the cache is
down.
"""

from __future__ import annotations

import functools
import logging
import threading
from time import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]
    RedisError = Exception  # type: ignore[assignment,misc]


_MISS = object()
_redis_available: bool | None = None
_availability_lock = threading.Lock()


class CacheBackend:
    """Thin async cache with an in-process fallback store.

    When Redis is unavailable the backend transparently uses a process-local
    dict so behaviour (including TTL) stays deterministic during development
    and tests.
    """

    def __init__(self) -> None:
        self._local: dict[str, tuple[float, Any]] = {}
        self._redis: Any = None
        if aioredis is not None:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )

    # ------------------------------------------------------------ helpers
    @property
    def enabled(self) -> bool:
        return settings.cache_enabled

    async def _healthy(self) -> bool:
        global _redis_available
        if not self._redis:
            return False
        with _availability_lock:
            if _redis_available is not None:
                return _redis_available
            try:
                await self._redis.ping()
                _redis_available = True
            except Exception:
                _redis_available = False
                logger.warning("Redis unreachable - using degraded in-memory cache.")
            return _redis_available

    # --------------------------------------------------------------- API
    async def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        try:
            if await self._healthy():
                return await self._redis.get(self._key(key))
            item = self._local.get(self._key(key))
            if not item:
                return None
            expires, value = item
            if expires < time():
                self._local.pop(self._key(key), None)
                return None
            return value
        except Exception:
            return None

    async def setex(self, key: str, ttl: int, value: Any) -> None:
        if not self.enabled:
            return
        try:
            if await self._healthy() and isinstance(value, str):
                await self._redis.setex(self._key(key), ttl, value)
                return
            self._local[self._key(key)] = (time() + ttl, value)
        except Exception:
            self._local[self._key(key)] = (time() + ttl, value)

    async def delete(self, key: str) -> None:
        try:
            if await self._healthy():
                await self._redis.delete(self._key(key))
            self._local.pop(self._key(key), None)
        except Exception:
            self._local.pop(self._key(key), None)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete keys matching an ``*``-containing pattern."""
        try:
            if await self._healthy():
                async for key in self._redis.scan_iter(match=self._key(pattern)):
                    await self._redis.delete(key)
            full = self._key(pattern)
            prefix = full.split("*", 1)[0]
            for local_key in list(self._local):
                if local_key.startswith(prefix):
                    self._local.pop(local_key, None)
        except Exception:
            pass

    async def incr(self, key: str, ttl: int = 60) -> int:
        """Atomic increment with TTL (rate limiting)."""
        full = self._key(key)
        try:
            if await self._healthy():
                value = await self._redis.incr(full)
                if value == 1:
                    await self._redis.expire(full, ttl)
                return int(value)
        except Exception:
            pass
        now = time()
        item = self._local.get(full)
        if not item or item[0] < now:
            self._local[full] = (now + ttl, 0)
            item = self._local[full]
        count = int(item[1]) + 1
        self._local[full] = (item[0], count)
        return count

    @staticmethod
    def _key(key: str) -> str:
        return f"{settings.app_slug}:{key}"


@functools.lru_cache(maxsize=1)
def get_cache() -> CacheBackend:
    return CacheBackend()


cache = get_cache()

__all__ = ["CacheBackend", "cache", "get_cache"]
