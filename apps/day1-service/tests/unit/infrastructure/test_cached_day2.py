"""CachedDay2Addons: one day2 call per cluster per TTL, and failures never remembered."""

from __future__ import annotations

import pytest

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.cached_day2 import CachedDay2Addons

HERZI = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")
HAWK = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-hawk-site1")


class CountingDay2:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failing = False

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        self.calls.append(cluster.name)
        if self.failing:
            raise Day2UnavailableError("day2 answered 503")
        return [InstalledAddon("redbull", "cluster-roles", cluster.name)]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_answers_are_cached_per_cluster_until_the_ttl() -> None:
    inner, clock = CountingDay2(), Clock()
    cached = CachedDay2Addons(inner, TtlCache(clock=clock), ttl=30)
    assert (await cached.installed(HERZI))[0].version == HERZI.name
    await cached.installed(HERZI)
    await cached.installed(HAWK)
    assert inner.calls == [HERZI.name, HAWK.name]
    clock.now = 31
    await cached.installed(HERZI)
    assert inner.calls == [HERZI.name, HAWK.name, HERZI.name]


async def test_a_failure_is_not_cached() -> None:
    inner = CountingDay2()
    cached = CachedDay2Addons(inner, TtlCache(), ttl=30)
    inner.failing = True
    with pytest.raises(Day2UnavailableError):
        await cached.installed(HERZI)
    inner.failing = False
    assert await cached.installed(HERZI)
    assert inner.calls == [HERZI.name, HERZI.name]
