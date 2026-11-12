"""Authoring add-ons: a new add-on, its team default, and fleet defaults; one MR each (ADR-0043).

What Wingman writes, on the team's own repo only:

- **create**: ``operators/<chart>/<chart>.yaml`` (the deploy config: lowercase
  ``repourl``, and ``targetRevision``, ``path``, ``projectNamespace``,
  ``syncPolicy``, ``ignoreDifferences`` only when set) and
  ``operators/<chart>/values.yaml``; optionally a fleet default in the same MR.
- **update the team default**: the deploy config edited in place (comments
  and untouched lines kept, ``domain.yaml_text``), and the values file.
- **make default**: ``defaults/<scope>/<chart>/values.yaml`` (always: the file
  is what makes the folder exist) and ``<chart>.yaml`` only for a sync
  override. A cluster that already has the chart in its own folder would get
  the same app twice (the XOR rule); its folder moves into the default in the
  same commit. Both folders generate the same Application names, so ArgoCD
  keeps those Applications: nothing is deleted, re-created or orphaned. The
  move is automatic when the cluster's effective deploy config and values do
  not change, and must be confirmed per cluster when they do.
- **update a fleet default**: its values file and its sync override.

Every change is refused first for a team that has not given Wingman write
access (``AccessService``), then checked as the platform would render it
(``refuse_new_errors``). A dry run plans everything and opens nothing.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Final, Literal
from urllib.parse import urlsplit

from wingman_core.domain.git import ChangeKind, FileChange, FileContent, RepoPath, commit_author
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
from wingman_day2.application.apps import LoadedLayer, load_layers
from wingman_day2.application.catalog import (
    chart_repo_findings,
    chart_values,
    check_chart_repo,
    version_order,
)
from wingman_day2.application.changes import check_chart_name, refuse_new_errors
from wingman_day2.application.topology import TeamState, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind, ClusterRef, DefaultsScope
from wingman_day2.domain.deploy_config import (
    DEFAULT_PATH,
    DEFAULT_REVISION,
    IGNORE_DIFFERENCES,
    PATH,
    PROJECT_NAMESPACE,
    REPOURL,
    SYNC_POLICY,
    TARGET_REVISION,
    leaf_application,
    miscased_repourl_keys,
    truthy,
)
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartAlreadyInstalledError,
    ChartNotInstalledError,
    UnknownChartError,
)
from wingman_day2.domain.findings import Finding, Rule, warning
from wingman_day2.domain.merge import merge_values
from wingman_day2.domain.platform import AppSource, Destination, PlannedApp, TeamPlan
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.sync_policy import (
    AUTOMATED,
    PLATFORM_DEFAULT,
    SYNC_OPTIONS,
    SyncSettings,
    effective_policy,
    full_policy,
    policy_override,
    sync_settings,
)
from wingman_day2.domain.teams import TeamAccess
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.yaml_text import dump_yaml, edit_mapping_text, same_value
from wingman_day2.domain.yaml_values import dump_values, parse_values
from wingman_day2.ports import ChartRepository, SigsRepository

SCOPE_LABELS: Final = {
    DefaultsScope.HUB: "the hub",
    DefaultsScope.MCES: "every MCE",
    DefaultsScope.HOSTED_CLUSTERS: "every hosted cluster",
    DefaultsScope.UPI: "every UPI cluster",
}
"""How a fleet scope is named to people: in titles, notes and the web."""

SCOPE_NOUNS: Final = {
    DefaultsScope.HUB: "hub",
    DefaultsScope.MCES: "MCE(s)",
    DefaultsScope.HOSTED_CLUSTERS: "hosted cluster(s)",
    DefaultsScope.UPI: "UPI cluster(s)",
}

NAMESPACE: Final = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
"""A Kubernetes namespace name (a DNS label)."""

EDITABLE_KEYS: Final = (REPOURL, TARGET_REVISION, PATH, PROJECT_NAMESPACE, IGNORE_DIFFERENCES)
"""The team-default deploy-config keys an edit may set (sync options go separately)."""


class Action(StrEnum):
    """What an authoring MR does: its branch action, label and footer ``Action``."""

    CREATE = "create-addon"
    UPDATE_DEFAULT = "update-default"
    MAKE_DEFAULT = "make-default"


class _Unset(Enum):
    UNSET = "unset"


UNSET: Final = _Unset.UNSET
"""A field the request left out: leave it as it is."""

type Unset = Literal[_Unset.UNSET]


@dataclass(frozen=True, slots=True)
class NewAddon:
    """A new add-on for a team's catalog, optionally a fleet default at once."""

    team: str
    chart: str
    repourl: str
    sync: SyncSettings
    target_revision: str | None = None
    path: str | None = None
    project_namespace: str | None = None
    ignore_differences: list[object] | None = None
    values: Mapping[str, object] = field(default_factory=dict)
    default_scope: DefaultsScope | None = None
    default_values: Mapping[str, object] = field(default_factory=dict)
    confirm_changes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TeamDefaultEdit:
    """An edit of ``operators/<chart>/``: the keys it sets (``None`` removes), sync, values."""

    keys: Mapping[str, object | None] = field(default_factory=dict)
    sync: SyncSettings | None = None
    values: Mapping[str, object] | None = None
    last_commit_id: str | None = None


