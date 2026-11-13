"""Install, update and remove: one MR on the team's repo per change (ADR-0022).

What Wingman writes:

- **install**: ``<cluster folder>/<chart>/values.yaml``, and ``<chart>.yaml``
  only when needed (a ``repourl`` the team default lacks, a namespace, or an
  explicitly requested emergency pin). Never a per-cluster ``targetRevision``
  by default: that detaches the cluster from fleet and OCP-version upgrades.
  Refused when the chart is a fleet default there (XOR rule).
- **update**: the values file, guarded by the ``last_commit_id`` the caller
  read; the pin only when asked. A fleet default is tweaked through
  ``defaults/<scope>/<chart>/values-<cluster>.yaml``.
- **remove**: every file of the chart folder. ArgoCD then deletes the wrapper
  Application but orphans the workload: it keeps running. If the folder was
  the cluster's last, a ``.gitkeep`` keeps the cluster registered so the
  team's fleet defaults on it are not orphaned too.
- **deploy on specific MCEs** (ADR-0053's amendment): the install above on
  each chosen MCE hub's own ``in-cluster/<chart>/``, one MR per MCE, opened a
  few at a time; each MCE is checked, refused or failed on its own, and
  nothing is retried. An add-on that is an MCE default is refused (XOR).

Before any MR, the team repo as it would be after the change is linted with
the platform's rules; a change that adds an error is refused. Nothing is
synced: leaf apps are manual-sync and Wingman has no ArgoCD access yet.
Every write is refused first for a team that has not given Wingman write
access to its project (ADR-0043).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from wingman_core.domain.errors import (
    AmbiguousWriteError,
    GitError,
    GitUnavailableError,
    RevisionConflictError,
)
from wingman_core.domain.git import FileChange, FileContent, RepoPath, commit_author
from wingman_core.domain.merge_request import MergeRequest, NewMergeRequest
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    MRMetadata,
    Repo,
    ResourceType,
    Verb,
    branch_name,
    mr_description,
    mr_title,
)
from wingman_core.domain.users import User
from wingman_core.ports.clock import Clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.application.access import AccessService
from wingman_day2.application.apps import LoadedLayer, deploy_of, load_deploy, load_layers
from wingman_day2.application.installed import override_layer
from wingman_day2.application.preview import find_app, team_version
from wingman_day2.application.topology import ClusterSummary, TeamState, Topology, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind, ClusterRef
from wingman_day2.domain.deploy_config import (
    PROJECT_NAMESPACE,
    REPOURL,
    TARGET_REVISION,
    LeafApplication,
)
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartAlreadyInstalledError,
    ChartNotInstalledError,
    Day2Error,
    UnknownChartError,
    UnknownTeamError,
)
from wingman_day2.domain.findings import Finding, Rule, Severity, warning
from wingman_day2.domain.lints import lint_team
from wingman_day2.domain.platform import (
    AppSource,
    PlannedApp,
    TeamPlan,
    plan_team,
    scope_exclusions,
)
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.teams import Team
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.yaml_values import dump_values, parse_values
from wingman_day2.ports import SigsRepository

logger = logging.getLogger(__name__)

MAX_INSTALL_CONCURRENCY: Final = 4
"""How many of a deploy-on-MCEs' merge requests are opened at once."""

CHART_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
"""A chart folder becomes part of Application names, so it must be a DNS label."""

_PENDING = "(this change)"


