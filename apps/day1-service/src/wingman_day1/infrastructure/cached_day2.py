"""CachedDay2Addons: day2's installed-addon lists, cached for a few seconds per cluster.

The drift summary asks day2 once per linked cluster; the cache turns a burst
of page loads into one call per cluster per TTL (ADR-0011). A failure is not
cached, so an unknown answer is retried next time rather than remembered.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import Day2Addons


class CachedDay2Addons:
    """A ``Day2Addons`` that caches ``inner``'s answers."""

    def __init__(self, inner: Day2Addons, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s answers in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """See Day2Addons.installed."""
        return await self._cache.get_or_fetch(
            keys.day2_installed(cluster.site, cluster.mce, cluster.name),
            lambda: self._inner.installed(cluster),
            ttl=self._ttl,
        )
