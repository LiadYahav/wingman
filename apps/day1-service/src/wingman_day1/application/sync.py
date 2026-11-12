"""Sync one cluster to its flavor: one day1 MR that sets every drifted locked value (ADR-0037).

The MR edits the cluster file's text (``wingman_day1.domain.cluster_text``):
each locked value the file does not hold is set to the flavor's, machine
configs included, and the header's ``specVersion`` becomes the flavor's
current version. Nothing else changes: not the keys others own (``vlanId``,
``dhcp_values``, ``mcFiles``, ``mcConfigMap``), not the CI block, not the
comments. Presets are never synced.

Configs follow the flavor exactly (ADR-0029), so a sync can remove configs.
The preview lists each removal, the sync is refused unless the request
confirms exactly those removals, and the MR description names them and every
nodepool whose configs change: merging rolls those nodes, because that is how
OpenShift applies a MachineConfig (drained and rebooted in place, or replaced,
by the nodepool's ``upgradeType``). Drift that needs a
person (a nodepool without one network config, a position the file does not
have) is never guessed: a hardware type can be chosen in the request, the
rest blocks the sync with the reason.

Missing add-ons are not day1's to write (ADR-0016): the preview and the
result list them, and the web installs them through day2, as the drift fix
does (one MR per team, ``POST /api/day2/clusters/{id}/addons/bulk``).

When the update-nodepool workflow owns the NodePool files, a sync of their
fields must go through it: one writer per file (architecture rule 4). The
``ClusterProvisioner`` port is where that switch happens.
"""

from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.drift import DriftService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.domain.addons import AddonDrift, VersionDifference
from wingman_day1.domain.changes import ClusterAction, ClusterChange, ProvisionResult
from wingman_day1.domain.cluster_file import AUTOMATION_KEYS, Provenance, edit_problems
from wingman_day1.domain.cluster_text import (
    Edit,
    SetConfigs,
    SetValue,
    edit_values,
    values_or_refuse,
    with_header,
)
from wingman_day1.domain.errors import InvalidInputError, StaleError, UneditableFileError
from wingman_day1.domain.machine_configs import MachineConfigCatalog, network_choice_problems
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec
from wingman_day1.domain.value_drift import (
    NodepoolRef,
    ValueDrift,
    file_nodepools,
    show_value,
    value_drift,
)
from wingman_day1.ports import ClusterProvisioner


@dataclass(frozen=True, slots=True)
class Removal:
    """A config a sync removes from a nodepool."""

    nodepool: NodepoolRef
    name: str


@dataclass(frozen=True, slots=True)
class Rebooting:
    """A nodepool whose configs a sync changes: merging rolls its nodes.

    How is the nodepool's own ``upgradeType`` (the chart's default is
    ``InPlace``: each node is drained and rebooted, ``inPlace.maxUnavailable``
    at a time, one when unset); ``Replace`` provisions new nodes instead.
    """

    nodepool: NodepoolRef
    replicas: int | None
    upgrade_type: str | None = None
    """The file's ``upgradeType``; ``None`` when unset (the chart's ``InPlace``)."""
    max_unavailable: int | str | None = None
    """The file's ``inPlace.maxUnavailable``; ``None`` when unset (one node at a time)."""

    @property
    def replaces_nodes(self) -> bool:
        """``upgradeType: Replace``: new nodes are provisioned and the old ones removed."""
        return self.upgrade_type == "Replace"


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """What syncing a cluster to its flavor would change, or why it cannot yet."""

    cluster: ClusterFile
    spec: ClusterSpec
    changes: tuple[ValueDrift, ...]
    """Every locked value the file does not hold (with the request's hardware choices)."""
    content: str
    """The file as the sync would write it (the current text when nothing can change)."""
    removals: tuple[Removal, ...]
    rebooting: tuple[Rebooting, ...]
    problems: tuple[str, ...]
    """Why the sync cannot run now: decisions a person must make, a layout Wingman cannot edit."""
    warnings: tuple[str, ...]
    addons_to_install: tuple[AddonDrift, ...]
    version_differences: tuple[VersionDifference, ...]
    addons_error: str | None
    """Set when day2 did not answer, so missing add-ons are unknown."""

    @property
    def changes_file(self) -> bool:
        """Whether the sync writes anything."""
        return self.content != self.cluster.content

    @property
    def diff(self) -> str:
        """The file change as a unified diff."""
        path = str(self.cluster.ref.path)
        return "".join(
            difflib.unified_diff(
                self.cluster.content.splitlines(keepends=True),
                self.content.splitlines(keepends=True),
                f"a/{path}",
                f"b/{path}",
            )
        )


