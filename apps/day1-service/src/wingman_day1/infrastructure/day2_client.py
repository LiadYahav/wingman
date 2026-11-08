"""HttpDay2Addons: what the day2 service reports as installed on a cluster.

The only place day1 knows day2 exists. Day1 reads; it never asks day2 to
install anything (ADR-0016). It authenticates with a short-lived session
token of its own (the services share the session secret), issued by the
injected ``token`` callable, so a cached drift result does not depend on
which user's request computed it.

Any failure is ``Day2UnavailableError``: addon state is then *unknown*,
never "nothing installed" (ADR-0004).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.observed import Day2Operation, Observer, Timer

JSON = Any
"""A decoded JSON value; narrowed where it is read."""


class HttpDay2Addons:
    """A ``Day2Addons`` over day2's ``GET /api/day2/clusters/{name}/addons``."""

    def __init__(
        self,
        *,
        base_url: str,
        token: Callable[[], str],
        timeout_seconds: float = 5.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Call day2 at ``base_url`` (e.g. ``http://wingman-day2:8002``) as ``token()``."""
        self._token = token
        self._observer = Observer(Dependency.DAY2, metrics, timer=timer)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """See Day2Addons.installed."""
        return await self._observer.call(
            Day2Operation.LIST_INSTALLED_ADDONS, self._installed(cluster)
        )

    async def _installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        path = f"/api/day2/clusters/{quote(cluster.name, safe='')}/addons"
        try:
            response = await self._client.get(
                path,
                params={"mce": cluster.mce},
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.TransportError as exc:
            raise Day2UnavailableError(
                f"day2 unreachable listing addons of {cluster.name}: {type(exc).__name__}"
            ) from exc
        if response.status_code != 200:
            raise Day2UnavailableError(
                f"day2 answered {response.status_code} listing addons of {cluster.name}"
            )
        try:
            return _installed(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise Day2UnavailableError(
                f"day2 returned a malformed addon list for {cluster.name}"
            ) from exc


def _installed(raw: JSON) -> list[InstalledAddon]:
    if not isinstance(raw, dict):
        raise TypeError("the response is not an object")
    items = raw["installed"]
    if not isinstance(items, list):
        raise TypeError("installed is not a list")
    addons: list[InstalledAddon] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("an installed addon is not an object")
        team, name, version = item["team"], item["name"], item.get("version") or ""
        if not (isinstance(team, str) and team and isinstance(name, str) and name):
            raise ValueError("an installed addon has no team or name")
        if not isinstance(version, str):
            raise TypeError("an installed addon's version is not a string")
        addons.append(InstalledAddon(team=team, name=name, version=version))
    return addons
