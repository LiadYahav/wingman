"""A per-replica TTL cache for GitLab reads (ADR-0011).

Reads dominate: every page lists clusters or addons, and each list is many
GitLab calls. The cache keeps a value for a short TTL, and concurrent misses
for one key share a single fetch, so a burst of page loads costs one GitLab
round trip instead of one per request. A failed fetch is never cached.

A write clears the keys it made stale, before the API answers, so the user's
next read sees their own change (server-scan ADR-0028's lesson).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast


@dataclass(slots=True)
class _Entry:
    value: object
    expires_at: float


class TtlCache:
    """Async get-or-fetch with TTL, single-flight and prefix invalidation."""

    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic, max_entries: int = 10_000
    ) -> None:
        """``max_entries`` bounds memory; the oldest-expiring entries go first."""
        self._clock = clock
        self._max_entries = max_entries
        self._entries: dict[str, _Entry] = {}
        self._inflight: dict[str, asyncio.Future[object]] = {}
        self._generation: dict[str, int] = {}

    async def get_or_fetch[T](
        self, key: str, fetch: Callable[[], Awaitable[T]], *, ttl: float
    ) -> T:
        """The cached value for ``key``, or ``fetch()``'s result, kept for ``ttl`` seconds."""
        entry = self._entries.get(key)
        if entry is not None and entry.expires_at > self._clock():
            return cast("T", entry.value)
        pending = self._inflight.get(key)
        if pending is not None:
            return cast("T", await asyncio.shield(pending))
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        generation = self._generation.get(key, 0)
        try:
            value = await fetch()
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved; waiters re-raise it themselves
            raise
        else:
            future.set_result(value)
            # An invalidation during the fetch means the value may predate a write: don't keep it.
            if self._generation.get(key, 0) == generation:
                self._store(key, value, ttl)
            return value
        finally:
            del self._inflight[key]

    def invalidate(self, key: str) -> None:
        """Forget ``key``."""
        self._entries.pop(key, None)
        self._generation[key] = self._generation.get(key, 0) + 1

    def invalidate_prefix(self, prefix: str) -> int:
        """Forget every key starting with ``prefix``; returns how many were cached."""
        keys = [k for k in self._entries if k.startswith(prefix)]
        keys += [k for k in self._inflight if k.startswith(prefix) and k not in keys]
        for key in keys:
            self.invalidate(key)
        return len(keys)

    def _store(self, key: str, value: object, ttl: float) -> None:
        if len(self._entries) >= self._max_entries and key not in self._entries:
            oldest = min(self._entries, key=lambda k: self._entries[k].expires_at)
            del self._entries[oldest]
        self._entries[key] = _Entry(value, self._clock() + ttl)
