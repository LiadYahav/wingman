"""Drift: does a cluster still match its flavor, at the version it is on?

A cluster is measured against the flavor version its header names
(``# specVersion``), read from the specs repo's history, never against the
newest (ADR-0044): a newer version is an **update**, which reaches the
cluster through its own MR, never drift. A header with no version, or a
version history does not have, is ``unknown``.

Two things make a linked cluster ``drifted`` (ADR-0036):

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
from dataclasses import dataclass, replace
from enum import StrEnum

from wingman_core.domain.merge_request import MergeRequest
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.open_syncs import OpenSyncs, open_syncs
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
from wingman_day1.ports import Day2Addons, RepoReads

MAX_DRIFT_CONCURRENCY = 8


class DriftState(StrEnum):
    """A cluster's drift verdict."""

    IN_SYNC = "in_sync"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"
    NOT_LINKED = "not_linked"


@dataclass(frozen=True, slots=True)
class FlavorUpdate:
    """A newer version of the cluster's flavor: an update, never drift (ADR-0044)."""

    version: str
    merge_request: MergeRequest | None = None
    """The open MR that moves the cluster to ``version``, if one is open."""


@dataclass(frozen=True, slots=True)
class ClusterDrift:
    """One cluster's drift against its flavor."""

    ref: ClusterRef
    state: DriftState
    spec_name: str | None = None
    spec_version: str | None = None
    """The flavor version the file's header names (the one it was created or synced from)."""
    current_spec_version: str | None = None
    """The flavor's newest version."""
    value_drift: tuple[ValueDrift, ...] = ()
    """Locked values the cluster file does not hold (ADR-0036)."""
    addon_drift: tuple[AddonDrift, ...] = ()
    """Flavor add-ons the cluster does not have, which day2 can install."""
    version_differences: tuple[VersionDifference, ...] = ()
    """Flavor add-ons at another version: reported only, never drift (ADR-0025)."""
    error: str | None = None
    """Why the verdict (or a part of it) could not be determined."""
    update: FlavorUpdate | None = None
    """The flavor's newest version when the cluster is on an older one."""

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
        day1: RepoReads,
    ) -> None:
        """Compare cluster files with their flavors, and add-ons with what ``day2`` reports.

        ``day1`` gives the open sync MRs: a cluster's pending update.
        """
        self._clusters = clusters
        self._specs = specs
        self._day2 = day2
        self._machine_configs = machine_configs
        self._day1 = day1

    async def for_cluster(self, ref: ClusterRef) -> ClusterDrift:
        """One cluster."""
        cluster = await self._clusters.get(ref)
        specs = {e.name: e for e in await self._specs.entries()}
        catalog = await self._machine_configs.catalog()
        return await self._check(cluster, specs, catalog, await open_syncs(self._day1))

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
        """``cluster`` against the flavor ``spec``, whatever its header names (import, sync)."""
        return await self._compare(cluster, spec.metadata.name, spec, catalog)

    async def _many(self, clusters: Iterable[ClusterFile]) -> list[ClusterDrift]:
        specs = {e.name: e for e in await self._specs.entries()}
        catalog = await self._machine_configs.catalog()
        syncs = await open_syncs(self._day1)
        limit = asyncio.Semaphore(MAX_DRIFT_CONCURRENCY)

        async def one(cluster: ClusterFile) -> ClusterDrift:
            async with limit:
                return await self._check(cluster, specs, catalog, syncs)

        return list(await asyncio.gather(*(one(c) for c in clusters)))

    async def _check(
        self,
        cluster: ClusterFile,
        specs: Mapping[str, SpecEntry],
        catalog: MachineConfigCatalog,
        syncs: OpenSyncs,
    ) -> ClusterDrift:
        """The cluster against the flavor version its header names; a newer one is an update."""
        provenance = cluster.provenance
        name = provenance.spec_name
        if not name:
            return ClusterDrift(cluster.ref, DriftState.NOT_LINKED)
        entry = specs.get(name)
        if entry is None:
            return _unknown(cluster, name, f"spec {name!r} no longer exists")
        newest = entry.spec.metadata.version if entry.spec is not None else None
        version = provenance.spec_version
        update = (
            FlavorUpdate(newest, syncs.to(cluster.ref.name, name, newest))
            if newest is not None and newest != version
            else None
        )
        try:
            load_values(cluster.content)
        except InvalidClusterFileError as exc:
            return _unknown(
                cluster,
                name,
                f"the cluster file cannot be read: {exc}",
                newest=newest,
                update=update,
            )
        if version is None:
            return _unknown(
                cluster,
                name,
                f"the header names no version of flavor {name!r}, so what the cluster should "
                "hold is unknown; syncing it records the newest",
                newest=newest,
                update=update,
            )
        spec = (
            entry.spec
            if entry.spec is not None and newest == version
            else await self._specs.at_version(name, version)
        )
        if spec is None:
            return _unknown(
                cluster,
                name,
                f"flavor {name!r} v{version} is not in the specs repo's history"
                + ("" if entry.spec is not None else "; the newest file cannot be read either"),
                newest=newest,
                update=update,
            )
        found = await self._compare(cluster, name, spec, catalog)
        error = found.error
        if entry.spec is None and error is None:
            error = f"flavor {name!r}'s newest file cannot be read, so a newer version is unknown"
        return replace(found, current_spec_version=newest, update=update, error=error)

    async def _compare(
        self,
        cluster: ClusterFile,
        name: str,
        spec: ClusterSpec,
        catalog: MachineConfigCatalog,
    ) -> ClusterDrift:
        """``cluster`` against ``spec``: its locked values and its add-ons."""
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


def _unknown(
    cluster: ClusterFile,
    name: str,
    error: str,
    *,
    newest: str | None = None,
    update: FlavorUpdate | None = None,
) -> ClusterDrift:
    """A linked cluster whose verdict cannot be determined: never in sync."""
    provenance = cluster.provenance
    return ClusterDrift(
        cluster.ref,
        DriftState.UNKNOWN,
        spec_name=name,
        spec_version=provenance.spec_version if provenance.spec_name == name else None,
        current_spec_version=newest,
        error=error,
        update=update,
    )