@dataclass(frozen=True, slots=True)
class SyncResult:
    """The MR a sync opened, and what day2 still has to install."""

    provision: ProvisionResult
    plan: SyncPlan


def sync_edits(drift: Sequence[ValueDrift]) -> list[Edit]:
    """The text edits that set every drifted value that needs no decision."""
    edits: list[Edit] = []
    for item in drift:
        if item.needs_decision is not None:
            continue
        if item.is_configs and item.nodepool is not None:
            entries = cast("Sequence[Mapping[str, str]]", item.flavor_value)
            edits.append(SetConfigs(item.nodepool.index, tuple(e["name"] for e in entries)))
        else:
            edits.append(SetValue(item.file_key, item.flavor_value))
    return edits


def _hardware_problems(
    choices: Mapping[int, str],
    drift: Sequence[ValueDrift],
    catalog: MachineConfigCatalog,
    *,
    cluster_name: str,
) -> list[str]:
    deciding = {d.nodepool.index for d in drift if d.needs_hardware and d.nodepool is not None}
    problems: list[str] = []
    for index, hardware in sorted(choices.items()):
        where = f"hardware: nodepool[{index}]"
        if index not in deciding:
            problems.append(f"{where} needs no hardware choice; its own network config is used")
            continue
        problems += network_choice_problems(where, hardware, catalog, cluster_name=cluster_name)
    return problems


