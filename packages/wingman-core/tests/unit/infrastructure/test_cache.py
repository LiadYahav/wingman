from __future__ import annotations

import asyncio

import pytest

from wingman_core.infrastructure.cache import TtlCache, stale_for


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_values_live_for_their_ttl() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10) == 1
    clock.now = 9.9
    assert await cache.get_or_fetch("k", fetch, ttl=10) == 1
    clock.now = 10.0
    assert await cache.get_or_fetch("k", fetch, ttl=10) == 2


async def test_concurrent_misses_share_one_fetch() -> None:
    cache = TtlCache()
    calls = 0
    release = asyncio.Event()

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "v"

    waiters = [asyncio.create_task(cache.get_or_fetch("k", fetch, ttl=10)) for _ in range(5)]
    await asyncio.sleep(0)
    release.set()
    assert await asyncio.gather(*waiters) == ["v"] * 5
    assert calls == 1


async def test_a_cancelled_first_reader_does_not_cancel_the_shared_fetch() -> None:
    """The first reader's request is dropped: the others still get the value, and it is kept."""
    cache = TtlCache()
    calls = 0
    release = asyncio.Event()

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "v"

    first = asyncio.create_task(cache.get_or_fetch("k", fetch, ttl=10))
    second = asyncio.create_task(cache.get_or_fetch("k", fetch, ttl=10))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == "v"
    assert await cache.get_or_fetch("k", fetch, ttl=10) == "v"
    assert calls == 1


async def test_a_fetch_whose_only_reader_is_cancelled_still_keeps_its_value() -> None:
    cache = TtlCache()
    calls = 0
    release = asyncio.Event()

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "v"

    only = asyncio.create_task(cache.get_or_fetch("k", fetch, ttl=10))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    only.cancel()
    with pytest.raises(asyncio.CancelledError):
        await only
    release.set()
    assert await asyncio.wait_for(cache.get_or_fetch("k", fetch, ttl=10), 1) == "v"
    assert calls == 1


async def test_failures_are_shared_but_never_cached() -> None:
    cache = TtlCache()
    attempts = 0
    release = asyncio.Event()

    async def failing() -> str:
        nonlocal attempts
        attempts += 1
        await release.wait()
        raise RuntimeError("gitlab down")

    first = asyncio.create_task(cache.get_or_fetch("k", failing, ttl=10))
    second = asyncio.create_task(cache.get_or_fetch("k", failing, ttl=10))
    await asyncio.sleep(0)
    release.set()
    for task in (first, second):
        with pytest.raises(RuntimeError):
            await task
    assert attempts == 1

    async def working() -> str:
        return "ok"

    assert await cache.get_or_fetch("k", working, ttl=10) == "ok"


async def test_invalidation_by_key_and_prefix() -> None:
    cache = TtlCache()
    for key in ("day1:clusters", "day1:cluster:a", "day2:addons"):
        await cache.get_or_fetch(key, lambda key=key: _value(key), ttl=60)
    assert cache.invalidate_prefix("day1:") == 2
    cache.invalidate("day2:addons")
    assert await cache.get_or_fetch("day1:clusters", lambda: _value("fresh"), ttl=60) == "fresh"
    assert await cache.get_or_fetch("day2:addons", lambda: _value("fresh2"), ttl=60) == "fresh2"


async def test_a_value_fetched_across_an_invalidation_is_not_kept() -> None:
    cache = TtlCache()
    release = asyncio.Event()

    async def slow() -> str:
        await release.wait()
        return "read before the write"

    task = asyncio.create_task(cache.get_or_fetch("k", slow, ttl=60))
    await asyncio.sleep(0)
    cache.invalidate_prefix("k")
    release.set()
    assert await task == "read before the write"
    assert await cache.get_or_fetch("k", lambda: _value("after"), ttl=60) == "after"


async def test_size_is_bounded() -> None:
    cache = TtlCache(max_entries=2)
    for key, ttl in (("a", 10), ("b", 20), ("c", 30)):
        await cache.get_or_fetch(key, lambda key=key: _value(key), ttl=ttl)
    assert await cache.get_or_fetch("a", lambda: _value("refetched"), ttl=10) == "refetched"


async def _value(value: str) -> str:
    return value


async def test_a_stale_value_is_answered_while_one_fetch_refreshes_it() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0
    release = asyncio.Event()

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        if calls > 1:
            await release.wait()
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1
    clock.now = 15.0
    # Expired but within its stale time: answered at once, three times, one refresh
    assert [await cache.get_or_fetch("k", fetch, ttl=10, stale=20) for _ in range(3)] == [1, 1, 1]
    await asyncio.sleep(0)
    assert calls == 2
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 2


async def test_past_its_stale_time_a_value_is_fetched_inline() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1
    clock.now = 30.0
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 2


async def test_a_failed_refresh_keeps_the_stale_value_until_its_time_is_over() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    fail = False

    async def fetch() -> str:
        if fail:
            raise RuntimeError("GitLab down")
        return "v"

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == "v"
    fail = True
    clock.now = 15.0
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == "v"
    await asyncio.sleep(0)
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == "v"
    clock.now = 30.0
    with pytest.raises(RuntimeError, match="GitLab down"):
        await cache.get_or_fetch("k", fetch, ttl=10, stale=20)


async def test_an_invalidated_value_is_never_answered_stale() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1
    clock.now = 15.0
    cache.invalidate("k")
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 2


async def test_a_refresh_across_an_invalidation_is_not_kept() -> None:
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0
    release = asyncio.Event()

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1
    clock.now = 15.0
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1  # starts refresh 2
    await asyncio.sleep(0)
    cache.invalidate("k")  # a write lands while refresh 2 runs
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 3


async def test_a_read_after_an_invalidation_never_joins_a_fetch_from_before_it() -> None:
    """A write's own next read must see it, even while a pre-write refresh still runs."""
    clock = Clock()
    cache = TtlCache(clock=clock)
    calls = 0
    release = asyncio.Event()

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()  # refresh 2 read GitLab before the write
        return calls

    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1
    clock.now = 15.0
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 1  # starts refresh 2
    await asyncio.sleep(0)
    cache.invalidate("k")  # the write lands while refresh 2 still runs
    # Its own fetch, not refresh 2 (which would wait on `release` and time out)
    assert await asyncio.wait_for(cache.get_or_fetch("k", fetch, ttl=10, stale=20), 1) == 3
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert await cache.get_or_fetch("k", fetch, ttl=10, stale=20) == 3


def test_stale_time_keeps_every_answer_within_a_minute() -> None:
    assert stale_for(30) == 30
    assert stale_for(15) == 45
    assert stale_for(60) == 0
    assert stale_for(90) == 0