@dataclass(frozen=True, slots=True)
class InstallSpec:
    """One chart to install. ``version`` other than the inherited one needs ``emergency_pin``."""

    team: str
    chart: str
    values: Mapping[str, object] = field(default_factory=dict)
    version: str | None = None
    emergency_pin: bool = False
    repourl: str | None = None
    project_namespace: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeResult:
    """An opened MR and what it does."""

    team: str
    cluster: ClusterSummary
    merge_request: MergeRequest
    changes: tuple[FileChange, ...]
    app_names: tuple[str, ...]
    findings: tuple[Finding, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BulkResult:
    """One MR per team; ``failed`` holds the teams whose MR could not be opened."""

    results: tuple[ChangeResult, ...]
    failed: tuple[tuple[str, GitError], ...]


@dataclass(frozen=True, slots=True)
class MceInstall:
    """One chosen MCE of a deploy on specific MCEs: its plan, its MR, or why not."""

    cluster: ClusterRef
    changes: tuple[FileChange, ...] = ()
    notes: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    refused: Day2Error | None = None
    result: ChangeResult | None = None
    failed: GitError | None = None

    @property
    def status(self) -> str:
        """``refused``, ``failed``, ``opened`` or (a dry run) ``planned``."""
        if self.refused is not None:
            return "refused"
        if self.failed is not None:
            return "failed"
        return "opened" if self.result is not None else "planned"


@dataclass(frozen=True, slots=True)
class MceInstalls:
    """A deploy on specific MCEs: one entry per chosen MCE, in the order asked."""

    team: str
    chart: str
    installs: tuple[MceInstall, ...]


@dataclass(slots=True)
class _Plan:
    state: TeamState
    summary: ClusterSummary
    charts: list[str] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)
    leaves: list[LeafApplication] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def tree(self) -> RepoTree:
        return self.state.repo.tree.with_changes(self.changes)


def check_chart_name(chart: str) -> str:
    """``chart`` if it can be a chart folder, else a refusal."""
    if not CHART_NAME.match(chart):
        raise ChangeRefusedError(
            f"{chart!r} is not a valid chart name (lowercase letters, digits and '-')",
            details={"rule": "chart-name", "chart": chart},
        )
    return chart


def require_writable(topology: Topology, summary: ClusterSummary) -> None:
    """Refuse a destination the platform would not render, or could render only as a phantom."""
    ref = summary.ref
    if ref.kind is ClusterKind.HUB:
        return
    if not ref.env:
        raise ChangeRefusedError(
            f"{ref.name}'s env is unknown; place it in a team repo first",
            details={"rule": str(Rule.ENV_UNKNOWN), "cluster": ref.id},
        )
    if not ref.env_allowed:
        raise ChangeRefusedError(
            f"{ref.id}: env {ref.env!r} is not one the platform accepts",
            details={"rule": str(Rule.ENV_NOT_ALLOWED), "cluster": ref.id},
        )
    if ref.kind is ClusterKind.UPI:
        return
    mce = topology.day1.mce(ref.site, ref.mce)
    hosted = topology.day1.hosted_cluster(ref.site, ref.mce, ref.name)
    if mce is None or mce.ocp_version is None:
        missing = layout.day1_mce_version_file(ref.site, ref.mce)
    elif ref.kind is ClusterKind.HOSTED and (hosted is None or hosted.ocp_version is None):
        missing = layout.day1_hosted_cluster_file(ref.site, ref.mce, ref.name)
    else:
        return
    raise ChangeRefusedError(
        f"day1 has no mastertag at {missing}: the platform renders nothing for {ref.name}, and a "
        "folder for it would be a phantom",
        details={"rule": str(Rule.DAY1_VERSION_MISSING), "cluster": ref.id, "path": str(missing)},
    )


def refuse_new_errors(
    topology: Topology, state: TeamState, changes: Sequence[FileChange]
) -> TeamPlan:
    """What the repo after ``changes`` generates, or the refusal of the errors it adds (ADR-0023).

    Errors the team repo already has do not block a change; only new ones do. The control
    files (``exclusions.yaml``, UPI ``version.yaml``) are read as the change leaves them.
    """
    before = {(f.rule, f.path, f.message) for f in state.findings if f.severity is Severity.ERROR}
    repo = state.repo.with_changes(changes)
    after_plan = plan_team(repo, topology.day1)
    added = [
        f
        for f in lint_team(repo, topology.day1, after_plan)
        if f.severity is Severity.ERROR and (f.rule, f.path, f.message) not in before
    ]
    if added:
        raise ChangeRefusedError(
            f"the change would break the platform's rules: {added[0].message}",
            details={"rule": str(added[0].rule), "findings": [f.message for f in added]},
        )
    return after_plan


