"""Existing clusters joining a flavor (ADR-0037, ADR-0044).

A cluster Wingman did not create has no flavor link. Import writes the link
(the comment header Wingman writes at create, ADR-0012) into each picked
cluster file, one day1 merge request per cluster (ADR-0044), and changes
nothing else in it: the text edit keeps every other byte, the CI block
included (``wingman_day1.domain.cluster_text``). Each cluster's link is
reviewed, merged or rejected on its own; once merged the cluster follows the
flavor, and what differs shows as drift (ADR-0036); sync fixes it.

The preview compares each picked cluster with the flavor first. A cluster
already linked to another flavor is refused unless the request says to
re-link it; one already linked to this flavor has nothing to import. The
import checks every pick again before it opens anything: one refused or
moved pick, and no merge request opens.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_core.domain.errors import AmbiguousWriteError, GitError, GitUnavailableError
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.drift import ClusterDrift, DriftService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.changes import ClusterAction, ClusterChange
from wingman_day1.domain.cluster_file import Provenance
from wingman_day1.domain.cluster_text import with_header
from wingman_day1.domain.errors import InvalidInputError, StaleError, UneditableFileError
from wingman_day1.domain.locks import is_configs_lock
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec
from wingman_day1.domain.value_drift import show_value
from wingman_day1.ports import ClusterProvisioner

logger = logging.getLogger(__name__)

MAX_IMPORT: Final = 50
"""Clusters per import: one review screen, and at most this many merge requests."""
MAX_IMPORT_CONCURRENCY: Final = 8
"""Picks read and compared with the flavor at once."""
MAX_OPEN_CONCURRENCY: Final = 4
"""Import merge requests opened at once (ADR-0044).

Each is a commit and an MR, about a second on GitLab: fifty in a row can
outlast the proxy's 60 s, and a request cut while day1 goes on opening
invites a retry that opens each cluster's MR twice. Four at a time keeps a
full import near fifteen seconds without many writes on GitLab at once.
"""


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


@dataclass(frozen=True, slots=True)
class ImportedCluster:
    """A picked cluster whose import merge request opened."""

    cluster: ClusterRef
    merge_request: MergeRequest


@dataclass(frozen=True, slots=True)
class ImportFailure:
    """A picked cluster, checked like the others, whose merge request did not open.

    ``error`` is GitLab's answer. An ``AmbiguousWriteError`` means the MR may
    have opened: it is reported, never retried (ADR-0006). A cluster whose MR
    was not started, because GitLab did not answer for another one, has a
    ``GitUnavailableError`` saying so: nothing was sent for it.
    """

    cluster: ClusterRef
    error: GitError


@dataclass(frozen=True, slots=True)
class ImportResult:
    """One merge request per picked cluster: those opened and those not, each in pick order."""

    spec_name: str
    spec_version: str
    opened: tuple[ImportedCluster, ...]
    failed: tuple[ImportFailure, ...]


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
    ) -> ImportResult:
        """One day1 MR per picked cluster that links it to the flavor; none if any pick is refused.

        Every pick is checked before anything opens: the flavor's version, no
        file changed since the ``last_commit_id`` the preview showed (the
        commit it was read at, ADR-0035), and each cluster's status. Then each
        cluster's MR opens on its own. Its commit carries that
        ``last_commit_id``, so a file that moves in between fails only its own
        MR (ADR-0006); a failure is reported beside the MRs that opened, never
        retried.
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
        contents: list[str] = []
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
            contents.append(with_header(cluster.content, provenance))
        if problems:
            raise InvalidInputError(
                f"these clusters cannot be imported into flavor {flavor}", problems
            )
        catalog = await self._machine_configs.catalog()
        drifts = await asyncio.gather(*(self._drift.against(c, spec, catalog) for c in clusters))
        changes = [
            ClusterChange(
                ClusterAction.IMPORT,
                cluster.ref,
                user,
                _summary(flavor, spec_version, cluster, drift),
                content=content,
                last_commit_id=pick.last_commit_id,
                spec_name=flavor,
                spec_version=spec_version,
            )
            for pick, cluster, drift, content in zip(picks, clusters, drifts, contents, strict=True)
        ]
        outcomes = await self._open_each(changes, user=user)
        return ImportResult(
            flavor,
            spec_version,
            opened=tuple(o for o in outcomes if isinstance(o, ImportedCluster)),
            failed=tuple(o for o in outcomes if isinstance(o, ImportFailure)),
        )

    async def _open_each(
        self, changes: Sequence[ClusterChange], *, user: User
    ) -> list[ImportedCluster | ImportFailure]:
        """Each change's MR, a few at a time, in order; once GitLab does not answer, no more start.

        A cluster's failure is its own: a moved file or a refused write fails
        that MR and the others open. GitLab unreachable, or leaving a write
        unconfirmed, is different: the MRs not started yet would wait on it
        too, so they are not sent and say why.
        """
        limit = asyncio.Semaphore(MAX_OPEN_CONCURRENCY)
        unanswered: list[str] = []

        async def one(change: ClusterChange) -> ImportedCluster | ImportFailure:
            ref = change.cluster
            async with limit:
                if unanswered:
                    return ImportFailure(
                        ref,
                        GitUnavailableError(
                            f"not sent: GitLab did not answer for {unanswered[0]}, so no more "
                            "merge requests were started; import this cluster again"
                        ),
                    )
                try:
                    result = await self._provisioner.apply(change)
                except GitError as exc:
                    if isinstance(exc, GitUnavailableError | AmbiguousWriteError):
                        unanswered.append(ref.name)
                    event = {
                        "user": user.username,
                        "cluster": ref.name,
                        "spec": change.spec_name or "",
                        "error": type(exc).__name__,
                    }
                    logger.warning(
                        "import merge request not opened: %s: %s",
                        " ".join(f"{k}={v}" for k, v in event.items()),
                        exc,
                        extra={"event": "import_mr_not_opened", **event},
                    )
                    return ImportFailure(ref, exc)
            return ImportedCluster(ref, result.merge_request)

        return list(await asyncio.gather(*(one(change) for change in changes)))

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


