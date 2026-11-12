"""Quick Links' checks and ArgoCD counts, cached per replica and shared by every viewer.

Each URL's reading and each instance's counts are kept ``ttl`` seconds, and
for ``ttl`` more they are answered while one check refreshes them in the
background (ADR-0052): a page open on every admin's screen checks each link
once per TTL, two reads at once share one check, and nothing is checked
while nobody looks. A failed check is a reading too, so it is kept like an
answer: a link that is down is not asked again on every read.

This is not GitLab data, so ADR-0011's minute does not bound it: a dot is
at most two TTLs old, and says when it was checked.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.quick_links import ArgoCdReading, LinkReading
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import ArgoCdApi, LinkProbe


class CachedLinkProbe:
    """A ``LinkProbe`` that keeps ``inner``'s readings."""

    def __init__(self, inner: LinkProbe, cache: TtlCache, *, ttl: float) -> None:
        """Keep readings in ``cache`` for ``ttl`` seconds, answered stale for ``ttl`` more."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def check(self, url: str) -> LinkReading:
        """See LinkProbe.check."""
        return await self._cache.get_or_fetch(
            keys.link_check(url), lambda: self._inner.check(url), ttl=self._ttl, stale=self._ttl
        )


class CachedArgoCd:
    """An ``ArgoCdApi`` that keeps ``inner``'s counts."""

    def __init__(self, inner: ArgoCdApi, cache: TtlCache, *, ttl: float) -> None:
        """Keep counts in ``cache`` for ``ttl`` seconds, answered stale for ``ttl`` more."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    def has_token(self, instance: str) -> bool:
        """See ArgoCdApi.has_token."""
        return self._inner.has_token(instance)

    async def application_counts(self, instance: str, url: str) -> ArgoCdReading:
        """See ArgoCdApi.application_counts."""
        return await self._cache.get_or_fetch(
            keys.argocd_counts(instance, url),
            lambda: self._inner.application_counts(instance, url),
            ttl=self._ttl,
            stale=self._ttl,
        )
