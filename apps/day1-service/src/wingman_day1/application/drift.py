"""Drift: does a cluster still match its spec?

Day1 cannot re-render a cluster to compare files: no inputs are stored, and
the file legitimately changes after create (CI and the allocate-segment
workflow add keys, people edit it). So drift is the spec's day2 addons:
each must be installed. One installed at another version than the spec
names is reported beside the verdict, never counted as drift (ADR-0025). A
cluster whose state cannot
be determined (its spec is gone or unreadable, day2 did not answer) is
``unknown``, never in sync (ADR-0004; herzi's "unknown is not zero").
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.specs import SpecCatalog, SpecEntry
from wingman_day1.domain.addons import (
    AddonDrift,
    RequestedAddon,
    VersionDifference,
    compare_addons,
)
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
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
    """One cluster's drift against its spec."""

    ref: ClusterRef
    state: DriftState
    spec_name: str | None = None
    spec_version: str | None = None
    """The spec version the cluster was created from."""
    current_spec_version: str | None = None
    addon_drift: tuple[AddonDrift, ...] = ()
    """Spec addons the cluster does not have: the drift, which day2 can install."""
    version_differences: tuple[VersionDifference, ...] = ()
    """Spec addons at another version: reported only, never drift (ADR-0025)."""
    error: str | None = None

    @property
    def is_drifted(self) -> bool | None:
        """``True``/``False``, or ``None`` when it could not be determined."""
        if self.state is DriftState.UNKNOWN:
            return None
        return self.state is DriftState.DRIFTED


class DriftService:
    """Drift for one cluster, all clusters, or a spec's clusters."""

    def __init__(self, clusters: ClusterService, specs: SpecCatalog, day2: Day2Addons) -> None:
        """Compare cluster files and specs with what ``day2`` reports."""
        self._clusters = clusters
        self._specs = specs
        self._day2 = day2

    async def for_cluster(self, ref: ClusterRef) -> ClusterDrift:
        """One cluster."""
        cluster = await self._clusters.get(ref)
        return await self._check(cluster, {e.name: e for e in await self._specs.entries()})

    async def summary(self) -> list[ClusterDrift]:
        """Every cluster."""
        return await self._many(await self._clusters.clusters())

    async def for_spec(self, name: str) -> list[ClusterDrift]:
        """The clusters created from a spec."""
        clusters = await self._clusters.clusters()
        return await self._many(c for c in clusters if c.provenance.spec_name == name)

    async def _many(self, clusters: Iterable[ClusterFile]) -> list[ClusterDrift]:
        specs = {e.name: e for e in await self._specs.entries()}
        limit = asyncio.Semaphore(MAX_DRIFT_CONCURRENCY)

        async def one(cluster: ClusterFile) -> ClusterDrift:
            async with limit:
                return await self._check(cluster, specs)

        return list(await asyncio.gather(*(one(c) for c in clusters)))

    async def _check(self, cluster: ClusterFile, specs: Mapping[str, SpecEntry]) -> ClusterDrift:
        provenance = cluster.provenance
        name = provenance.spec_name
        if not name:
            return ClusterDrift(cluster.ref, DriftState.NOT_LINKED)

        def verdict(
            state: DriftState,
            *,
            current: str | None = None,
            drift: tuple[AddonDrift, ...] = (),
            differences: tuple[VersionDifference, ...] = (),
            error: str | None = None,
        ) -> ClusterDrift:
            return ClusterDrift(
                cluster.ref,
                state,
                spec_name=name,
                spec_version=provenance.spec_version,
                current_spec_version=current,
                addon_drift=drift,
                version_differences=differences,
                error=error,
            )

        entry = specs.get(name)
        if entry is None:
            return verdict(DriftState.UNKNOWN, error=f"spec {name!r} no longer exists")
        if entry.spec is None:
            return verdict(DriftState.UNKNOWN, error=f"spec {name!r} cannot be read")
        spec = entry.spec
        current = spec.metadata.version
        expected = [RequestedAddon(a.team, a.name, a.version) for a in spec.spec.day2.addons]
        if not expected:
            return verdict(DriftState.IN_SYNC, current=current)
        try:
            installed = await self._day2.installed(cluster.ref)
        except Day2UnavailableError as exc:
            return verdict(DriftState.UNKNOWN, current=current, error=f"day2 did not answer: {exc}")
        found = compare_addons(expected, installed, requested=provenance.requested_addons)
        state = DriftState.DRIFTED if found.missing else DriftState.IN_SYNC
        return verdict(
            state, current=current, drift=found.missing, differences=found.version_differences
        )