def _summary(flavor: str, version: str, cluster: ClusterFile, drift: ClusterDrift) -> str:
    """One cluster's MR description: the link it gains, and what will show as its drift."""
    ref = cluster.ref
    before = cluster.provenance.spec_name
    relinked = (
        f" (it followed flavor `{before}` v{cluster.provenance.spec_version or '?'}; "
        "re-linked on request)"
        if before
        else ""
    )
    values = len(drift.value_drift)
    addons = len(drift.addon_drift)
    facts = [f"{values} locked value{'s differ' if values != 1 else ' differs'}"]
    decide = sum(1 for d in drift.value_drift if d.needs_decision)
    if decide:
        facts.append(f"{decide} need{'s' if decide == 1 else ''} a person to decide")
    facts.append(
        f"{addons} add-on{'s' if addons != 1 else ''} missing"
        if drift.error is None
        else "missing add-ons unknown"
    )
    lines = [
        f"Linking hosted cluster **{ref.name}** to flavor `{flavor}` v{version}{relinked}.",
        "",
        f"Site `{ref.site}`, MCE `{ref.mce}`.",
        "",
        "The file gains only the flavor header (`# specName`, `# specVersion`); nothing else "
        "in it changes. Nothing on the cluster changes when this merges: from then on it "
        "follows the flavor, and what differs from it shows as drift, which a sync fixes.",
        "",
        f"Once linked: {', '.join(facts)}.",
    ]
    for item in drift.value_drift:
        where = f"`{item.file_key}`"
        if item.nodepool is not None:
            where += f" (nodepool `{item.nodepool.name}`)"
        if item.needs_decision:
            lines.append(f"- {where}: needs a person: {item.needs_decision}")
        elif item.added or item.removed:
            parts = [f"adds {', '.join(f'`{n}`' for n in item.added)}"] if item.added else []
            if item.removed:
                parts.append(f"removes {', '.join(f'`{n}`' for n in item.removed)}")
            lines.append(f"- {where}: a sync {'; '.join(parts)}")
        else:
            lines.append(
                f"- {where}: the file has {show_value(item.cluster_value)}, "
                f"the flavor locks {show_value(item.flavor_value)}"
            )
    lines += [f"- add-on `{a.team}/{a.name}`: missing; day2 installs it" for a in drift.addon_drift]
    if drift.error is not None:
        lines.append(f"- add-ons: {drift.error}")
    return "\n".join(lines)