def _pending(path: RepoPath, values: Mapping[str, object], role: LayerRole) -> LoadedLayer:
    return LoadedLayer(
        Layer(role, path), FileContent(path, _PENDING, dump_values(values), ""), dict(values)
    )


def _sync_note(leaf: LeafApplication) -> str:
    if leaf.auto_sync:
        return (
            f"{leaf.name} on {leaf.argo}'s ArgoCD syncs automatically (its syncPolicy is "
            "automated) once the MR is merged."
        )
    return (
        f"After the merge, ArgoCD on {leaf.argo} generates {leaf.name}, which is manual-sync: "
        "nothing is deployed until someone syncs it. Wingman has no ArgoCD access yet."
    )


class ChangeService:
    """Open the MRs that install, update and remove charts."""

    def __init__(
        self,
        gitlab: GitLabPort,
        topology: TopologyService,
        sigs: SigsRepository,
        access: AccessService,
        clock: Clock,
    ) -> None:
        """Write through ``gitlab``; read through ``topology`` and ``sigs``; check ``access``."""
        self._gitlab = gitlab
        self._topology = topology
        self._sigs = sigs
        self._access = access
        self._clock = clock

    # ── install ─────────────────────────────────────────────────────────────

    async def _plan_install(self, plan: _Plan, spec: InstallSpec) -> None:
        """Add one chart's files to ``plan``, or raise why it cannot be installed."""
        state, ref = plan.state, plan.summary.ref
        tree = plan.tree
        chart = check_chart_name(spec.chart)
        folder = layout.chart_dir(ref, chart)
        if tree.is_dir(folder):
            raise ChartAlreadyInstalledError(
                f"{folder}/ exists already in {state.team.name}; update it instead",
                details={"rule": "installed", "team": state.team.name, "path": str(folder)},
            )
        if not tree.is_dir(layout.operators_dir(chart)) and not spec.repourl:
            raise UnknownChartError(
                f"{state.team.name} has no operators/{chart}/; give a repourl to install a chart "
                "that has no Sig values",
                details={"team": state.team.name, "chart": chart},
            )
        self._check_xor(state, ref, chart, tree)
        app = PlannedApp(
            state.team.name, ref, chart, AppSource.CLUSTER, team_version(state, plan.summary)
        )
        inherited_layers = await load_layers(
            self._sigs, state.team, tree, app.deploy_config_layers[:-1]
        )
        inherited = deploy_of(app, inherited_layers, tree).leaf
        overrides = self._install_overrides(app, inherited, spec, plan)
        own = app.deploy_config_layers[-1].path
        new_layers = [*inherited_layers]
        if overrides:
            plan.changes.append(FileChange.create(own, dump_values(overrides)))
            new_layers.append(_pending(own, overrides, LayerRole.CLUSTER))
        plan.changes.append(
            FileChange.create(folder.child(layout.VALUES_FILE), dump_values(spec.values))
        )
        leaf = deploy_of(app, tuple(new_layers), tree).leaf
        plan.charts.append(chart)
        plan.leaves.append(leaf)

    @staticmethod
    def _check_xor(state: TeamState, ref: ClusterRef, chart: str, tree: RepoTree) -> None:
        if ref.kind is ClusterKind.HUB:
            return
        fleet = layout.defaults_dir(ref.defaults_scope).child(chart)
        if not tree.is_dir(fleet):
            return
        exclusions = scope_exclusions(state.repo, ref.defaults_scope)
        if exclusions is not None and chart in exclusions.excluded_charts(ref.exclusion_key or ""):
            return
        tweak = fleet.child(f"values-{ref.exclusion_key}.yaml")
        raise ChartAlreadyInstalledError(
            f"{chart} is a fleet default of {state.team.name} ({fleet}/), so it is deployed to "
            f"{ref.name} already; a chart folder for it would generate the same app twice (the "
            f"XOR rule). Its values for this cluster go in {tweak}.",
            details={
                "rule": "xor",
                "team": state.team.name,
                "fleet_default": str(fleet),
                "tweak": str(tweak),
            },
        )

    @staticmethod
    def _install_overrides(
        app: PlannedApp, inherited: LeafApplication, spec: InstallSpec, plan: _Plan
    ) -> dict[str, object]:
        """The deploy-config keys the cluster folder must set; empty when it needs no file."""
        overrides: dict[str, object] = {}
        if spec.repourl and spec.repourl != inherited.repo_url:
            overrides[REPOURL] = spec.repourl
        elif not inherited.repo_url:
            raise ChangeRefusedError(
                f"no layer of {app.chart}'s deploy config sets a lowercase repourl (check "
                f"operators/{app.chart}/{app.chart}.yaml for `repoUrl`), so the app would render "
                "with an empty repoURL; give repourl to set it for this cluster",
                details={"rule": str(Rule.REPOURL_MISSING), "chart": app.chart},
            )
        if spec.project_namespace and spec.project_namespace != (
            inherited.destination_namespace or ""
        ):
            overrides[PROJECT_NAMESPACE] = spec.project_namespace
        if spec.version and spec.version != inherited.target_revision:
            if not spec.emergency_pin:
                raise ChangeRefusedError(
                    f"{app.ref.name} would get {app.chart} at {inherited.target_revision} (its "
                    f"Sig values or their OCP-version pin). Writing {spec.version} into the "
                    "cluster folder is an emergency pin that detaches it from every future "
                    "upgrade; ask for it explicitly with emergency_pin, or change the pin in "
                    f"operators/{app.chart}/",
                    details={
                        "rule": "emergency-pin-required",
                        "inherited": inherited.target_revision,
                        "requested": spec.version,
                    },
                )
            overrides[TARGET_REVISION] = spec.version
            plan.findings.append(
                warning(
                    Rule.EMERGENCY_PIN,
                    f"pins {app.chart} to {spec.version} on {app.ref.name} only: an emergency pin; "
                    "remove it once the add-on's own version or an ocp-versions/ pin catches up",
                    team=app.team,
                    cluster=app.ref.id,
                    chart=app.chart,
                )
            )
        return overrides

    async def install(
        self,
        key: str,
        spec: InstallSpec,
        user: User,
        *,
        mce: str | None = None,
        message: str | None = None,
    ) -> ChangeResult:
        """Open an MR installing ``spec`` on cluster ``key``."""
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        state = topology.team(spec.team)
        await self._access.require_write(state.team)
        require_writable(topology, summary)
        plan = _Plan(state, summary)
        await self._plan_install(plan, spec)
        self._validate(topology, plan)
        return await self._open(plan, user, Verb.INSTALL, message)

    async def bulk_install(
        self,
        key: str,
        specs: Sequence[InstallSpec],
        user: User,
        *,
        mce: str | None = None,
        message: str | None = None,
    ) -> BulkResult:
        """Install several charts on one cluster: one MR per team, all validated first."""
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        for team in dict.fromkeys(spec.team for spec in specs):
            try:
                state = topology.team(team)
            except UnknownTeamError:
                continue  # listed with the other problems below
            await self._access.require_write(state.team)
        require_writable(topology, summary)
        plans: dict[str, _Plan] = {}
        problems: list[dict[str, object]] = []
        for spec in specs:
            plan = plans.get(spec.team)
            try:
                if plan is None:
                    plan = plans[spec.team] = _Plan(topology.team(spec.team), summary)
                await self._plan_install(plan, spec)
            except Day2Error as exc:
                problems.append(
                    {"team": spec.team, "chart": spec.chart, "detail": exc.detail, **exc.details}
                )
        for plan in plans.values():
            try:
                self._validate(topology, plan)
            except ChangeRefusedError as exc:
                problems.append({"team": plan.state.team.name, "detail": exc.detail, **exc.details})
        if problems:
            raise ChangeRefusedError(
                f"{len(problems)} of the requested charts cannot be installed; nothing was opened",
                details={"rule": "bulk", "problems": problems},
            )
        results: list[ChangeResult] = []
        failed: list[tuple[str, GitError]] = []
        for plan in plans.values():
            try:
                results.append(await self._open(plan, user, Verb.INSTALL, message))
            except GitError as exc:
                failed.append((plan.state.team.name, exc))
        if failed and not results:
            raise failed[0][1]
        return BulkResult(tuple(results), tuple(failed))

    async def install_on_mces(  # noqa: C901 - baseline: plan, check and open per MCE
        self,
        team: str,
        chart: str,
        clusters: Sequence[str],
        user: User,
        *,
        values: Mapping[str, object] | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> MceInstalls:
        """Install ``chart`` in each chosen MCE hub's own folder: one MR per MCE.

        Each MCE is planned and checked on its own (an MCE default of the chart
        is refused, the XOR rule; so is one with the chart in its folder
        already, or one the platform renders nothing for). The rest are opened
        a few at a time; a write that fails fails that MCE only, and once
        GitLab does not answer, no more are started. Nothing is retried.
        """
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        chart = check_chart_name(chart)
        if not state.repo.tree.is_dir(layout.operators_dir(chart)):
            raise UnknownChartError(
                f"team {team} has no operators/{chart}/ to install",
                details={"team": team, "chart": chart},
            )
        keys = list(dict.fromkeys(clusters))
        if not keys:
            raise ChangeRefusedError("choose at least one MCE", details={"rule": "no-mce"})
        planned: list[tuple[MceInstall, _Plan | None]] = []
        for key in keys:
            try:
                ref = ClusterRef.parse(key)
            except Day2Error as exc:
                raise ChangeRefusedError(
                    f"{key!r} is not an MCE id (mce:<site>:<env>:<mce>)",
                    details={"rule": "not-an-mce", "cluster": key},
                ) from exc
            if ref.kind is not ClusterKind.MCE:
                raise ChangeRefusedError(
                    f"{key} is not an MCE: deploy on specific MCEs installs on MCE hubs only",
                    details={"rule": "not-an-mce", "cluster": key},
                )
            try:
                summary = topology.cluster(ref)
                require_writable(topology, summary)
                plan = _Plan(state, summary)
                await self._plan_install(plan, InstallSpec(team, chart, values=dict(values or {})))
                self._validate(topology, plan)
            except Day2Error as exc:
                planned.append((MceInstall(ref, refused=exc), None))
                continue
            notes = (*plan.notes, *(_sync_note(leaf) for leaf in plan.leaves))
            install = MceInstall(ref, tuple(plan.changes), notes, tuple(plan.findings))
            planned.append((install, plan))
        if dry_run:
            return MceInstalls(team, chart, tuple(i for i, _ in planned))
        limit = asyncio.Semaphore(MAX_INSTALL_CONCURRENCY)
        unanswered: list[str] = []

        async def one(install: MceInstall, plan: _Plan | None) -> MceInstall:
            if plan is None:
                return install
            async with limit:
                if unanswered:
                    return MceInstall(
                        install.cluster,
                        install.changes,
                        install.notes,
                        install.findings,
                        failed=GitUnavailableError(
                            f"not sent: GitLab did not answer for {unanswered[0]}, so no more "
                            "merge requests were started; deploy on this MCE again"
                        ),
                    )
                try:
                    result = await self._open(plan, user, Verb.INSTALL, message)
                except GitError as exc:
                    if isinstance(exc, GitUnavailableError | AmbiguousWriteError):
                        unanswered.append(install.cluster.name)
                    logger.warning(
                        "install merge request not opened: user=%s team=%s chart=%s cluster=%s "
                        "error=%s",
                        user.username,
                        team,
                        chart,
                        install.cluster.id,
                        type(exc).__name__,
                        extra={"event": "mce_install_not_opened"},
                    )
                    return MceInstall(
                        install.cluster,
                        install.changes,
                        install.notes,
                        install.findings,
                        failed=exc,
                    )
            return MceInstall(
                install.cluster, install.changes, install.notes, install.findings, result=result
            )

        done = await asyncio.gather(*(one(i, p) for i, p in planned))
        return MceInstalls(team, chart, tuple(done))

    # ── update ──────────────────────────────────────────────────────────────

    async def update(
        self,
        key: str,
        team: str,
        chart: str,
        values: Mapping[str, object],
        user: User,
        *,
        version: str | None = None,
        emergency_pin: bool = False,
        last_commit_id: str | None = None,
        mce: str | None = None,
        message: str | None = None,
    ) -> ChangeResult:
        """Open an MR changing the chart's values on the cluster (and its pin, when asked).

        ``last_commit_id`` is the commit the caller read the values file at;
        if the file changed since, the commit is refused (409) instead of
        overwriting the other change (ADR-0006).
        """
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        state = topology.team(team)
        await self._access.require_write(state.team)
        app = self._installed(state, summary, chart)
        plan = _Plan(state, summary, charts=[chart])
        await self._plan_values(plan, app, values, last_commit_id)
        deploy = await load_deploy(self._sigs, state.team, state.repo.tree, app)
        if version is not None:
            self._plan_pin(plan, app, deploy.layers, version, emergency_pin=emergency_pin)
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {chart} on {summary.ref.name} already has these values",
                details={"rule": "no-change"},
            )
        plan.leaves.append(deploy.leaf)
        self._validate(topology, plan)
        return await self._open(plan, user, Verb.UPDATE, message)

    @staticmethod
    def _installed(state: TeamState, summary: ClusterSummary, chart: str) -> PlannedApp:
        app = find_app(state, summary, chart)
        if app is None:
            raise ChartNotInstalledError(
                f"{state.team.name} does not deploy {chart} to {summary.ref.name}",
                details={"team": state.team.name, "chart": chart, "cluster": summary.ref.id},
            )
        return app

    async def _plan_values(
        self,
        plan: _Plan,
        app: PlannedApp,
        values: Mapping[str, object],
        last_commit_id: str | None,
    ) -> None:
        path = override_layer(app).path
        current = await self._sigs.read(plan.state.team, path)
        content = dump_values(values)
        if current is None:
            if last_commit_id:
                raise RevisionConflictError(f"{path} was deleted since {last_commit_id[:8]}")
            if values or app.source is AppSource.CLUSTER:
                plan.changes.append(FileChange.create(path, content))
            return
        guard = last_commit_id or current.last_commit_id
        existing, problem = parse_values(current.content, path=str(path))
        if app.source is AppSource.FLEET_DEFAULT and not values:
            plan.changes.append(FileChange.delete(path, last_commit_id=guard))
        elif problem is not None or existing != dict(values):
            plan.changes.append(FileChange.update(path, content, last_commit_id=guard))

    @staticmethod
    def _plan_pin(
        plan: _Plan,
        app: PlannedApp,
        layers: Sequence[LoadedLayer],
        version: str,
        *,
        emergency_pin: bool,
    ) -> None:
        tree = plan.state.repo.tree
        current = deploy_of(app, tuple(layers), tree).leaf.target_revision
        if version == current:
            return
        if app.source is AppSource.FLEET_DEFAULT:
            raise ChangeRefusedError(
                f"{app.chart} reaches {app.ref.name} as a fleet default, which cannot be pinned "
                "for one cluster: its revision comes from the default, the Sig values or an "
                "OCP-version pin",
                details={"rule": "fleet-default-pin"},
            )
        own = layers[-1]
        inherited = deploy_of(app, tuple(layers[:-1]), tree).leaf.target_revision
        doc = dict(own.values)
        if version == inherited:
            doc.pop(TARGET_REVISION, None)
        elif not emergency_pin:
            raise ChangeRefusedError(
                f"{version} differs from the inherited {inherited}: writing it is an emergency "
                "pin; ask for it explicitly with emergency_pin",
                details={
                    "rule": "emergency-pin-required",
                    "inherited": inherited,
                    "requested": version,
                },
            )
        else:
            doc[TARGET_REVISION] = version
            plan.findings.append(
                warning(
                    Rule.EMERGENCY_PIN,
                    f"pins {app.chart} to {version} on {app.ref.name} only (an emergency pin)",
                    team=app.team,
                    cluster=app.ref.id,
                    chart=app.chart,
                )
            )
        path = own.layer.path
        if own.file is None:
            plan.changes.append(FileChange.create(path, dump_values(doc)))
        elif doc:
            plan.changes.append(
                FileChange.update(path, dump_values(doc), last_commit_id=own.file.last_commit_id)
            )
        else:
            plan.changes.append(FileChange.delete(path, last_commit_id=own.file.last_commit_id))

    # ── remove ──────────────────────────────────────────────────────────────

    async def remove(
        self,
        key: str,
        team: str,
        chart: str,
        user: User,
        *,
        last_commit_id: str | None = None,
        mce: str | None = None,
        message: str | None = None,
    ) -> ChangeResult:
        """Open an MR deleting the chart's folder from the cluster (the workload is orphaned)."""
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        state = topology.team(team)
        await self._access.require_write(state.team)
        app = self._installed(state, summary, chart)
        if app.source is AppSource.FLEET_DEFAULT:
            scope = app.ref.defaults_scope
            raise ChangeRefusedError(
                f"{chart} reaches {summary.ref.name} as a fleet default of {team} ({app.folder}/): "
                f"it is on every destination of {scope}, and is not removed from one. Its values "
                "for this cluster are set here, or on the add-on's page on Addons "
                f"({team}/{chart}). An add-on wanted on some MCEs only is not a default: it is "
                "deployed on those MCEs (ADR-0053).",
                details={
                    "rule": "fleet-default-remove",
                    "path": str(app.folder),
                    "addon": f"/addons/{team}/{chart}",
                    # 3.12.0's key; that page now redirects to the add-on's.
                    "operator": f"/teams/{team}/operators/{chart}",
                },
            )
        deploy = await load_deploy(self._sigs, state.team, state.repo.tree, app)
        plan = _Plan(state, summary, charts=[chart], leaves=[deploy.leaf])
        values_path = app.folder.child(layout.VALUES_FILE)
        for path in state.repo.tree.files_under(app.folder):
            file = await self._sigs.read(state.team, path)
            guard = last_commit_id if (last_commit_id and path == values_path) else None
            plan.changes.append(
                FileChange.delete(
                    path, last_commit_id=guard or (file.last_commit_id if file else None)
                )
            )
        registration = layout.registration_dir(summary.ref)
        if registration is not None and not plan.tree.is_dir(registration):
            keep = registration.child(layout.GITKEEP)
            plan.changes.append(FileChange.create(keep, ""))
            plan.notes.append(
                f"{chart} was the last chart folder of {summary.ref.name} in {team}: {keep} keeps "
                f"the cluster registered, so {team}'s fleet defaults on it stay managed."
            )
        plan.notes.append(
            f"Deleting {app.folder}/ deletes the ArgoCD Application {deploy.leaf.name}, but ArgoCD "
            f"orphans the workload: {chart} keeps running on {summary.ref.name}. A full teardown "
            f"needs `argocd app delete {deploy.leaf.name} --cascade` on {deploy.leaf.argo}'s "
            "ArgoCD after the merge (runbook R8). Wingman has no ArgoCD access yet."
        )
        self._validate(topology, plan)
        return await self._open(plan, user, Verb.REMOVE, message, sync_notes=False)

    # ── shared ──────────────────────────────────────────────────────────────

    def _validate(self, topology: Topology, plan: _Plan) -> None:
        """Refuse a change that adds a platform error; note the apps it adds besides its own."""
        state = plan.state
        after_plan = refuse_new_errors(topology, state, plan.changes)
        old = {(a.ref, a.chart, a.source) for a in state.plan.apps}
        for app in after_plan.apps:
            if (app.ref, app.chart, app.source) not in old and app.chart not in plan.charts:
                plan.notes.append(
                    f"This also registers {app.ref.name} with {state.team.name}, so the fleet "
                    f"default {app.chart} ({app.folder}/) deploys to it too."
                )

    async def _open(
        self,
        plan: _Plan,
        user: User,
        verb: Verb,
        message: str | None,
        *,
        sync_notes: bool = True,
    ) -> ChangeResult:
        team, ref = plan.state.team, plan.summary.ref
        charts = plan.charts
        resource = f"{team.name}/{','.join(charts)}"
        action = verb.value.lower()
        branch = branch_name(
            username=user.username,
            action=f"{action}-{charts[0]}"
            if len(charts) == 1
            else f"{action}-{len(charts)}-charts",
            resource=ref.name,
            at=self._clock(),
        )
        notes = [*plan.notes, *(_sync_note(leaf) for leaf in plan.leaves if sync_notes)]
        title = mr_title(
            Repo.DAY2,
            verb,
            ResourceType.ADDON,
            resource,
            f"from {ref.name}" if verb is Verb.REMOVE else f"on {ref.name}",
        )
        human = _description(plan, verb, notes, message)
        metadata = MRMetadata(user.username, action, ResourceType.ADDON, resource, Repo.DAY2)
        commit_message = (
            f"{verb} {', '.join(charts)} {'from' if verb is Verb.REMOVE else 'on'} {ref.name}\n\n"
            f"Team: {team.name}\nCluster: {ref.id}\nRequested by {user.username} via Wingman"
        )
        merge_request = await open_team_mr(
            self._gitlab,
            self._sigs,
            team,
            user,
            branch=branch,
            action=action,
            message=commit_message,
            changes=plan.changes,
            title=title,
            description=mr_description(human, metadata),
        )
        return ChangeResult(
            team.name,
            plan.summary,
            merge_request,
            tuple(plan.changes),
            tuple(leaf.name for leaf in plan.leaves),
            tuple(plan.findings),
            tuple(notes),
        )


