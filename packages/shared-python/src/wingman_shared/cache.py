"""In-memory cache with stale-while-revalidate and webhook invalidation.

Strategy:
- Fresh hit (age < TTL): return immediately
- Stale hit (age >= TTL): return immediately + trigger background refresh
- Miss: fetch synchronously, cache, return

Invalidation:
- Webhook-driven: instant invalidation when GitLab pushes events
- Write-through: services invalidate on their own writes
- TTL fallback: stale data triggers background refresh automatically
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    fetched_at: float
    ttl: float
    refreshing: bool = False

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self.fetched_at) > self.ttl

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.fetched_at


class CacheManager:
    """Async in-memory cache with stale-while-revalidate semantics.

    Includes LRU eviction when max_size is reached to prevent unbounded growth.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._max_size = max_size

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: float = 30.0,
    ) -> Any:
        """Get cached value or fetch from source.

        Args:
            key: Cache key (e.g. "day1:clusters:list")
            fetcher: Async callable that fetches fresh data from GitLab
            ttl: Seconds before entry is considered stale
        """
        entry = self._store.get(key)

        if entry is not None:
            if not entry.is_stale:
                return entry.value

            # Stale hit — return cached data immediately, refresh in background
            if not entry.refreshing:
                entry.refreshing = True
                asyncio.create_task(
                    self._background_refresh(key, fetcher, ttl),
                    name=f"cache-refresh:{key}",
                )
            return entry.value

        # Cache miss — fetch synchronously with per-key lock (prevents thundering herd)
        if key not in self._key_locks:
            self._key_locks[key] = asyncio.Lock()
        lock = self._key_locks[key]

        async with lock:
            # Double-check after acquiring lock (another task may have fetched already)
            entry = self._store.get(key)
            if entry is not None:
                return entry.value

            value = await fetcher()
            self._evict_if_full()
            self._store[key] = CacheEntry(
                value=value,
                fetched_at=time.monotonic(),
                ttl=ttl,
            )
            return value

    def _evict_if_full(self) -> None:
        """Evict oldest entries if cache exceeds max_size."""
        if len(self._store) < self._max_size:
            return
        # Sort by fetched_at (oldest first) and remove 10% of entries
        entries = sorted(self._store.items(), key=lambda x: x[1].fetched_at)
        evict_count = max(1, len(entries) // 10)
        for key, _ in entries[:evict_count]:
            del self._store[key]
        logger.debug(
            "Cache evicted %d oldest entries (was at max_size=%d)", evict_count, self._max_size
        )

    async def _background_refresh(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: float,
    ) -> None:
        try:
            value = await fetcher()
            self._store[key] = CacheEntry(
                value=value,
                fetched_at=time.monotonic(),
                ttl=ttl,
            )
            logger.debug("Cache refreshed: %s", key)
        except Exception as exc:
            logger.warning("Background cache refresh failed for %s: %s", key, exc)
            # Keep stale entry; reset flag so next request can try again
            entry = self._store.get(key)
            if entry is not None:
                entry.refreshing = False

    def peek(self, key: str) -> Any | None:
        """Return the cached value if present (fresh or stale), without triggering a fetch."""
        entry = self._store.get(key)
        return entry.value if entry is not None else None

    def invalidate(self, key: str) -> None:
        """Remove a specific key from cache."""
        self._store.pop(key, None)
        logger.debug("Cache invalidated: %s", key)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys that start with prefix.

        Example: invalidate_prefix("day1:clusters") clears all cluster cache entries.
        """
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        if keys:
            logger.debug("Cache invalidated prefix %s (%d keys)", prefix, len(keys))

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        count = len(self._store)
        self._store.clear()
        logger.info("Full cache cleared (%d keys)", count)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics for monitoring and debugging."""
        now = time.monotonic()
        total = len(self._store)
        stale = sum(1 for e in self._store.values() if e.is_stale)
        oldest = max((now - e.fetched_at for e in self._store.values()), default=0.0)
        return {
            "total_keys": total,
            "max_size": self._max_size,
            "fresh_keys": total - stale,
            "stale_keys": stale,
            "oldest_entry_seconds": round(oldest, 1),
        }
