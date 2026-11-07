"""FakeDay2Addons: a Day2Addons over a fixed table, for tests and ``WINGMAN_GIT_BACKEND=fake``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef


class FakeDay2Addons:
    """Installed addons per cluster name; ``unavailable`` makes every call fail like day2 down."""

    def __init__(
        self,
        installed: Mapping[str, Sequence[InstalledAddon]] | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        """Seed what day2 reports, keyed by cluster name."""
        self._installed = {name: list(addons) for name, addons in (installed or {}).items()}
        self.unavailable = unavailable

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """See Day2Addons.installed."""
        if self.unavailable:
            raise Day2UnavailableError(f"day2 unreachable listing addons of {cluster.name} (fake)")
        return list(self._installed.get(cluster.name, []))