async def open_team_mr(
    gitlab: GitLabPort,
    sigs: SigsRepository,
    team: Team,
    user: User,
    *,
    branch: str,
    action: str,
    message: str,
    changes: Sequence[FileChange],
    title: str,
    description: str,
) -> MergeRequest:
    """One commit of ``changes`` on a new ``branch`` of ``team``'s repo, and its MR.

    The team's reads are dropped whatever happens: a write that failed may still have landed.
    """
    try:
        await gitlab.commit(
            team.project.id,
            branch=branch,
            start_branch=sigs.branch,
            message=message,
            changes=changes,
            author=commit_author(user),
        )
        return await gitlab.create_merge_request(
            team.project.id,
            NewMergeRequest(
                source_branch=branch,
                target_branch=sigs.branch,
                title=title,
                description=description,
                labels=(WINGMAN_LABEL, "day2", action),
            ),
        )
    finally:
        sigs.invalidate(team)


def _description(plan: _Plan, verb: Verb, notes: Sequence[str], message: str | None) -> str:
    ref = plan.summary.ref
    where = "from" if verb is Verb.REMOVE else "on"
    lines = [
        f"{verb} **{', '.join(plan.charts)}** (team **{plan.state.team.name}**) "
        f"{where} {ref.kind} cluster **{ref.name}** (`{ref.id}`).",
        "",
        "Files:",
        *(f"- {c.kind} `{c.path}`" for c in plan.changes),
    ]
    if plan.findings:
        lines += ["", "Warnings:", *(f"- {f.message}" for f in plan.findings)]
    lines += ["", *notes]
    if message:
        lines += ["", "Notes from the requester:", message]
    return "\n".join(lines)
