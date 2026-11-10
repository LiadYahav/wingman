"""Existing clusters joining a flavor (ADR-0037).

A cluster Wingman did not create has no flavor link. Import writes the link
(the comment header Wingman writes at create, ADR-0012) into each picked
cluster file, all in one day1 merge request, and changes nothing else in
them: the text edit keeps every other byte, the CI block included
(``wingman_day1.domain.cluster_text``). After the merge the clusters follow
the flavor, and what differs shows as drift (ADR-0036); sync fixes it.

The preview compares each picked cluster with the flavor first. A cluster
already linked to another flavor is refused unless the request says to
re-link it; one already linked to this flavor has nothing to import.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.drift import ClusterDrift, DriftService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.changes import FileUpdate, ImportChange, ProvisionResult
from wingman_day1.domain.cluster_file import Provenance
from wingman_day1.domain.cluster_text import with_header
from wingman_day1.domain.errors import InvalidInputError, StaleError, UneditableFileError
from wingman_day1.domain.locks import is_configs_lock
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec
from wingman_day1.ports import ClusterProvisioner

MAX_IMPORT: Final = 50
"""Clusters per import: one commit and one review."""
MAX_IMPORT_CONCURRENCY: Final = 8


class ImportStatus(StrEnum):
    """Whether a picked cluster can be imported into the flavor."""

    READY = "ready"
    """Not linked to a flavor: the import links it."""
    RELINK = "relink"
    """Linked to another flavor: imported only when the request says ``relink``."""
    LINKED = "linked"
    """Already linked to this flavor: nothing to import (sync it instead)."""
    REFUSED = "refused"
    """Its file cannot be linked safely; ``problems`` says why."""


@dataclass(frozen=True, slots=True)
class ImportPick:
    """A cluster picked for import, as the preview returned it."""

    ref: ClusterRef
    last_commit_id: str
    relink: bool = False


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    """One picked cluster: whether it can be imported, and how it differs from the flavor."""

    cluster: ClusterFile
    status: ImportStatus
    drift: ClusterDrift
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """What importing the picked clusters into a flavor would do."""

    spec_name: str
    spec_version: str
    candidates: tuple[ImportCandidate, ...]
    warnings: tuple[str, ...]
    """About the flavor: locks that mean little on a cluster the flavor did not create."""


def positional_warnings(spec: ClusterSpec) -> list[str]:
    """Each lock on one nodepool position: on an imported file it is whichever nodepool is there."""
    return [
        f"{lock.path} locks one nodepool by position: on a cluster the flavor did not create it "
        f"compares the file's nodepool[{lock.path.segments[1]}], whichever that is"
        + ("; nodepools[*].configs compares every nodepool" if is_configs_lock(lock.path) else "")
        for lock in spec.locks()
        if lock.path.segments[0] == "nodepools" and not lock.is_rule
    ]


def _relinked_addons(cluster: ClusterFile, spec: ClusterSpec) -> tuple[RequestedAddon, ...]:
    """The add-on values requested before that the new flavor still lists, at its version."""
    listed = {str(a.key): a for a in spec.spec.day2.addons}
    return tuple(
        RequestedAddon(a.team, a.name, listed[str(a.key)].version, a.override_values)
        for a in cluster.provenance.requested_addons
        if str(a.key) in listed and a.override_values
    )


class ImportService:
    """Preview and propose linking existing clusters to a flavor."""

    def __init__(
        self,
        clusters: ClusterService,
        specs: SpecCatalog,
        drift: DriftService,
        machine_configs: MachineConfigService,
        provisioner: ClusterProvisioner,
    ) -> None:
        """Read clusters and flavors, compare them, and propose through ``provisioner``."""
        self._clusters = clusters
        self._specs = specs
        self._drift = drift
        self._machine_configs = machine_configs
        self._provisioner = provisioner

    async def preview(self, flavor: str, refs: Sequence[ClusterRef]) -> ImportPreview:
        """Each picked cluster against the flavor: whether it can join, and what differs."""
        spec = await self._specs.get(flavor)
        _require_picks(refs)
        catalog = await self._machine_configs.catalog()
        limit = asyncio.Semaphore(MAX_IMPORT_CONCURRENCY)

        async def one(ref: ClusterRef) -> ImportCandidate:
            async with limit:
                cluster = await self._clusters.get(ref)
                drift = await self._drift.against(cluster, spec, catalog)
            status, problems = self._status(cluster, spec, relink=False)
            return ImportCandidate(cluster, status, drift, tuple(problems))

        candidates = await asyncio.gather(*(one(ref) for ref in refs))
        return ImportPreview(
            flavor,
            spec.metadata.version,
            tuple(candidates),
            tuple(positional_warnings(spec)),
        )

    async def import_clusters(
        self,
        flavor: str,
        picks: Sequence[ImportPick],
        *,
        spec_version: str,
        user: User,
    ) -> ProvisionResult:
        """One day1 MR that links every picked cluster to the flavor, or none at all.

        No file may have changed since the ``last_commit_id`` the preview showed
        (the commit it was read at, ADR-0035); the commit carries it, so a file
        that moves before the commit fails the whole MR (ADR-0006).
        """
        spec = await self._specs.get(flavor)
        if spec.metadata.version != spec_version:
            raise StaleError(
                f"flavor {flavor} is now v{spec.metadata.version}, not v{spec_version}; "
                "preview the import again"
            )
        _require_picks([p.ref for p in picks])
        clusters = await asyncio.gather(*(self._clusters.get(p.ref) for p in picks))
        moved = await asyncio.gather(
            *(self._clusters.changed_since(p.ref, p.last_commit_id) for p in picks)
        )
        stale = [
            f"{c.ref.name} ({pick.last_commit_id[:8]} → {c.last_commit_id[:8]})"
            for pick, c, changed in zip(picks, clusters, moved, strict=True)
            if changed
        ]
        if stale:
            raise StaleError(
                f"changed since the preview: {', '.join(stale)}; preview the import again"
            )
        problems: list[str] = []
        files: list[FileUpdate] = []
        for pick, cluster in zip(picks, clusters, strict=True):
            status, found = self._status(cluster, spec, relink=pick.relink)
            if (
                status is ImportStatus.REFUSED
                or status is ImportStatus.LINKED
                or (status is ImportStatus.RELINK and not pick.relink)
            ):
                problems += found
                continue
            provenance = Provenance(flavor, spec_version, _relinked_addons(cluster, spec))
            files.append(
                FileUpdate(
                    cluster.ref, with_header(cluster.content, provenance), pick.last_commit_id
                )
            )
        if problems:
            raise InvalidInputError(
                f"these clusters cannot be imported into flavor {flavor}", problems
            )
        catalog = await self._machine_configs.catalog()
        drifts = await asyncio.gather(*(self._drift.against(c, spec, catalog) for c in clusters))
        return await self._provisioner.link(
            ImportChange(
                spec_name=flavor,
                spec_version=spec_version,
                files=tuple(files),
                requested_by=user,
                summary=_summary(flavor, spec_version, clusters, drifts),
            )
        )

    @staticmethod
    def _status(
        cluster: ClusterFile, spec: ClusterSpec, *, relink: bool
    ) -> tuple[ImportStatus, list[str]]:
        name, flavor = cluster.ref.name, spec.metadata.name
        linked = cluster.provenance.spec_name
        try:
            with_header(cluster.content, Provenance(flavor, spec.metadata.version))
        except UneditableFileError as exc:
            return ImportStatus.REFUSED, [f"{name}: {exc}: {'; '.join(exc.problems)}"]
        if linked == flavor:
            return ImportStatus.LINKED, [
                f"{name}: already follows flavor {flavor} "
                f"v{cluster.provenance.spec_version or '?'}; sync it instead"
            ]
        if linked:
            if relink:
                return ImportStatus.RELINK, []
            return ImportStatus.RELINK, [
                f"{name}: follows flavor {linked} v{cluster.provenance.spec_version or '?'}; "
                f"send relink: true to link it to {flavor} instead"
            ]
        return ImportStatus.READY, []


def _require_picks(refs: Sequence[ClusterRef]) -> None:
    problems: list[str] = []
    if not refs:
        problems.append("clusters: pick at least one cluster")
    if len(refs) > MAX_IMPORT:
        problems.append(f"clusters: {len(refs)} picked; one import takes at most {MAX_IMPORT}")
    seen: set[ClusterRef] = set()
    for ref in refs:
        if ref in seen:
            problems.append(f"clusters: {ref.name} is picked twice")
        seen.add(ref)
    if problems:
        raise InvalidInputError("the clusters picked cannot be imported", problems)


def _summary(
    flavor: str,
    version: str,
    clusters: Sequence[ClusterFile],
    drifts: Sequence[ClusterDrift],
) -> str:
    lines = [
        f"Linking **{len(clusters)} cluster{'s' if len(clusters) != 1 else ''}** to flavor "
        f"`{flavor}` v{version}.",
        "",
        "Each file gains only the flavor header (`# specName`, `# specVersion`); nothing else "
        "in it changes. Nothing on a cluster changes when this merges: from then on each "
        "cluster follows the flavor, and what differs from it shows as drift, which a sync "
        "fixes.",
        "",
    ]
    for cluster, drift in zip(clusters, drifts, strict=True):
        where = f"`{cluster.ref.name}` ({cluster.ref.site}/{cluster.ref.mce})"
        before = cluster.provenance.spec_name
        relinked = (
            f", re-linked from flavor `{before}` v{cluster.provenance.spec_version or '?'}"
            if before
            else ""
        )
        values = len(drift.value_drift)
        addons = len(drift.addon_drift)
        facts = [f"{values} locked value{'s' if values != 1 else ''} differ"]
        decide = sum(1 for d in drift.value_drift if d.needs_decision)
        if decide:
            facts.append(f"{decide} need{'s' if decide == 1 else ''} a person to decide")
        facts.append(
            f"{addons} add-on{'s' if addons != 1 else ''} missing"
            if drift.error is None
            else "missing add-ons unknown"
        )
        lines.append(f"- {where}{relinked}: {', '.join(facts)}")
    return "\n".join(lines)