@dataclass(frozen=True, slots=True)
class KeyChange:
    """One leaf of a cluster's effective deploy config or values that a move changes."""

    stack: str
    key: str
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class Adoption:
    """A cluster whose own chart folder moves into the new fleet default."""

    ref: ClusterRef
    moved: tuple[tuple[RepoPath, RepoPath], ...]
    deleted: tuple[RepoPath, ...]
    gitkeep: RepoPath | None
    changes: tuple[KeyChange, ...]

    def details(self) -> dict[str, object]:
        """The adoption as plain data, for a problem's ``details``."""
        return {
            "cluster": self.ref.id,
            "name": self.ref.name,
            "changes": [
                {"stack": c.stack, "key": c.key, "before": c.before, "after": c.after}
                for c in self.changes
            ],
        }


@dataclass(slots=True)
class AuthoringPlan:
    """Everything one authoring MR writes and what it does."""

    state: TeamState
    action: Action
    chart: str
    scope: DefaultsScope | None
    title: str = ""
    changes: list[FileChange] = field(default_factory=list)
    previous: dict[str, str] = field(default_factory=dict)
    reach: list[ClusterRef] = field(default_factory=list)
    adopted: list[Adoption] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def team(self) -> str:
        """The team's name."""
        return self.state.team.name

    @property
    def tree(self) -> RepoTree:
        """The team repo as it would be after the MR."""
        return self.state.repo.tree.with_changes(self.changes)

    @property
    def needs_confirmation(self) -> list[str]:
        """The ids of the adopted clusters whose effective config the move changes."""
        return [a.ref.id for a in self.adopted if a.changes]

    def pending(self, path: RepoPath) -> FileChange | None:
        """The last change this plan makes to ``path``."""
        return next((c for c in reversed(self.changes) if c.path == path), None)


@dataclass(frozen=True, slots=True)
class AuthoringResult:
    """A plan, and the MR it opened (``None`` for a dry run)."""

    plan: AuthoringPlan
    merge_request: MergeRequest | None


@dataclass(frozen=True, slots=True)
class ScopeReach:
    """A fleet scope and the destinations a default there reaches today."""

    scope: DefaultsScope
    destinations: tuple[ClusterRef, ...]

    @property
    def label(self) -> str:
        """``every hosted cluster``, ``the hub``, ..."""
        return SCOPE_LABELS[self.scope]


@dataclass(frozen=True, slots=True)
class AddonTemplate:
    """What a new add-on form starts from, read from the team's own add-ons."""

    team: str
    access: TeamAccess
    sync: SyncSettings
    sync_source: str
    repourl_prefix: str | None
    scopes: tuple[ScopeReach, ...]


@dataclass(frozen=True, slots=True)
class FleetDefault:
    """One ``defaults/<scope>/<chart>/`` of a team."""

    team: str
    chart: str
    scope: DefaultsScope
    folder: RepoPath
    in_catalog: bool
    values: LoadedLayer
    deploy: LoadedLayer
    sync: SyncSettings
    sync_overridden: bool
    reach: tuple[ClusterRef, ...]
    excluded: tuple[ClusterRef, ...]
    tweaks: tuple[RepoPath, ...]
    access: TeamAccess
    findings: tuple[Finding, ...]

    @property
    def last_commit_id(self) -> str | None:
        """The commit the folder was read at (send it back on edit)."""
        file = self.values.file or self.deploy.file
        return file.last_commit_id if file else None


def _flatten(values: object, prefix: str = "") -> dict[str, object]:
    if isinstance(values, dict) and values:
        out: dict[str, object] = {}
        for key, sub in values.items():
            out |= _flatten(sub, f"{prefix}.{key}" if prefix else str(key))
        return out
    return {prefix: values} if prefix else {}


def _key_changes(
    stack: str, before: dict[str, object], after: dict[str, object]
) -> list[KeyChange]:
    old, new = _flatten(before), _flatten(after)
    return [
        KeyChange(stack, key, old.get(key), new.get(key))
        for key in sorted({*old, *new})
        if key not in old or key not in new or not same_value(old[key], new[key])
    ]


def fleet_apps(plan: TeamPlan, chart: str, scope: DefaultsScope) -> list[PlannedApp]:
    """The apps a fleet default of ``chart`` generates (on the hub, the hub's own folder)."""
    if scope is DefaultsScope.HUB:
        return [a for a in plan.apps if a.ref.kind is ClusterKind.HUB and a.chart == chart]
    return [
        a
        for a in plan.apps
        if a.chart == chart
        and a.source is AppSource.FLEET_DEFAULT
        and a.ref.defaults_scope is scope
    ]


def _scope_destinations(plan: TeamPlan, scope: DefaultsScope) -> tuple[ClusterRef, ...]:
    return tuple(d.ref for d in plan.destinations if d.ref.defaults_scope is scope and d.renders)


