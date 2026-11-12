"""Authoring operators: a new one, its team default, and fleet defaults; one MR each (ADR-0043).

An *operator* is a chart in a team's catalog (``operators/<chart>/``) and the
fleet defaults built from it; the API keeps calling it an add-on. What
Wingman writes, on the team's own repo only:

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
  keeps those Applications: nothing is deleted, re-created or orphaned. An
  old entry of the scope's ``exclusions.yaml`` naming such a cluster would
  delete its app once the default exists: it goes in the same commit
  (ADR-0053).
- **update a fleet default**: its values file and its sync override.

Every change is refused first for a team that has not given Wingman write
access (``AccessService``), then checked as the platform would render it, and
measured on every app of the chart (``PlanWriter.validate``): whatever it
deletes or changes must be confirmed against the preview's digest. A dry run
plans everything and opens nothing.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Final, Literal

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title
from wingman_core.domain.users import User
from wingman_day2.application.apps import LoadedLayer, load_layers
from wingman_day2.application.changes import check_chart_name
from wingman_day2.application.plan_writer import (
    SCOPE_LABELS,
    SCOPE_NOUNS,
    SCOPE_ORDER,
    Action,
    Adoption,
    AuthoringPlan,
    AuthoringResult,
    DestinationImpact,
    Effect,
    KeyChange,
    PlanWriter,
    fleet_apps,
    scope_destinations,
)
from wingman_day2.application.topology import TeamState
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
from wingman_day2.domain.exclusions import set_excluded
from wingman_day2.domain.findings import Finding, Rule, warning
from wingman_day2.domain.merge import merge_values
from wingman_day2.domain.platform import TeamPlan, scope_exclusions
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
from wingman_day2.domain.yaml_text import dump_yaml, edit_mapping_text, same_value
from wingman_day2.domain.yaml_values import dump_values, parse_values

__all__ = [
    "SCOPE_LABELS",
    "SCOPE_NOUNS",
    "UNSET",
    "Action",
    "AddonTemplate",
    "Adoption",
    "AuthoringPlan",
    "AuthoringResult",
    "AuthoringService",
    "DestinationImpact",
    "Effect",
    "FleetDefault",
    "KeyChange",
    "NewAddon",
    "ScopeReach",
    "TeamDefaultEdit",
    "Unset",
    "fleet_apps",
    "new_deploy_config",
]

NAMESPACE: Final = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
"""A Kubernetes namespace name (a DNS label)."""

EDITABLE_KEYS: Final = (REPOURL, TARGET_REVISION, PATH, PROJECT_NAMESPACE, IGNORE_DIFFERENCES)
"""The team-default deploy-config keys an edit may set (sync options go separately)."""


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


def check_namespace(namespace: object) -> None:
    """Refuse a value that is no Kubernetes namespace name."""
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


def _existing_note(plan: AuthoringPlan) -> str | None:
    """The note on destinations that had the chart before and whose deploy config changes."""
    changed = [i for i in plan.impact if i.effect is Effect.CHANGED]
    if not changed:
        return None
    return (
        f"{len(changed)} destination(s) already deploy {plan.chart} "
        f"({', '.join(i.ref.name for i in changed)}), and this change moves what they deploy: "
        "listed below key by key, each to be confirmed. A manual-sync leaf deploys it when "
        "someone syncs it; an auto-sync one at once."
    )


class AuthoringService(PlanWriter):
    """Plan and open the MRs that create add-ons and edit team and fleet defaults."""

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
            (sync, count), *_ = settings.most_common()
            # A tie among the leaders goes to the platform's default, when it is one of them.
            if settings[PLATFORM_DEFAULT] == count:
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
                ScopeReach(scope, scope_destinations(state.plan, scope)) for scope in SCOPE_ORDER
            ),
        )

    async def fleet_defaults(self, team: str | None = None) -> list[FleetDefault]:
        """Every ``defaults/<scope>/<chart>/`` (of one team, or all)."""
        topology = await self._topology.load()
        states = [topology.team(team)] if team else list(topology.teams)
        access = await self._access.of_all([s.team for s in states])
        return [
            await self.fleet_default(state, scope, chart, access[state.team.name])
            for state in states
            for scope in DefaultsScope
            for chart in state.repo.tree.subdirs(layout.defaults_dir(scope))
        ]

    async def fleet_default(
        self, state: TeamState, scope: DefaultsScope, chart: str, access: TeamAccess
    ) -> FleetDefault:
        """One fleet default of ``state``'s team, read."""
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
        self,
        spec: NewAddon,
        user: User,
        *,
        dry_run: bool = False,
        message: str | None = None,
        expected_digest: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR adding ``spec`` to the team's catalog.

        Clusters that have the chart in their own folder already get the new
        team layer under it, so what they deploy may change: each such change
        is listed and must be confirmed (review of 3.8.0).
        """
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
        check_namespace(spec.project_namespace)
        _check_ignore_differences(spec.ignore_differences)
        plan = AuthoringPlan(state, Action.CREATE, chart, spec.default_scope)
        deploy_path = folder.child(layout.deploy_config_name(chart))
        plan.findings += await self.check_chart_repo(
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
                plan, spec.default_scope, values=spec.default_values, sync=None
            )
        after = await self.validate(topology, plan)
        existing = _existing_note(plan)
        plan.notes.append(
            f"After the merge, {chart} is in {state.team.project.path_with_namespace}'s catalog "
            f"(operators/{chart}/), with {_sync_words(sync)}. "
            + (
                existing
                if existing
                else "Nothing is deployed by the catalog itself: install it on a cluster from "
                "Wingman, or make it a fleet default."
            )
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
        self.confirm(plan, spec.confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

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
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
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
        if file is None:
            await self.refuse_if_deleted(plan, deploy_path, edit.last_commit_id)
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
            plan.findings += await self.check_chart_repo(
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
            self.write(plan, deploy_path, text, file, edit.last_commit_id)
        if edit.values is not None:
            await self.plan_values(
                plan, folder.child(layout.VALUES_FILE), edit.values, edit.last_commit_id
            )
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: operators/{chart}/ already holds this",
                details={"rule": "no-change"},
            )
        after = await self.validate(topology, plan)
        apps = [a for a in after.apps if a.chart == chart]
        plan.reach = sorted({a.ref for a in apps}, key=lambda r: r.id)
        changed = sum(1 for i in plan.impact if i.effect is Effect.CHANGED)
        plan.notes.append(
            f"Every destination that gets {chart} from {team} inherits this team default unless "
            "an OCP-version pin, a fleet default or its own folder sets the same key: "
            f"{len(plan.reach)} destination(s) get {chart} today, and what {changed} of them "
            "deploy changes (listed key by key). "
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
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

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
                check_namespace(value)
            if key == IGNORE_DIFFERENCES:
                _check_ignore_differences(value)
            if key == TARGET_REVISION and value == DEFAULT_REVISION:
                value = None
            if key == PATH and value is not None and str(value).strip("/") in ("", DEFAULT_PATH):
                value = None
            # An empty value removes the key: ArgoCD reads `ignoreDifferences: []` as none too.
            if value is None or value == "" or value == []:
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
        expected_digest: str | None = None,
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
        await self._plan_default(plan, scope, values=values, sync=sync)
        after = await self.validate(topology, plan)
        await self._reach(plan, after, scope)
        plan.title = mr_title(
            Repo.DAY2,
            Verb.PROMOTE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"to a fleet default on {SCOPE_LABELS[scope]}",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    async def _plan_default(
        self,
        plan: AuthoringPlan,
        scope: DefaultsScope,
        *,
        values: Mapping[str, object],
        sync: SyncSettings | None,
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
            team_doc = await self.doc(plan, layout.operators_dir(chart).child(name), after=True)
            override = policy_override([team_doc], sync.checked())
            if override:
                fleet_doc[SYNC_POLICY] = override
        plan.changes.append(FileChange.create(fleet.child(layout.VALUES_FILE), dump_values(values)))
        if fleet_doc:
            plan.changes.append(FileChange.create(fleet.child(name), dump_yaml(fleet_doc)))
        exclusions = (
            scope_exclusions(plan.state.repo, scope) if scope is not DefaultsScope.HUB else None
        )
        listed = set(exclusions.names(chart)) if exclusions else set()
        for destination in plan.state.plan.destinations:
            ref = destination.ref
            if ref.kind is ClusterKind.HUB or ref.defaults_scope is not scope:
                continue
            if base.is_dir(layout.chart_dir(ref, chart)):
                adoption = await self.adopt(plan, destination, fleet)
                if ref.exclusion_key in listed:
                    adoption = replace(adoption, exclusion_removed=True)
                plan.adopted.append(adoption)
        await self._drop_stale_entries(plan, scope)

    async def _drop_stale_entries(self, plan: AuthoringPlan, scope: DefaultsScope) -> None:
        """Remove the ``exclusions.yaml`` entries that would delete an adopted cluster's app.

        Until the default exists, an entry for its chart is inert (and a lint
        error: it names no chart folder). Once the folder is there it excludes
        the cluster, and the cluster's own folder is gone with the move: its
        app would be deleted and its workload orphaned. The cluster asked for
        nothing of the kind, and the entry is stale, so it goes in the same
        commit; the cluster is listed for confirmation (ADR-0053).
        """
        stale = {a.ref.exclusion_key or "" for a in plan.adopted if a.exclusion_removed}
        if not stale:
            return
        path = layout.exclusions_file(scope)
        file = await self._sigs.read(plan.state.team, path)
        if file is None:
            return
        exclusions = scope_exclusions(plan.state.repo, scope)
        names = [n for n in (exclusions.names(plan.chart) if exclusions else ()) if n not in stale]
        text = set_excluded(file.content, plan.chart, names, path=str(path))
        if text is not None and text != file.content:
            self.write(plan, path, text, file, None)
        plan.notes.append(
            f"{path} names {', '.join(sorted(stale))} for {plan.chart}: an entry that does "
            "nothing today (there is no default to exclude from) and that would delete the app "
            "of each once the default exists, because its own folder moves into the default. "
            "The entry goes in this MR, so each keeps its Application."
        )

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
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
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
                team_doc = await self.doc(
                    plan, layout.operators_dir(chart).child(name), after=False
                )
                policy = policy_override([team_doc], sync.checked(), current)
            new = {k: v for k, v in doc.items() if k != SYNC_POLICY}
            if policy:
                new = {**doc, SYNC_POLICY: policy}
            if not same_value(new, doc):
                text = edit_mapping_text(old_text, new, path=str(path)) if file else dump_yaml(new)
                self.write(plan, path, text, file, last_commit_id)
        if values is not None:
            await self.plan_values(plan, fleet.child(layout.VALUES_FILE), values, last_commit_id)
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {fleet}/ already holds this", details={"rule": "no-change"}
            )
        after = await self.validate(topology, plan)
        await self._reach(plan, after, scope, new_default=False)
        plan.title = mr_title(
            Repo.DAY2,
            Verb.UPDATE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"fleet default on {SCOPE_LABELS[scope]}",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    # ── shared ──────────────────────────────────────────────────────────────

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
            docs = [
                (str(x.path), await self.doc(plan, x.path, after=True))
                for x in app.deploy_config_layers
            ]
            merged = merge_values({}, docs).values
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
        if plan.excluded:
            plan.notes.append(
                f"{layout.exclusions_file(scope)} keeps it off "
                f"{', '.join(r.name for r in plan.excluded)}."
            )
        removed = [i for i in plan.impact if i.effect is Effect.REMOVED]
        if plan.adopted:
            plan.notes.append(
                f"{len(plan.adopted)} of them had {plan.chart} in their own folder: those folders "
                "move into the default in this MR (a non-empty values.yaml becomes "
                f"defaults/{scope}/{plan.chart}/values-<cluster>.yaml), so their Applications keep "
                "their names and ArgoCD neither deletes nor re-creates them."
                + ("" if removed else " Nothing is orphaned.")
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
