"""Drift: does a cluster still match its flavor?

Two things make a linked cluster ``drifted`` (ADR-0033):

- **value drift**: a value the flavor locks that the cluster file does not
  hold (``wingman_day1.domain.value_drift``). Presets never drift.
- **a missing add-on**: a flavor day2 add-on that day2 does not report as
  installed (ADR-0016). One installed at another version is reported beside
  the verdict, never counted as drift (ADR-0025).

Day1 cannot re-render a cluster to compare files: the file legitimately
changes after create (CI and the allocate-segment workflow add keys, people
edit what is not locked). A cluster whose state cannot be determined (its
file or flavor is gone or unreadable, day2 did not answer and nothing else
drifted) is ``unknown``, never in sync (ADR-0004; herzi's "unknown is not
zero").
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.specs import SpecCatalog, SpecEntry
from wingman_day1.domain.addons import (
    AddonDrift,
    RequestedAddon,
    VersionDifference,
    compare_addons,
)
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import Day2UnavailableError, InvalidClusterFileError
from wingman_day1.domain.machine_configs import MachineConfigCatalog
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec
from wingman_day1.domain.value_drift import ValueDrift, value_drift
from wingman_day1.ports import Day2Addons

MAX_DRIFT_CONCURRENCY = 8


class DriftState(StrEnum):
    """A cluster's drift verdict."""

    IN_SYNC = "in_sync"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"
    NOT_LINKED = "not_linked"


@dataclass(frozen=True, slots=True)
class ClusterDrift:
    """One cluster's drift against its flavor."""

    ref: ClusterRef
    state: DriftState
    spec_name: str | None = None
    spec_version: str | None = None
    """The flavor version the file's header names (the one it was created or synced from)."""
    current_spec_version: str | None = None
    value_drift: tuple[ValueDrift, ...] = ()
    """Locked values the cluster file does not hold (ADR-0033)."""
    addon_drift: tuple[AddonDrift, ...] = ()
    """Flavor add-ons the cluster does not have, which day2 can install."""
    version_differences: tuple[VersionDifference, ...] = ()
    """Flavor add-ons at another version: reported only, never drift (ADR-0025)."""
    error: str | None = None
    """Why the verdict (or a part of it) could not be determined."""

    @property
    def is_drifted(self) -> bool | None:
        """``True``/``False``, or ``None`` when it could not be determined."""
        if self.state is DriftState.UNKNOWN:
            return None
        return self.state is DriftState.DRIFTED


class DriftService:
    """Drift for one cluster, all clusters, or a flavor's clusters."""

    def __init__(
        self,
        clusters: ClusterService,
        specs: SpecCatalog,
        day2: Day2Addons,
        machine_configs: MachineConfigService,
    ) -> None:
        """Compare cluster files with their flavors, and add-ons with what ``day2`` reports."""
        self._clusters = clusters
        self._specs = specs
        self._day2 = day2
        self._machine_configs = machine_configs

    async def for_cluster(self, ref: ClusterRef) -> ClusterDrift:
        """One cluster."""
        cluster = await self._clusters.get(ref)
        specs = {e.name: e for e in await self._specs.entries()}
        return await self._check(cluster, specs, await self._machine_configs.catalog())

    async def summary(self) -> list[ClusterDrift]:
        """Every cluster."""
        return await self._many(await self._clusters.clusters())

    async def for_spec(self, name: str) -> list[ClusterDrift]:
        """The clusters whose header names the flavor."""
        clusters = await self._clusters.clusters()
        return await self._many(c for c in clusters if c.provenance.spec_name == name)

    async def against(
        self, cluster: ClusterFile, spec: ClusterSpec, catalog: MachineConfigCatalog
    ) -> ClusterDrift:
        """``cluster`` against the flavor ``spec``, whatever flavor its header names (import)."""
        name = spec.metadata.name
        return await self._compare(cluster, name, SpecEntry(name, spec), catalog)

    async def _many(self, clusters: Iterable[ClusterFile]) -> list[ClusterDrift]:
        specs = {e.name: e for e in await self._specs.entries()}
        catalog = await self._machine_configs.catalog()
        limit = asyncio.Semaphore(MAX_DRIFT_CONCURRENCY)

        async def one(cluster: ClusterFile) -> ClusterDrift:
            async with limit:
                return await self._check(cluster, specs, catalog)

        return list(await asyncio.gather(*(one(c) for c in clusters)))

    async def _check(
        self,
        cluster: ClusterFile,
        specs: Mapping[str, SpecEntry],
        catalog: MachineConfigCatalog,
    ) -> ClusterDrift:
        name = cluster.provenance.spec_name
        if not name:
            return ClusterDrift(cluster.ref, DriftState.NOT_LINKED)
        return await self._compare(cluster, name, specs.get(name), catalog)

    async def _compare(
        self,
        cluster: ClusterFile,
        name: str,
        entry: SpecEntry | None,
        catalog: MachineConfigCatalog,
    ) -> ClusterDrift:
        provenance = cluster.provenance

        def verdict(
            state: DriftState,
            *,
            current: str | None = None,
            values: tuple[ValueDrift, ...] = (),
            drift: tuple[AddonDrift, ...] = (),
            differences: tuple[VersionDifference, ...] = (),
            error: str | None = None,
        ) -> ClusterDrift:
            return ClusterDrift(
                cluster.ref,
                state,
                spec_name=name,
                spec_version=provenance.spec_version if provenance.spec_name == name else None,
                current_spec_version=current,
                value_drift=values,
                addon_drift=drift,
                version_differences=differences,
                error=error,
            )

        if entry is None:
            return verdict(DriftState.UNKNOWN, error=f"spec {name!r} no longer exists")
        if entry.spec is None:
            return verdict(DriftState.UNKNOWN, error=f"spec {name!r} cannot be read")
        spec = entry.spec
        current = spec.metadata.version
        try:
            values = load_values(cluster.content)
        except InvalidClusterFileError as exc:
            return verdict(
                DriftState.UNKNOWN,
                current=current,
                error=f"the cluster file cannot be read: {exc}",
            )
        locked = value_drift(
            spec.locks(),
            values,
            cluster_name=cluster.hosted_cluster.cluster_name,
            catalog=catalog,
        )
        expected = [RequestedAddon(a.team, a.name, a.version) for a in spec.spec.day2.addons]
        if not expected:
            state = DriftState.DRIFTED if locked else DriftState.IN_SYNC
            return verdict(state, current=current, values=locked)
        try:
            installed = await self._day2.installed(cluster.ref)
        except Day2UnavailableError as exc:
            if locked:  # drifted whatever day2 says; only the add-on part is unknown
                return verdict(
                    DriftState.DRIFTED,
                    current=current,
                    values=locked,
                    error=f"day2 did not answer, so missing add-ons are unknown: {exc}",
                )
            return verdict(DriftState.UNKNOWN, current=current, error=f"day2 did not answer: {exc}")
        found = compare_addons(expected, installed, requested=provenance.requested_addons)
        state = DriftState.DRIFTED if found.missing or locked else DriftState.IN_SYNC
        return verdict(
            state,
            current=current,
            values=locked,
            drift=found.missing,
            differences=found.version_differences,
        )