def new_deploy_config(spec: NewAddon) -> dict[str, object]:
    """The ``<chart>.yaml`` of a new add-on: only the keys that are set, lowercase ``repourl``."""
    doc: dict[str, object] = {REPOURL: spec.repourl.strip()}
    if spec.target_revision and spec.target_revision != DEFAULT_REVISION:
        doc[TARGET_REVISION] = spec.target_revision
    if spec.path and spec.path.strip("/") not in ("", DEFAULT_PATH):
        doc[PATH] = spec.path.strip("/")
    if spec.project_namespace:
        doc[PROJECT_NAMESPACE] = spec.project_namespace
    policy = full_policy(spec.sync)
    if policy:
        doc[SYNC_POLICY] = policy
    if spec.ignore_differences:
        doc[IGNORE_DIFFERENCES] = list(spec.ignore_differences)
    return doc


def _check_namespace(namespace: object) -> None:
    if namespace is not None and not NAMESPACE.match(str(namespace)):
        raise ChangeRefusedError(
            f"{namespace!r} is not a Kubernetes namespace name (lowercase letters, digits, '-')",
            details={"rule": "namespace-invalid"},
        )


def _check_ignore_differences(value: object) -> None:
    if value is not None and not (
        isinstance(value, list) and all(isinstance(item, dict) for item in value)
    ):
        raise ChangeRefusedError(
            "ignoreDifferences is ArgoCD's list of {group, kind, jsonPointers, ...} entries",
            details={"rule": "ignore-differences-invalid"},
        )


