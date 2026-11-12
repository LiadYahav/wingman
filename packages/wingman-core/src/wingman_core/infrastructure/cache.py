"""A per-replica TTL cache for GitLab reads (ADR-0011, ADR-0041).

Reads dominate: every page lists clusters or addons, and each list is many
GitLab calls. The cache keeps a value for a short TTL, and concurrent misses
for one key share a single fetch, so a burst of page loads costs one GitLab
round trip instead of one per request. A failed fetch is never cached.

A read may also accept a stale value (``stale``): once the TTL is over, the
value is still answered for ``stale`` more seconds while one fetch refreshes
it in the background, so a page does not wait on GitLab each time a TTL ends.
No value older than ``MAX_AGE`` is answered (ADR-0011's minute).

A write clears the keys it made stale, before the API answers, so the user's
next read sees their own change (server-scan ADR-0028's lesson). A cleared
key is gone, never answered stale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, cast

logger = logging.getLogger(__name__)

MAX_AGE: Final = 60.0
"""The oldest a value may be when it is answered, stale or not (ADR-0011)."""


def stale_for(ttl: float) -> float:
    """How long past ``ttl`` a value may be answered while it refreshes: up to :data:`MAX_AGE`."""
    return max(0.0, MAX_AGE - ttl)


@dataclass(slots=True)
class _Entry:
    value: object
    expires_at: float
    stale_until: float


class TtlCache:
    """Async get-or-fetch with TTL, single-flight, stale-while-refresh and prefix invalidation."""

    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic, max_entries: int = 10_000
    ) -> None:
        """``max_entries`` bounds memory; the oldest-expiring entries go first."""
        self._clock = clock
        self._max_entries = max_entries
        self._entries: dict[str, _Entry] = {}
        self._inflight: dict[str, asyncio.Future[object]] = {}
        self._generation: dict[str, int] = {}
        self._refreshing: set[asyncio.Task[object]] = set()

    async def get_or_fetch[T](
        self,
        key: str,
        fetch: Callable[[], Awaitable[T]],
        *,
        ttl: float,
        stale: float = 0.0,
    ) -> T:
        """The cached value for ``key``, or ``fetch()``'s result, kept for ``ttl`` seconds.

        With ``stale``, an expired value is answered for ``stale`` more seconds
        while one background ``fetch()`` replaces it; a failed refresh keeps
        the old value until that time is over, and then a read fetches (and
        fails) itself.
        """
        now = self._clock()
        entry = self._entries.get(key)
        if entry is not None:
            if entry.expires_at > now:
                return cast("T", entry.value)
            if entry.stale_until > now:
                self._refresh(key, fetch, ttl, stale)
                return cast("T", entry.value)
        pending = self._inflight.get(key)
        if pending is not None:
            return cast("T", await asyncio.shield(pending))
        return await self._fetch(key, fetch, ttl, stale)

    async def _fetch[T](
        self, key: str, fetch: Callable[[], Awaitable[T]], ttl: float, stale: float
    ) -> T:
        future, generation = self._start(key)
        return await self._run(key, future, generation, fetch, ttl, stale)

    def _start(self, key: str) -> tuple[asyncio.Future[object], int]:
        """Mark ``key`` as being fetched, so other readers wait for this fetch."""
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        return future, self._generation.get(key, 0)

    async def _run[T](
        self,
        key: str,
        future: asyncio.Future[object],
        generation: int,
        fetch: Callable[[], Awaitable[T]],
        ttl: float,
        stale: float,
    ) -> T:
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
                self._store(key, value, ttl, stale)
            return value
        finally:
            if self._inflight.get(key) is future:
                del self._inflight[key]

    def _refresh[T](
        self, key: str, fetch: Callable[[], Awaitable[T]], ttl: float, stale: float
    ) -> None:
        """Start one background fetch of ``key``, unless one is already running."""
        if key in self._inflight:
            return
        future, generation = self._start(key)

        async def run() -> object:
            try:
                return await self._run(key, future, generation, fetch, ttl, stale)
            except Exception as exc:  # noqa: BLE001 - a failed refresh keeps the stale value
                logger.warning("refreshing %s failed: %s: %s", key, type(exc).__name__, exc)
                return None

        task = asyncio.ensure_future(run())
        self._refreshing.add(task)
        task.add_done_callback(self._refreshing.discard)

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

    def _store(self, key: str, value: object, ttl: float, stale: float) -> None:
        if len(self._entries) >= self._max_entries and key not in self._entries:
            oldest = min(self._entries, key=lambda k: self._entries[k].expires_at)
            del self._entries[oldest]
        now = self._clock()
        self._entries[key] = _Entry(value, now + ttl, now + ttl + stale)