class SyncService:
    """Preview and propose syncing one cluster to its flavor."""

    def __init__(
        self,
        clusters: ClusterService,
        specs: SpecCatalog,
        drift: DriftService,
        machine_configs: MachineConfigService,
        provisioner: ClusterProvisioner,
    ) -> None:
        """Read the cluster, its flavor and the catalogue; propose through ``provisioner``."""
        self._clusters = clusters
        self._specs = specs
        self._drift = drift
        self._machine_configs = machine_configs
        self._provisioner = provisioner

    async def preview(self, ref: ClusterRef, *, hardware: Mapping[int, str]) -> SyncPlan:
        """What a sync would write, the removals and reboots it means, and what blocks it."""
        cluster = await self._clusters.get(ref)
        name = cluster.provenance.spec_name
        if not name:
            raise InvalidInputError(
                f"cluster {ref.name!r} follows no flavor",
                [f"{ref.name}: import it into a flavor first (POST /specs/<flavor>/import)"],
            )
        spec = await self._specs.get(name)
        catalog = await self._machine_configs.catalog()
        try:
            values = values_or_refuse(cluster.content)
        except UneditableFileError as exc:
            raise InvalidInputError(str(exc), exc.problems) from exc
        cluster_name = cluster.hosted_cluster.cluster_name
        plain = value_drift(spec.locks(), values, cluster_name=cluster_name, catalog=catalog)
        choice_problems = _hardware_problems(hardware, plain, catalog, cluster_name=cluster_name)
        if choice_problems:
            raise InvalidInputError(
                f"the hardware chosen for {ref.name} is not usable", choice_problems
            )
        changes = value_drift(
            spec.locks(), values, cluster_name=cluster_name, catalog=catalog, hardware=hardware
        )
        problems = [f"{d.file_key}: {d.needs_decision}" for d in changes if d.needs_decision]
        content = cluster.content
        try:
            content = with_header(
                edit_values(cluster.content, sync_edits(changes)),
                Provenance(name, spec.metadata.version, cluster.provenance.requested_addons),
            )
        except UneditableFileError as exc:
            problems += [f"{exc}: {problem}" for problem in exc.problems]
            content = cluster.content
        before = set(edit_problems(cluster.content, cluster.content))
        problems += [p for p in edit_problems(cluster.content, content) if p not in before]
        addons = await self._drift.against(cluster, spec, catalog)
        decided = [d for d in changes if d.needs_decision is None]
        return SyncPlan(
            cluster=cluster,
            spec=spec,
            changes=changes,
            content=content,
            removals=tuple(
                Removal(d.nodepool, removed)
                for d in decided
                if d.nodepool is not None
                for removed in d.removed
            ),
            rebooting=tuple(
                _rebooting(values, d.nodepool)
                for d in decided
                if d.is_configs and d.nodepool is not None and (d.added or d.removed)
            ),
            problems=tuple(problems),
            warnings=tuple(_mc_files_warnings(values, decided)),
            addons_to_install=addons.addon_drift,
            version_differences=addons.version_differences,
            addons_error=addons.error,
        )

    async def sync(
        self,
        ref: ClusterRef,
        *,
        last_commit_id: str,
        spec_version: str,
        hardware: Mapping[int, str],
        confirm_removals: Sequence[tuple[int, str]],
        user: User,
    ) -> SyncResult:
        """Open the sync MR, guarded by the commit and the flavor version the preview showed.

        ``last_commit_id`` is the commit the preview read the repo at (ADR-0035):
        the sync goes ahead if the file did not change since, and the write
        carries it, so GitLab refuses a file that moves before the commit.
        """
        plan = await self.preview(ref, hardware=hardware)
        cluster, spec = plan.cluster, plan.spec
        if await self._clusters.changed_since(ref, last_commit_id):
            raise StaleError(
                f"cluster {ref.name!r} changed since the preview ({last_commit_id[:8]} → "
                f"{cluster.last_commit_id[:8]}); preview the sync again"
            )
        if spec.metadata.version != spec_version:
            raise StaleError(
                f"flavor {spec.metadata.name} is now v{spec.metadata.version}, not "
                f"v{spec_version}; preview the sync again"
            )
        if plan.problems:
            raise InvalidInputError(f"cluster {ref.name!r} cannot be synced yet", plan.problems)
        if not plan.changes_file:
            raise InvalidInputError(
                f"cluster {ref.name!r} already holds every value flavor "
                f"{spec.metadata.name} v{spec_version} locks",
                ["nothing to change in the cluster file; install missing add-ons through day2"],
            )
        unconfirmed = _confirmation_problems(plan.removals, confirm_removals)
        if unconfirmed:
            raise InvalidInputError(
                "the sync removes configs the request does not confirm", unconfirmed
            )
        result = await self._provisioner.apply(
            ClusterChange(
                action=ClusterAction.SYNC,
                cluster=ref,
                requested_by=user,
                summary=_summary(plan),
                content=plan.content,
                last_commit_id=last_commit_id,
                spec_name=spec.metadata.name,
                spec_version=spec.metadata.version,
            )
        )
        return SyncResult(result, plan)


def _rebooting(values: Mapping[str, object], nodepool: NodepoolRef) -> Rebooting:
    pool = file_nodepools(values)[nodepool.index]
    found = cast("Mapping[str, object]", pool) if isinstance(pool, Mapping) else {}
    replicas = found.get("replicas")
    upgrade = found.get("upgradeType")
    in_place = found.get("inPlace")
    limit = (
        cast("Mapping[str, object]", in_place).get("maxUnavailable")
        if isinstance(in_place, Mapping)
        else None
    )
    return Rebooting(
        nodepool,
        replicas if isinstance(replicas, int) and not isinstance(replicas, bool) else None,
        upgrade if isinstance(upgrade, str) else None,
        limit if isinstance(limit, int | str) and not isinstance(limit, bool) else None,
    )


def _mc_files_warnings(values: Mapping[str, object], drift: Sequence[ValueDrift]) -> list[str]:
    """A file with an explicit ``mcFiles`` renders only what it names (the CI's rule)."""
    listed = values.get("mcFiles")
    if not isinstance(listed, list):
        return []
    named = {str(n) for n in cast("Sequence[object]", listed)}
    added = sorted({name for d in drift for name in d.added if name not in named})
    if not added:
        return []
    return [
        f"this file lists mcFiles, so the CI renders only the configs it names, and "
        f"{', '.join(added)} {'is' if len(added) == 1 else 'are'} not among them; Wingman never "
        "writes mcFiles (ADR-0012): check that the CI adds them on the MR branch before merging"
    ]