class AuthoringService:
    """Plan and open the MRs that create add-ons and edit team and fleet defaults."""

    def __init__(
        self,
        gitlab: GitLabPort,
        topology: TopologyService,
        sigs: SigsRepository,
        charts: ChartRepository,
        access: AccessService,
        clock: Clock,
    ) -> None:
        """Write through ``gitlab``; read through the rest; ask ``access`` before any write."""
        self._gitlab = gitlab
        self._topology = topology
        self._sigs = sigs
        self._charts = charts
        self._access = access
        self._clock = clock

    # ── reads ───────────────────────────────────────────────────────────────

    async def template(self, team: str) -> AddonTemplate:
        """What a new add-on of ``team`` starts from."""
        state = (await self._topology.load()).team(team)
        tree = state.repo.tree
        charts = tree.subdirs(RepoPath.of(layout.OPERATORS))
        layers = [
            Layer(LayerRole.TEAM, layout.operators_dir(c).child(layout.deploy_config_name(c)))
            for c in charts
        ]
        loaded = [x for x in await load_layers(self._sigs, state.team, tree, layers) if x.exists]
        settings = Counter(sync_settings(x.values.get(SYNC_POLICY)) for x in loaded)
        project = state.team.project.path_with_namespace
        if settings:
            (sync, count), *rest = settings.most_common()
            if rest and rest[0][1] == count and PLATFORM_DEFAULT in dict(settings.most_common()):
                sync = PLATFORM_DEFAULT
            source = (
                f"the sync options most of {project}'s add-ons use "
                f"({settings[sync]} of {len(loaded)})"
            )
        else:
            sync = PLATFORM_DEFAULT
            source = f"the platform's default: {project} has no add-on in operators/ to copy from"
        prefixes = Counter(
            str(x.values[REPOURL]).strip().rsplit("/", 1)[0] + "/"
            for x in loaded
            if truthy(x.values.get(REPOURL)) and "/" in str(x.values[REPOURL])
        )
        return AddonTemplate(
            team=state.team.name,
            access=await self._access.of(state.team),
            sync=sync,
            sync_source=source,
            repourl_prefix=prefixes.most_common(1)[0][0] if prefixes else None,
            scopes=tuple(
                ScopeReach(scope, _scope_destinations(state.plan, scope))
                for scope in (
                    DefaultsScope.HOSTED_CLUSTERS,
                    DefaultsScope.MCES,
                    DefaultsScope.HUB,
                    DefaultsScope.UPI,
                )
            ),
        )

    async def fleet_defaults(self, team: str | None = None) -> list[FleetDefault]:
        """Every ``defaults/<scope>/<chart>/`` (of one team, or all)."""
        topology = await self._topology.load()
        states = [topology.team(team)] if team else list(topology.teams)
        access = await self._access.of_all([s.team for s in states])
        return [
            await self._fleet_default(state, scope, chart, access[state.team.name])
            for state in states
            for scope in DefaultsScope
            for chart in state.repo.tree.subdirs(layout.defaults_dir(scope))
        ]

    async def _fleet_default(
        self, state: TeamState, scope: DefaultsScope, chart: str, access: TeamAccess
    ) -> FleetDefault:
        tree = state.repo.tree
        folder = layout.defaults_dir(scope).child(chart)
        name = layout.deploy_config_name(chart)
        team_deploy, values, deploy = await load_layers(
            self._sigs,
            state.team,
            tree,
            [
                Layer(LayerRole.TEAM, layout.operators_dir(chart).child(name)),
                Layer(LayerRole.FLEET, folder.child(layout.VALUES_FILE)),
                Layer(LayerRole.FLEET, folder.child(name)),
            ],
        )
        policy = effective_policy([team_deploy.values, deploy.values])
        apps = fleet_apps(state.plan, chart, scope)
        findings = [
            warning(
                Rule.YAML_INVALID,
                x.problem.message,
                team=state.team.name,
                path=x.problem.path,
                chart=chart,
            )
            for x in (team_deploy, values, deploy)
            if x.problem is not None
        ]
        return FleetDefault(
            team=state.team.name,
            chart=chart,
            scope=scope,
            folder=folder,
            in_catalog=tree.is_dir(layout.operators_dir(chart)),
            values=values,
            deploy=deploy,
            sync=sync_settings(policy),
            sync_overridden=SYNC_POLICY in deploy.values,
            reach=tuple(a.ref for a in apps),
            excluded=tuple(
                e.ref
                for e in state.plan.excluded
                if e.chart == chart and e.ref.defaults_scope is scope
            ),
            tweaks=tuple(
                p
                for p in tree.files_under(folder)
                if p.parent == folder and p.name.startswith("values-") and p.name.endswith(".yaml")
            ),
            access=access,
            findings=tuple(findings),
        )

    # ── create ──────────────────────────────────────────────────────────────

    async def create(
        self, spec: NewAddon, user: User, *, dry_run: bool = False, message: str | None = None
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR adding ``spec`` to the team's catalog."""
        topology = await self._topology.load()
        state = topology.team(spec.team)
        await self._access.require_write(state.team)
        chart = check_chart_name(spec.chart)
        folder = layout.operators_dir(chart)
        if state.repo.tree.is_dir(folder):
            raise ChartAlreadyInstalledError(
                f"{state.team.name} has {folder}/ already; edit its team default instead",
                details={"rule": "addon-exists", "team": state.team.name, "path": str(folder)},
            )
        sync = spec.sync.checked()
        _check_namespace(spec.project_namespace)
        _check_ignore_differences(spec.ignore_differences)
        plan = AuthoringPlan(state, Action.CREATE, chart, spec.default_scope)
        deploy_path = folder.child(layout.deploy_config_name(chart))
        plan.findings += await self._check_chart_repo(
            spec.repourl,
            spec.target_revision,
            spec.path,
            file=str(deploy_path),
            where={"team": state.team.name, "chart": chart},
        )
        plan.changes += [
            FileChange.create(deploy_path, dump_yaml(new_deploy_config(spec))),
            FileChange.create(folder.child(layout.VALUES_FILE), dump_values(spec.values)),
        ]
        label = SCOPE_LABELS[spec.default_scope] if spec.default_scope else ""
        if spec.default_scope is not None:
            await self._plan_default(
                plan,
                spec.default_scope,
                values=spec.default_values,
                sync=None,
                confirm=spec.confirm_changes,
                dry_run=dry_run,
            )
        after = refuse_new_errors(topology, state, plan.tree)
        plan.notes.append(
            f"After the merge, {chart} is in {state.team.project.path_with_namespace}'s catalog "
            f"(operators/{chart}/), with {_sync_words(sync)}. Nothing is deployed by the catalog "
            "itself: install it on a cluster from Wingman, or make it a fleet default."
        )
        if spec.default_scope is not None:
            await self._reach(plan, after, spec.default_scope)
        plan.title = mr_title(
            Repo.DAY2,
            Verb.CREATE,
            ResourceType.ADDON,
            f"{state.team.name}/{chart}",
            "in the team catalog" + (f" and as a fleet default on {label}" if label else ""),
        )
        return await self._finish(plan, user, message, dry_run=dry_run)

    async def _check_chart_repo(
        self,
        repourl: str,
        revision: object,
        chart_path: object,
        *,
        file: str,
        where: Mapping[str, str],
    ) -> list[Finding]:
        """Refuse a chart repo URL that cannot work; warn about one Wingman cannot check.

        ``file`` is the deploy config that sets it, for the findings.
        """
        url = urlsplit(repourl.strip())
        if url.scheme not in ("http", "https") or not url.netloc or not url.path.strip("/"):
            raise ChangeRefusedError(
                f"{repourl!r} is not a chart repo URL (https://<gitlab>/<group>/<chart>.git)",
                details={"rule": "repourl-invalid", "repourl": repourl},
            )
        if not self._charts.on_this_gitlab(repourl):
            return [
                warning(
                    Rule.CHART_REPO_ELSEWHERE,
                    f"{repourl} is not on this GitLab: Wingman cannot list its versions or show "
                    "its default values (ArgoCD reads it as written)",
                    path=file,
                    **where,
                )
            ]
        check = await check_chart_repo(self._charts, repourl)
        project = check.project
        if project is None:
            raise ChangeRefusedError(
                check.problem or f"{repourl} names no project on this GitLab that Wingman can read",
                details={"rule": "chart-repo-missing", "repourl": repourl},
            )
        found = chart_repo_findings(check, path=file, **where)
        wanted = str(revision) if truthy(revision) else DEFAULT_REVISION
        if wanted != DEFAULT_REVISION:
            branches = await self._charts.branches(project)
            if wanted not in branches:
                raise ChangeRefusedError(
                    f"{project.path_with_namespace} has no branch {wanted!r}; a chart version is "
                    "one of its branches (or HEAD, its default branch)",
                    details={
                        "rule": "revision-unknown",
                        "revision": wanted,
                        "versions": version_order(project.default_branch, branches),
                    },
                )
        chart = await chart_values(
            self._charts, repourl, wanted, str(chart_path) if truthy(chart_path) else DEFAULT_PATH
        )
        if chart.problem is not None:
            found.append(warning(Rule.CHART_VALUES_MISSING, chart.problem, path=file, **where))
        return found

    # ── team default ────────────────────────────────────────────────────────

    async def update_team_default(
        self,
        team: str,
        chart: str,
        edit: TeamDefaultEdit,
        user: User,
        *,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR editing ``operators/<chart>/``."""
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        tree = state.repo.tree
        folder = layout.operators_dir(chart)
        if not tree.is_dir(folder):
            raise UnknownChartError(
                f"team {team} has no operators/{chart}/", details={"team": team, "chart": chart}
            )
        plan = AuthoringPlan(state, Action.UPDATE_DEFAULT, chart, None)
        deploy_path = folder.child(layout.deploy_config_name(chart))
        file = await self._sigs.read(state.team, deploy_path) if tree.is_file(deploy_path) else None
        old_text = file.content if file else ""
        doc, problem = parse_values(old_text, path=str(deploy_path))
        if problem is not None:
            raise ChangeRefusedError(
                f"{problem.message} ({deploy_path}): fix it by hand first",
                details={"rule": str(Rule.YAML_INVALID), "path": str(deploy_path)},
            )
        new, renames = self._edited_deploy(doc, edit)
        repo_keys = {REPOURL, TARGET_REVISION, PATH}
        if repo_keys & set(edit.keys) and truthy(new.get(REPOURL)):
            plan.findings += await self._check_chart_repo(
                str(new[REPOURL]),
                new.get(TARGET_REVISION),
                new.get(PATH),
                file=str(deploy_path),
                where={"team": team, "chart": chart},
            )
        if not same_value(new, doc):
            text = (
                edit_mapping_text(old_text, new, path=str(deploy_path), renames=renames)
                if file
                else dump_yaml(new)
            )
            self._write(plan, deploy_path, text, file, edit.last_commit_id)
        if edit.values is not None:
            await self._plan_values(
                plan, folder.child(layout.VALUES_FILE), edit.values, edit.last_commit_id
            )
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: operators/{chart}/ already holds this",
                details={"rule": "no-change"},
            )
        after = refuse_new_errors(topology, state, plan.tree)
        apps = [a for a in after.apps if a.chart == chart]
        plan.reach = sorted({a.ref for a in apps}, key=lambda r: r.id)
        plan.notes.append(
            f"Every destination that gets {chart} from {team} inherits this team default unless "
            "an OCP-version pin, a fleet default or its own folder sets the same key: "
            f"{len(plan.reach)} destination(s) get {chart} today. "
            + (
                f"targetRevision moves to {new.get(TARGET_REVISION) or DEFAULT_REVISION} on every "
                "one that does not pin it. "
                if TARGET_REVISION in edit.keys
                else ""
            )
            + "Leaves that are manual-sync deploy the change only when someone syncs them."
        )
        plan.title = mr_title(
            Repo.DAY2, Verb.UPDATE, ResourceType.ADDON, f"{team}/{chart}", "team default"
        )
        return await self._finish(plan, user, message, dry_run=dry_run)

    @staticmethod
    def _edited_deploy(
        doc: Mapping[str, object], edit: TeamDefaultEdit
    ) -> tuple[dict[str, object], dict[str, str]]:
        """The deploy config after ``edit``, and the miscased keys renamed to ``repourl``."""
        new = dict(doc)
        renames: dict[str, str] = {}
        unknown = sorted(set(edit.keys) - set(EDITABLE_KEYS))
        if unknown:
            raise ChangeRefusedError(
                f"{unknown[0]} is not a key Wingman edits", details={"rule": "key-not-editable"}
            )
        for key, value in edit.keys.items():
            if key == REPOURL:
                if value is None or not str(value).strip():
                    raise ChangeRefusedError(
                        "repourl cannot be removed: the platform needs it to find the chart",
                        details={"rule": str(Rule.REPOURL_MISSING)},
                    )
                miscased = miscased_repourl_keys(new)
                if miscased and REPOURL not in new:
                    renames[miscased[0]] = REPOURL
                    new = {(REPOURL if k == miscased[0] else k): v for k, v in new.items()}
                    miscased = miscased[1:]
                for stray in miscased:
                    new.pop(stray, None)
                value = str(value).strip()
            if key == PROJECT_NAMESPACE:
                _check_namespace(value)
            if key == IGNORE_DIFFERENCES:
                _check_ignore_differences(value)
            if key == TARGET_REVISION and value == DEFAULT_REVISION:
                value = None
            if key == PATH and value is not None and str(value).strip("/") in ("", DEFAULT_PATH):
                value = None
            if value is None or value == "":
                new.pop(key, None)
            else:
                new[key] = value
        if edit.sync is not None:
            policy = full_policy(edit.sync.checked(), new.get(SYNC_POLICY))
            if policy:
                new[SYNC_POLICY] = policy
            else:
                new.pop(SYNC_POLICY, None)
        return new, renames

    # ── fleet defaults ──────────────────────────────────────────────────────

    async def make_default(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        user: User,
        *,
        values: Mapping[str, object],
        sync: SyncSettings | None = None,
        confirm_changes: Sequence[str] = (),
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR making ``chart`` a fleet default."""
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        if not state.repo.tree.is_dir(layout.operators_dir(chart)):
            raise UnknownChartError(
                f"team {team} has no operators/{chart}/", details={"team": team, "chart": chart}
            )
        plan = AuthoringPlan(state, Action.MAKE_DEFAULT, chart, scope)
        await self._plan_default(
            plan, scope, values=values, sync=sync, confirm=confirm_changes, dry_run=dry_run
        )
        after = refuse_new_errors(topology, state, plan.tree)
        await self._reach(plan, after, scope)
        plan.title = mr_title(
            Repo.DAY2,
            Verb.PROMOTE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"to a fleet default on {SCOPE_LABELS[scope]}",
        )
        return await self._finish(plan, user, message, dry_run=dry_run)

    async def _plan_default(
        self,
        plan: AuthoringPlan,
        scope: DefaultsScope,
        *,
        values: Mapping[str, object],
        sync: SyncSettings | None,
        confirm: Sequence[str],
        dry_run: bool,
    ) -> None:
        chart = plan.chart
        base = plan.state.repo.tree
        fleet = layout.defaults_dir(scope).child(chart)
        if base.is_dir(fleet):
            raise ChartAlreadyInstalledError(
                f"{chart} is a fleet default on {SCOPE_LABELS[scope]} already ({fleet}/); edit it "
                "instead",
                details={"rule": "default-exists", "path": str(fleet)},
            )
        name = layout.deploy_config_name(chart)
        fleet_doc: dict[str, object] = {}
        if sync is not None:
            team_doc = await self._doc(plan, layout.operators_dir(chart).child(name), after=True)
            override = policy_override([team_doc], sync.checked())
            if override:
                fleet_doc[SYNC_POLICY] = override
        plan.changes.append(FileChange.create(fleet.child(layout.VALUES_FILE), dump_values(values)))
        if fleet_doc:
            plan.changes.append(FileChange.create(fleet.child(name), dump_yaml(fleet_doc)))
        for destination in plan.state.plan.destinations:
            ref = destination.ref
            if ref.kind is ClusterKind.HUB or ref.defaults_scope is not scope:
                continue
            if base.is_dir(layout.chart_dir(ref, chart)):
                plan.adopted.append(await self._adopt(plan, destination, fleet))
        needs = plan.needs_confirmation
        if not dry_run and sorted(set(confirm)) != sorted(needs):
            changed = [a for a in plan.adopted if a.changes]
            raise ChangeRefusedError(
                (
                    f"{len(changed)} cluster(s) already have {chart} in their own folder, and "
                    "moving it into the default changes what they deploy: confirm each of them "
                    f"in confirm_changes ({', '.join(needs)})"
                )
                if needs
                else "confirm_changes names clusters whose move changes nothing; send it empty",
                details={
                    "rule": "confirm-changes",
                    "needs_confirmation": needs,
                    "adopted": [a.details() for a in changed],
                },
            )

    async def _adopt(
        self, plan: AuthoringPlan, destination: Destination, fleet: RepoPath
    ) -> Adoption:
        """Move ``destination``'s own chart folder into the default; compare before and after."""
        ref = destination.ref
        chart = plan.chart
        team = plan.state.team
        base = plan.state.repo.tree
        own = layout.chart_dir(ref, chart)
        values_path = own.child(layout.VALUES_FILE)
        deploy_path = own.child(layout.deploy_config_name(chart))
        files = base.files_under(own)
        others = [
            p for p in files if p not in (values_path, deploy_path) and not p.name.startswith(".")
        ]
        if others:
            raise ChangeRefusedError(
                f"{own}/ holds {others[0]} besides its values and deploy config; move or delete it "
                f"by hand, then make {chart} a default",
                details={
                    "rule": "adoption-blocked",
                    "cluster": ref.id,
                    "files": [str(p) for p in others],
                },
            )
        app = PlannedApp(team.name, ref, chart, AppSource.CLUSTER, destination.ocp_version)
        deploy_before = await self._merged(plan, app.deploy_config_layers, after=False)
        values_before = await self._merged(plan, app.workload_layers, after=False)
        moved: list[tuple[RepoPath, RepoPath]] = []
        deleted: list[RepoPath] = []
        tweak = fleet.child(f"values-{ref.exclusion_key}.yaml")
        for path in files:
            file = await self._sigs.read(team, path)
            text = file.content if file else ""
            if path == values_path and text.strip() not in ("", "{}"):
                _, problem = parse_values(text, path=str(path))
                if problem is not None:
                    raise ChangeRefusedError(
                        f"{problem.message} ({path}): fix it by hand, then make {chart} a default",
                        details={"rule": "adoption-blocked", "cluster": ref.id, "path": str(path)},
                    )
                plan.changes.append(FileChange.create(tweak, text))
                moved.append((path, tweak))
            else:
                deleted.append(path)
            plan.previous[str(path)] = text
            plan.changes.append(
                FileChange.delete(path, last_commit_id=file.last_commit_id if file else None)
            )
        gitkeep = None
        registration = layout.registration_dir(ref)
        if registration is not None and not plan.tree.is_dir(registration):
            gitkeep = registration.child(layout.GITKEEP)
            plan.changes.append(FileChange.create(gitkeep, ""))
        deploy_after = await self._merged(plan, app.deploy_config_layers, after=True)
        values_after = await self._merged(plan, app.workload_layers, after=True)
        changes = [
            *_key_changes("deploy", deploy_before, deploy_after),
            *_key_changes("values", values_before, values_after),
        ]
        return Adoption(ref, tuple(moved), tuple(deleted), gitkeep, tuple(changes))

    async def update_fleet_default(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        user: User,
        *,
        values: Mapping[str, object] | None = None,
        sync: SyncSettings | None | Unset = UNSET,
        last_commit_id: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR editing ``defaults/<scope>/<chart>/``.

        ``sync=None`` removes the fleet layer's sync settings (back to the team
        default's); ``UNSET`` leaves them.
        """
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        tree = state.repo.tree
        fleet = layout.defaults_dir(scope).child(chart)
        if not tree.is_dir(fleet):
            raise ChartNotInstalledError(
                f"{chart} is not a fleet default of {team} on {SCOPE_LABELS[scope]}",
                details={"team": team, "chart": chart, "scope": str(scope)},
            )
        plan = AuthoringPlan(state, Action.UPDATE_DEFAULT, chart, scope)
        name = layout.deploy_config_name(chart)
        if sync is not UNSET:
            path = fleet.child(name)
            file = await self._sigs.read(state.team, path) if tree.is_file(path) else None
            old_text = file.content if file else ""
            doc, problem = parse_values(old_text, path=str(path))
            if problem is not None:
                raise ChangeRefusedError(
                    f"{problem.message} ({path}): fix it by hand first",
                    details={"rule": str(Rule.YAML_INVALID), "path": str(path)},
                )
            current = doc.get(SYNC_POLICY)
            if sync is None:
                policy = dict(current) if isinstance(current, Mapping) else {}
                policy.pop(AUTOMATED, None)
                policy.pop(SYNC_OPTIONS, None)
            else:
                team_doc = await self._doc(
                    plan, layout.operators_dir(chart).child(name), after=False
                )
                policy = policy_override([team_doc], sync.checked(), current)
            new = {k: v for k, v in doc.items() if k != SYNC_POLICY}
            if policy:
                new = {**doc, SYNC_POLICY: policy}
            if not same_value(new, doc):
                text = edit_mapping_text(old_text, new, path=str(path)) if file else dump_yaml(new)
                self._write(plan, path, text, file, last_commit_id)
        if values is not None:
            await self._plan_values(plan, fleet.child(layout.VALUES_FILE), values, last_commit_id)
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {fleet}/ already holds this", details={"rule": "no-change"}
            )
        after = refuse_new_errors(topology, state, plan.tree)
        await self._reach(plan, after, scope, new_default=False)
        plan.title = mr_title(
            Repo.DAY2,
            Verb.UPDATE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"fleet default on {SCOPE_LABELS[scope]}",
        )
        return await self._finish(plan, user, message, dry_run=dry_run)

    # ── shared ──────────────────────────────────────────────────────────────

    async def _text(self, plan: AuthoringPlan, path: RepoPath, *, after: bool) -> str | None:
        if after:
            change = plan.pending(path)
            if change is not None:
                return None if change.kind is ChangeKind.DELETE else change.content
        if not plan.state.repo.tree.is_file(path):
            return None
        file = await self._sigs.read(plan.state.team, path)
        return file.content if file else None

    async def _doc(self, plan: AuthoringPlan, path: RepoPath, *, after: bool) -> dict[str, object]:
        text = await self._text(plan, path, after=after)
        if text is None:
            return {}
        values, problem = parse_values(text, path=str(path))
        if problem is not None:
            raise ChangeRefusedError(
                f"{problem.message} ({path}): Wingman cannot tell what the change does; fix it "
                "by hand first",
                details={"rule": str(Rule.YAML_INVALID), "path": str(path)},
            )
        return values

    async def _merged(
        self, plan: AuthoringPlan, layers: Sequence[Layer], *, after: bool
    ) -> dict[str, object]:
        docs = [(str(x.path), await self._doc(plan, x.path, after=after)) for x in layers]
        return merge_values({}, docs).values

    @staticmethod
    def _write(
        plan: AuthoringPlan,
        path: RepoPath,
        text: str,
        file: FileContent | None,
        last_commit_id: str | None,
    ) -> None:
        """Update ``file`` (guarded by the caller's read, else this one) or create ``path``."""
        if file is not None:
            plan.previous[str(path)] = file.content
            plan.changes.append(
                FileChange.update(path, text, last_commit_id=last_commit_id or file.last_commit_id)
            )
        else:
            plan.changes.append(FileChange.create(path, text))

    async def _plan_values(
        self,
        plan: AuthoringPlan,
        path: RepoPath,
        values: Mapping[str, object],
        last_commit_id: str | None,
    ) -> None:
        tree = plan.state.repo.tree
        file = await self._sigs.read(plan.state.team, path) if tree.is_file(path) else None
        if file is None:
            if values or not tree.files_under(path.parent):
                plan.changes.append(FileChange.create(path, dump_values(values)))
            return
        existing, problem = parse_values(file.content, path=str(path))
        if problem is None and same_value(existing, dict(values)):
            return
        self._write(plan, path, dump_values(values), file, last_commit_id)

    async def _reach(
        self,
        plan: AuthoringPlan,
        after: TeamPlan,
        scope: DefaultsScope,
        *,
        new_default: bool = True,
    ) -> None:
        """Fill ``plan.reach`` with the default's destinations, and say what the merge does."""
        apps = fleet_apps(after, plan.chart, scope)
        plan.reach = [a.ref for a in apps]
        label = SCOPE_LABELS[scope]
        project = plan.state.team.project.path_with_namespace
        if not apps:
            plan.notes.append(
                f"{project} registers no {SCOPE_NOUNS[scope]} yet: the default deploys to each "
                "one once the team has a folder for it."
            )
            return
        leaves = []
        for app in apps:
            merged = await self._merged(plan, app.deploy_config_layers, after=True)
            leaves.append(leaf_application(merged, team=plan.team, chart=plan.chart, ref=app.ref))
        auto = sum(1 for leaf in leaves if leaf.auto_sync)
        verb = "generates" if new_default else "updates"
        names = sorted({leaf.name for leaf in leaves})
        leaf_name = names[0] if len(names) == 1 else f"{plan.team}-<cluster>-{plan.chart}-deploy"
        where = (
            "the hub"
            if scope is DefaultsScope.HUB
            else f"the {len(apps)} {SCOPE_NOUNS[scope]} {project} registers "
            f"({', '.join(a.ref.name for a in apps)}), on each one's ArgoCD"
        )
        plan.notes.append(
            f"After the merge, ArgoCD {verb} {leaf_name} on {where}. "
            + (
                "They sync by themselves (auto-sync)."
                if auto == len(leaves)
                else "They are manual-sync: nothing deploys until someone syncs each one in "
                "ArgoCD (Wingman has no ArgoCD access yet)."
                if auto == 0
                else f"{auto} of them sync by themselves; the others wait for a manual sync."
            )
        )
        if plan.adopted:
            plan.notes.append(
                f"{len(plan.adopted)} of them had {plan.chart} in their own folder: those folders "
                "move into the default in this MR (a non-empty values.yaml becomes "
                f"defaults/{scope}/{plan.chart}/values-<cluster>.yaml), so their Applications keep "
                "their names and ArgoCD neither deletes nor re-creates them. Nothing is orphaned."
            )
        settings = {sync_settings(leaf.sync_policy) for leaf in leaves}
        if len(settings) > 1:
            plan.findings.append(
                warning(
                    Rule.SYNC_DIFFERS,
                    f"{plan.chart}'s sync options differ between destinations of {label}: an "
                    "OCP-version pin or a cluster's own deploy config sets them for some",
                    team=plan.team,
                    chart=plan.chart,
                )
            )

    async def _finish(
        self, plan: AuthoringPlan, user: User, message: str | None, *, dry_run: bool
    ) -> AuthoringResult:
        if dry_run:
            return AuthoringResult(plan, None)
        team = plan.state.team
        action = str(plan.action)
        resource = f"{team.name}/{plan.chart}"
        branch = branch_name(
            username=user.username,
            action=action,
            resource=f"{plan.chart}-{plan.scope}" if plan.scope else plan.chart,
            at=self._clock(),
        )
        metadata = MRMetadata(user.username, action, ResourceType.ADDON, resource, Repo.DAY2)
        commit_message = (
            f"{plan.title.removeprefix(f'[Wingman/{Repo.DAY2}] ')}\n\n"
            f"Team: {team.name}\nRequested by {user.username} via Wingman"
        )
        try:
            await self._gitlab.commit(
                team.project.id,
                branch=branch,
                start_branch=self._sigs.branch,
                message=commit_message,
                changes=plan.changes,
                author=commit_author(user),
            )
            merge_request = await self._gitlab.create_merge_request(
                team.project.id,
                NewMergeRequest(
                    source_branch=branch,
                    target_branch=self._sigs.branch,
                    title=plan.title,
                    description=mr_description(_description(plan, message), metadata),
                    labels=(WINGMAN_LABEL, "day2", action),
                ),
            )
        finally:
            self._sigs.invalidate(team)
        return AuthoringResult(plan, merge_request)


def _sync_words(sync: SyncSettings) -> str:
    mode = (
        "auto-sync"
        + (" with prune" if sync.prune else "")
        + (" and self-heal" if sync.self_heal else "")
        if sync.auto_sync
        else "manual sync"
    )
    options = ", ".join(sync.sync_options) if sync.sync_options else "no sync options"
    return f"{mode} and {options}"


def _description(plan: AuthoringPlan, message: str | None) -> str:
    lines = [
        f"{plan.title.removeprefix(f'[Wingman/{Repo.DAY2}] ')} (team **{plan.team}**).",
        "",
        "Files:",
        *(f"- {c.kind} `{c.path}`" for c in plan.changes),
    ]
    if plan.adopted:
        lines += [
            "",
            "Clusters whose own folder moves into the default (same Application names: nothing "
            "is deleted, re-created or orphaned):",
        ]
        for adoption in plan.adopted:
            what = (
                "nothing changes"
                if not adoption.changes
                else "; ".join(
                    f"{c.stack} `{c.key}`: {c.before!r} → {c.after!r}" for c in adoption.changes
                )
            )
            lines.append(f"- **{adoption.ref.name}** (`{adoption.ref.id}`): {what}")
    if plan.findings:
        lines += ["", "Warnings:", *(f"- {f.message}" for f in plan.findings)]
    lines += ["", *plan.notes]
    if message:
        lines += ["", "Notes from the requester:", message]
    return "\n".join(lines)
