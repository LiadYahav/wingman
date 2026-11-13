"""A per-replica TTL cache for GitLab reads (ADR-0011, ADR-0041).

Reads dominate: every page lists clusters or addons, and each list is many
GitLab calls. The cache keeps a value for a short TTL, and concurrent misses
for one key share a single fetch, so a burst of page loads costs one GitLab
round trip instead of one per request. A failed fetch is never cached. The
fetch runs in a task of its own that every reader awaits shielded, the first
one too, so a reader whose request is dropped never cancels the others' fetch.

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
from functools import partial
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
        self._inflight: dict[str, asyncio.Task[object]] = {}
        self._generation: dict[str, int] = {}
        self._tasks: set[asyncio.Task[object]] = set()

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
        task = self._inflight.get(key)
        if task is None:
            task = self._start(key, fetch, ttl, stale)
        return cast("T", await asyncio.shield(task))

    def _start[T](
        self, key: str, fetch: Callable[[], Awaitable[T]], ttl: float, stale: float
    ) -> asyncio.Task[object]:
        """Fetch ``key`` in a task of its own, which every reader of ``key`` waits for."""
        task = asyncio.ensure_future(
            self._run(key, self._generation.get(key, 0), fetch, ttl, stale)
        )
        self._inflight[key] = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run[T](
        self, key: str, generation: int, fetch: Callable[[], Awaitable[T]], ttl: float, stale: float
    ) -> T:
        try:
            value = await fetch()
        finally:
            if self._inflight.get(key) is asyncio.current_task():
                del self._inflight[key]
        # An invalidation during the fetch means the value may predate a write: don't keep it.
        if self._generation.get(key, 0) == generation:
            self._store(key, value, ttl, stale)
        return value

    def _refresh[T](
        self, key: str, fetch: Callable[[], Awaitable[T]], ttl: float, stale: float
    ) -> None:
        """Start one background fetch of ``key``, unless one is already running."""
        if key not in self._inflight:
            self._start(key, fetch, ttl, stale).add_done_callback(partial(_log_failed_refresh, key))

    def invalidate(self, key: str) -> None:
        """Forget ``key``, and any fetch of it already running.

        A fetch that started before a write may answer what the write
        replaced, so a later read never joins it: it starts its own.
        """
        self._entries.pop(key, None)
        self._inflight.pop(key, None)
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


def _log_failed_refresh(key: str, task: asyncio.Task[object]) -> None:
    """A failed refresh keeps the stale value (``get_or_fetch``); it is only logged."""
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.warning("refreshing %s failed: %s: %s", key, type(exc).__name__, exc)