def _confirmation_problems(
    planned: Sequence[Removal], confirmed: Sequence[tuple[int, str]]
) -> list[str]:
    want = Counter((r.nodepool.index, r.name) for r in planned)
    got = Counter(confirmed)
    problems = [
        f"nodepool[{index}].configs: the sync removes {name}; confirm it in confirm_removals"
        for (index, name), count in sorted(want.items())
        if got[(index, name)] < count
    ]
    problems += [
        f"nodepool[{index}].configs: confirm_removals names {name}, which the sync does not remove"
        for (index, name), count in sorted(got.items())
        if want[(index, name)] < count
    ]
    return problems


def _summary(plan: SyncPlan) -> str:
    cluster, spec = plan.cluster, plan.spec
    ref = cluster.ref
    before = cluster.provenance.spec_version or "?"
    lines = [
        f"Syncing hosted cluster **{ref.name}** to flavor `{spec.metadata.name}` "
        f"v{spec.metadata.version} (the file followed v{before}).",
        "",
        f"Site `{ref.site}`, MCE `{ref.mce}`.",
        "",
        "Every value the flavor locks and the file did not hold is set to the flavor's:",
    ]
    for change in plan.changes:
        where = f"`{change.file_key}`"
        if change.nodepool is not None:
            where += f" (nodepool `{change.nodepool.name}`)"
        if change.is_configs:
            parts = [f"add {', '.join(f'`{n}`' for n in change.added)}"] if change.added else []
            if change.removed:
                parts.append(f"**remove** {', '.join(f'`{n}`' for n in change.removed)}")
            lines.append(f"- {where}: {'; '.join(parts)}")
        else:
            was, now = show_value(change.cluster_value), show_value(change.flavor_value)
            lines.append(f"- {where}: {was} → {now}")
    if not plan.changes:
        lines.append("- none; only the header's flavor version changes")
    if before != spec.metadata.version:
        lines.append(f"- header: `specVersion` {before} → {spec.metadata.version}")
    if plan.removals:
        removed = "; ".join(f"`{r.name}` from nodepool `{r.nodepool.name}`" for r in plan.removals)
        lines += [
            "",
            f"**This removes machine configs:** {removed}. The flavor fixes each nodepool's "
            "configs to exactly its list.",
        ]
    if plan.rebooting:
        lines += [
            "",
            "**Merging rolls nodes.** The machine configs of these nodepools change, and "
            "OpenShift applies a MachineConfig change to every node of the nodepool:",
            *(f"- `{r.nodepool.name}`{_nodes(r.replicas)}: {_how(r)}" for r in plan.rebooting),
            "",
            "Merge in a window the cluster's owners accept.",
        ]
    if plan.warnings:
        lines += ["", *(f"**Check:** {w}" for w in plan.warnings)]
    if plan.addons_to_install:
        names = ", ".join(f"`{a.team}/{a.name}`" for a in plan.addons_to_install)
        lines += [
            "",
            f"Missing add-ons are not part of this MR; install them through day2: {names}.",
        ]
    keys = ", ".join(f"`{k}`" for k in AUTOMATION_KEYS)
    lines += [
        "",
        f"Not changed: {keys}, the `# === Added by CI ===` block, comments, and every value "
        "the flavor does not lock.",
    ]
    return "\n".join(lines)


def _nodes(replicas: int | None) -> str:
    if replicas is None:
        return ""
    return f" ({replicas} node{'s' if replicas != 1 else ''})"


def _how(rebooting: Rebooting) -> str:
    if rebooting.replaces_nodes:
        return "replaced (`upgradeType: Replace`): new nodes are provisioned, then the old removed"
    at_a_time = (
        "one node at a time"
        if rebooting.max_unavailable is None
        else f"`inPlace.maxUnavailable: {rebooting.max_unavailable}` at a time"
    )
    return f"drained and rebooted in place, {at_a_time}"
