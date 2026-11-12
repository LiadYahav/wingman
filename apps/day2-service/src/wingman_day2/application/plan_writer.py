"""What every authoring MR shares: its plan, impact, digest, confirmation (ADR-0043, ADR-0053).

- **Impact.** Every app of the plan's chart, on every destination of every
  kind, before and after: its effective deploy config and workload values
  (chart defaults aside, Helm's ``null`` kept as a value, because a ``null``
  deletes a chart default), and whether it is generated at all. An app that
  goes is ``removed`` (the workload is orphaned, ``prune: false``), one that
  comes is ``added``, one whose config or values move is ``changed``.
- **Confirmation.** Every ``removed`` or ``changed`` destination, and every
  adopted cluster whose move changes something, must be confirmed by id,
  together with the preview's **digest**: a sha256 of what the MR writes
  (each file's path, kind and text), its title and its impact. A request
  whose digest is not the plan's any more is refused (``PlanChangedError``,
  409): the repo moved between the preview and the submit, and the person
  never saw what would now be opened (ADR-0006).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

from wingman_core.domain.errors import NotFoundError, RevisionConflictError
from wingman_core.domain.git import ChangeKind, FileChange, FileContent, RepoPath, commit_author
from wingman_core.domain.merge_request import MergeRequest, NewMergeRequest
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    MRMetadata,
    Repo,
    ResourceType,
    branch_name,
    mr_description,
)
from wingman_core.domain.users import User
from wingman_core.ports.clock import Clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.application.access import AccessService
from wingman_day2.application.catalog import (
    chart_repo_findings,
    chart_values,
    check_chart_repo,
    version_order,
)
from wingman_day2.application.changes import refuse_new_errors
from wingman_day2.application.topology import TeamState, Topology, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ALLOWED_ENVS, ClusterKind, ClusterRef, DefaultsScope
from wingman_day2.domain.deploy_config import (
    DEFAULT_PATH,
    DEFAULT_REVISION,
    leaf_application,
    truthy,
)
from wingman_day2.domain.errors import ChangeRefusedError, PlanChangedError
from wingman_day2.domain.findings import Finding, Rule, warning
from wingman_day2.domain.merge import merge_layers, merge_values
from wingman_day2.domain.platform import AppSource, Destination, PlannedApp, TeamPlan
from wingman_day2.domain.stacks import Layer
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.yaml_text import same_value
from wingman_day2.domain.yaml_values import YamlProblem, dump_values, parse_values
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

SCOPE_ORDER: Final = (
    DefaultsScope.HOSTED_CLUSTERS,
    DefaultsScope.MCES,
    DefaultsScope.HUB,
    DefaultsScope.UPI,
)
"""The order the web shows the scopes in."""


class Action(StrEnum):
    """What an authoring MR does: its branch action, label and footer ``Action``."""

    CREATE = "create-addon"
    UPDATE_DEFAULT = "update-default"
    MAKE_DEFAULT = "make-default"
    SET_EXCLUSIONS = "set-exclusions"
    OVERRIDE_VALUES = "override-values"
    OVERRIDE_DEPLOY = "override-deploy"


class Effect(StrEnum):
    """What an MR does to one destination's app of the chart."""

    CHANGED = "changed"
    REMOVED = "removed"
    ADDED = "added"


@dataclass(frozen=True, slots=True)
class KeyChange:
    """One leaf of a destination's effective deploy config or values that the MR changes.

    ``after_null`` is a Helm ``null``: the key is deleted, the chart's own default with it.
    """

    stack: str
    key: str
    before: object
    after: object
    after_null: bool = False

    def details(self) -> dict[str, object]:
        """As plain data."""
        return {
            "stack": self.stack,
            "key": self.key,
            "before": self.before,
            "after": self.after,
            "after_null": self.after_null,
        }


@dataclass(frozen=True, slots=True)
class Adoption:
    """A cluster whose own chart folder moves into the new fleet default.

    ``exclusion_removed``: an entry of the scope's ``exclusions.yaml`` named it
    for the chart (inert until now, the chart was no default), and would have
    deleted its app; the entry goes in the same commit.
    """

    ref: ClusterRef
    moved: tuple[tuple[RepoPath, RepoPath], ...]
    deleted: tuple[RepoPath, ...]
    gitkeep: RepoPath | None
    changes: tuple[KeyChange, ...]
    exclusion_removed: bool = False

    def details(self) -> dict[str, object]:
        """The adoption as plain data, for a problem's ``details``."""
        return {
            "cluster": self.ref.id,
            "name": self.ref.name,
            "changes": [c.details() for c in self.changes],
            "exclusion_removed": self.exclusion_removed,
        }


@dataclass(frozen=True, slots=True)
class DestinationImpact:
    """What the MR does to the chart's app on one destination."""

    ref: ClusterRef
    effect: Effect
    app_name: str
    changes: tuple[KeyChange, ...] = ()

    @property
    def orphaned(self) -> bool:
        """Whether the Application goes and its workload keeps running, unmanaged."""
        return self.effect is Effect.REMOVED

    @property
    def needs_confirmation(self) -> bool:
        """Whether the request must name this destination in ``confirm_changes``."""
        return self.effect is Effect.REMOVED or (
            self.effect is Effect.CHANGED and bool(self.changes)
        )

    def details(self) -> dict[str, object]:
        """As plain data."""
        return {
            "cluster": self.ref.id,
            "name": self.ref.name,
            "effect": str(self.effect),
            "app_name": self.app_name,
            "changes": [c.details() for c in self.changes],
            "orphaned": self.orphaned,
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
    impact: list[DestinationImpact] = field(default_factory=list)
    excluded: list[ClusterRef] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    docs: dict[str, tuple[dict[str, object], YamlProblem | None]] = field(
        default_factory=dict, repr=False
    )

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
        """The ids the request must confirm: what goes or changes, and moves that change."""
        ids = {a.ref.id for a in self.adopted if a.changes or a.exclusion_removed}
        ids |= {i.ref.id for i in self.impact if i.needs_confirmation}
        return sorted(ids)

    @property
    def digest(self) -> str:
        """A sha256 of what the MR writes and does; the preview's must match the submit's."""
        payload = {
            "title": self.title,
            "files": [
                [str(c.kind), str(c.path), c.content, str(c.previous_path or "")]
                for c in self.changes
            ],
            "impact": [i.details() for i in self.impact],
            "adopted": [a.details() for a in self.adopted],
        }
        text = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()

    def pending(self, path: RepoPath) -> FileChange | None:
        """The last change this plan makes to ``path``."""
        return next((c for c in reversed(self.changes) if c.path == path), None)

    def impact_on(self, ref: ClusterRef) -> DestinationImpact | None:
        """What the plan does on ``ref``."""
        return next((i for i in self.impact if i.ref == ref), None)


@dataclass(frozen=True, slots=True)
class AuthoringResult:
    """A plan, and the MR it opened (``None`` for a dry run)."""

    plan: AuthoringPlan
    merge_request: MergeRequest | None


def flatten(values: object, prefix: str = "") -> dict[str, object]:
    """Dotted leaves of ``values`` (an empty mapping is a leaf)."""
    if isinstance(values, dict) and values:
        out: dict[str, object] = {}
        for key, sub in values.items():
            out |= flatten(sub, f"{prefix}.{key}" if prefix else str(key))
        return out
    return {prefix: values} if prefix else {}


def key_changes(stack: str, before: dict[str, object], after: dict[str, object]) -> list[KeyChange]:
    """Every leaf that differs between ``before`` and ``after``, by dotted key."""
    old, new = flatten(before), flatten(after)
    return [
        KeyChange(stack, key, old.get(key), new.get(key), key in new and new[key] is None)
        for key in sorted({*old, *new})
        if key not in old or key not in new or not same_value(old[key], new[key])
    ]


def scope_destinations(plan: TeamPlan, scope: DefaultsScope) -> tuple[ClusterRef, ...]:
    """The destinations of ``scope`` a team registers that the platform renders."""
    return tuple(d.ref for d in plan.destinations if d.ref.defaults_scope is scope and d.renders)


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


def tweak_path(scope: DefaultsScope, chart: str, ref: ClusterRef) -> RepoPath:
    """``defaults/<scope>/<chart>/values-<name>.yaml``: a fleet default's values for one name."""
    return layout.defaults_dir(scope).child(chart, f"values-{ref.exclusion_key}.yaml")


class PlanWriter:
    """Reads a plan's files before and after, measures its impact, and opens its MR."""

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

    # ── files before and after ──────────────────────────────────────────────

    async def text(self, plan: AuthoringPlan, path: RepoPath, *, after: bool) -> str | None:
        """``path``'s text before the MR, or after it."""
        if after:
            change = plan.pending(path)
            if change is not None:
                return None if change.kind is ChangeKind.DELETE else change.content
        if not plan.state.repo.tree.is_file(path):
            return None
        file = await self._sigs.read(plan.state.team, path)
        return file.content if file else None

    async def doc(
        self, plan: AuthoringPlan, path: RepoPath, *, after: bool, strict: bool = True
    ) -> dict[str, object]:
        """``path`` parsed (``{}`` when absent).

        Invalid YAML refuses, or with ``strict=False`` reads as ``{}`` with a warning.
        """
        pending = plan.pending(path) if after else None
        if pending is None and str(path) in plan.docs:
            values, problem = plan.docs[str(path)]
        else:
            text = await self.text(plan, path, after=after)
            values, problem = parse_values(text, path=str(path)) if text is not None else ({}, None)
            if pending is None:
                # Only today's files are kept: a later change of the plan moves "after".
                plan.docs[str(path)] = (values, problem)
        if problem is not None:
            if strict:
                raise ChangeRefusedError(
                    f"{problem.message} ({path}): Wingman cannot tell what the change does; fix "
                    "it by hand first",
                    details={"rule": str(Rule.YAML_INVALID), "path": str(path)},
                )
            note = warning(
                Rule.YAML_INVALID,
                f"{problem.message}: Wingman reads {path} as empty to say what changes",
                team=plan.team,
                path=str(path),
                chart=plan.chart,
            )
            if note not in plan.findings:
                plan.findings.append(note)
        return values

    async def merged(
        self, plan: AuthoringPlan, layers: Sequence[Layer], *, after: bool, strict: bool = True
    ) -> dict[str, object]:
        """``layers`` merged as Helm's ``-f`` files are, ``null`` kept (chart defaults aside)."""
        docs = [
            (str(x.path), await self.doc(plan, x.path, after=after, strict=strict)) for x in layers
        ]
        return merge_layers(docs).values

    async def _app_state(
        self, plan: AuthoringPlan, app: PlannedApp, *, after: bool
    ) -> tuple[dict[str, object], dict[str, object], str]:
        deploy_docs = [
            (str(x.path), await self.doc(plan, x.path, after=after, strict=False))
            for x in app.deploy_config_layers
        ]
        values = await self.merged(plan, app.workload_layers, after=after, strict=False)
        name = leaf_application(
            merge_values({}, deploy_docs).values, team=plan.team, chart=app.chart, ref=app.ref
        ).name
        return merge_layers(deploy_docs).values, values, name

    async def compare(
        self, plan: AuthoringPlan, before: PlannedApp, after: PlannedApp
    ) -> list[KeyChange]:
        """What changes for one app between ``before`` (read as today) and ``after`` (the MR)."""
        deploy_before, values_before, _ = await self._app_state(plan, before, after=False)
        deploy_after, values_after, _ = await self._app_state(plan, after, after=True)
        return [
            *key_changes("deploy", deploy_before, deploy_after),
            *key_changes("values", values_before, values_after),
        ]

    # ── writing ─────────────────────────────────────────────────────────────

    @staticmethod
    def write(
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

    async def refuse_if_deleted(
        self, plan: AuthoringPlan, path: RepoPath, last_commit_id: str | None
    ) -> None:
        """409 when ``path`` is gone now but existed at the commit the caller read."""
        if not last_commit_id:
            return
        try:
            await self._gitlab.read_file(plan.state.team.project.id, path, ref=last_commit_id)
        except NotFoundError:
            return
        raise RevisionConflictError(
            f"{path} was deleted since {last_commit_id[:8]}, which the change was based on: "
            "read it again"
        )

    async def plan_values(
        self,
        plan: AuthoringPlan,
        path: RepoPath,
        values: Mapping[str, object],
        last_commit_id: str | None,
        *,
        delete_when_empty: bool = False,
    ) -> None:
        """Replace a values file whole, guarded; never re-create one deleted since the read."""
        tree = plan.state.repo.tree
        file = await self._sigs.read(plan.state.team, path) if tree.is_file(path) else None
        if file is None:
            await self.refuse_if_deleted(plan, path, last_commit_id)
            if values or (not delete_when_empty and not tree.files_under(path.parent)):
                plan.changes.append(FileChange.create(path, dump_values(values)))
            return
        existing, problem = parse_values(file.content, path=str(path))
        if delete_when_empty and not values:
            plan.previous[str(path)] = file.content
            plan.changes.append(
                FileChange.delete(path, last_commit_id=last_commit_id or file.last_commit_id)
            )
            return
        if problem is None and same_value(existing, dict(values)):
            return
        self.write(plan, path, dump_values(values), file, last_commit_id)

    async def check_chart_repo(
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

    async def adopt(
        self, plan: AuthoringPlan, destination: Destination, fleet: RepoPath
    ) -> Adoption:
        """Move ``destination``'s own chart folder into the fleet default; compare before, after.

        A non-empty ``values.yaml`` becomes ``values-<name>.yaml`` in ``fleet``,
        byte for byte: refused when that name is an env (the env layer has that
        file name) or the file exists already (another destination of that name).
        """
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
                f"by hand first",
                details={
                    "rule": "adoption-blocked",
                    "cluster": ref.id,
                    "files": [str(p) for p in others],
                },
            )
        app = PlannedApp(team.name, ref, chart, AppSource.CLUSTER, destination.ocp_version)
        deploy_before, values_before, _ = await self._app_state(plan, app, after=False)
        moved: list[tuple[RepoPath, RepoPath]] = []
        deleted: list[RepoPath] = []
        tweak = fleet.child(f"values-{ref.exclusion_key}.yaml")
        for path in files:
            file = await self._sigs.read(team, path)
            text = file.content if file else ""
            if path == values_path and text.strip() not in ("", "{}"):
                _, problem = parse_values(text, path=str(path))
                blocked = (
                    problem.message
                    if problem is not None
                    else f"{tweak.name} would be the {ref.exclusion_key} env layer"
                    if ref.exclusion_key in ALLOWED_ENVS
                    else f"{tweak} exists already (another destination named {ref.exclusion_key})"
                    if base.is_file(tweak) or plan.pending(tweak) is not None
                    else None
                )
                if blocked is not None:
                    raise ChangeRefusedError(
                        f"{path} cannot move into the default: {blocked}; move it by hand first",
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
        after_app = PlannedApp(
            team.name, ref, chart, AppSource.FLEET_DEFAULT, destination.ocp_version
        )
        deploy_after, values_after, _ = await self._app_state(plan, after_app, after=True)
        changes = [
            *key_changes("deploy", deploy_before, deploy_after),
            *key_changes("values", values_before, values_after),
        ]
        return Adoption(ref, tuple(moved), tuple(deleted), gitkeep, tuple(changes))

    # ── checking ────────────────────────────────────────────────────────────

    async def validate(self, topology: Topology, plan: AuthoringPlan) -> TeamPlan:
        """Refuse new platform errors (ADR-0023); fill the plan's impact and exclusions."""
        after = refuse_new_errors(topology, plan.state, plan.changes)
        before = {a.ref: a for a in plan.state.plan.apps if a.chart == plan.chart}
        later = {a.ref: a for a in after.apps if a.chart == plan.chart}
        impact: list[DestinationImpact] = []
        for ref in sorted({*before, *later}, key=lambda r: r.id):
            old, new = before.get(ref), later.get(ref)
            if new is None and old is not None:
                _, _, name = await self._app_state(plan, old, after=False)
                impact.append(DestinationImpact(ref, Effect.REMOVED, name))
            elif old is None and new is not None:
                _, _, name = await self._app_state(plan, new, after=True)
                impact.append(DestinationImpact(ref, Effect.ADDED, name))
            elif old is not None and new is not None:
                changes = await self.compare(plan, old, new)
                if changes:
                    _, _, name = await self._app_state(plan, new, after=True)
                    impact.append(DestinationImpact(ref, Effect.CHANGED, name, tuple(changes)))
        plan.impact = impact
        if plan.scope is not None and plan.scope is not DefaultsScope.HUB:
            plan.excluded = sorted(
                {
                    e.ref
                    for e in after.excluded
                    if e.chart == plan.chart and e.ref.defaults_scope is plan.scope
                },
                key=lambda r: r.id,
            )
        return after

    @staticmethod
    def confirm(
        plan: AuthoringPlan,
        confirm_changes: Sequence[str],
        expected_digest: str | None,
        *,
        dry_run: bool,
    ) -> None:
        """Refuse a request that did not confirm exactly what the plan changes, as previewed."""
        if dry_run:
            return
        digest = plan.digest
        if expected_digest is not None and expected_digest != digest:
            raise PlanChangedError(
                f"{plan.state.team.project.path_with_namespace} changed since the preview: this "
                "change would now write or do something else. Preview it again.",
                details={"rule": "plan-changed", "digest": digest, "expected": expected_digest},
            )
        needs = plan.needs_confirmation
        if sorted(set(confirm_changes)) != needs:
            raise ChangeRefusedError(
                (
                    f"this change deletes or changes what {len(needs)} destination(s) deploy: "
                    f"confirm each of them in confirm_changes ({', '.join(needs)})"
                )
                if needs
                else "confirm_changes names destinations this change does not touch; send it empty",
                details={
                    "rule": "confirm-changes",
                    "needs_confirmation": needs,
                    "impact": [i.details() for i in plan.impact if i.needs_confirmation],
                    "adopted": [
                        a.details() for a in plan.adopted if a.changes or a.exclusion_removed
                    ],
                },
            )
        if needs and expected_digest is None:
            raise ChangeRefusedError(
                "a change that deletes or changes what destinations deploy is confirmed against "
                "its preview: send the preview's digest as expected_digest",
                details={"rule": "confirm-against-preview", "needs_confirmation": needs},
            )

    # ── opening ─────────────────────────────────────────────────────────────

    async def finish(
        self, plan: AuthoringPlan, user: User, message: str | None, *, dry_run: bool
    ) -> AuthoringResult:
        """Open the plan's MR (one commit on a new branch), unless ``dry_run``."""
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
                    description=mr_description(describe(plan, message), metadata),
                    labels=(WINGMAN_LABEL, "day2", action),
                ),
            )
        finally:
            self._sigs.invalidate(team)
        return AuthoringResult(plan, merge_request)


def _change_words(changes: Sequence[KeyChange]) -> str:
    return "; ".join(
        f"{c.stack} `{c.key}`: {c.before!r} → "
        + ("null (deletes the chart's default)" if c.after_null else repr(c.after))
        for c in changes
    )


def describe(plan: AuthoringPlan, message: str | None) -> str:
    """The MR description's human part: files, what moves, what each destination gets."""
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
            what = _change_words(adoption.changes) if adoption.changes else "nothing changes"
            if adoption.exclusion_removed:
                what += (
                    f"; its entry in {layout.exclusions_file(adoption.ref.defaults_scope)} goes, "
                    "or its app would be deleted"
                )
            lines.append(f"- **{adoption.ref.name}** (`{adoption.ref.id}`): {what}")
    removed = [i for i in plan.impact if i.effect is Effect.REMOVED]
    changed = [i for i in plan.impact if i.effect is Effect.CHANGED]
    added = [i for i in plan.impact if i.effect is Effect.ADDED]
    if removed:
        lines += [
            "",
            "**Applications this deletes. ArgoCD orphans their workloads (`prune: false`): they "
            "keep running, unmanaged, until someone tears them down (runbook R10):**",
            *(f"- **{i.ref.name}** (`{i.ref.id}`): {i.app_name}" for i in removed),
        ]
    if changed:
        lines += [
            "",
            "Destinations whose deploy config or values change:",
            *(f"- **{i.ref.name}** (`{i.ref.id}`): {_change_words(i.changes)}" for i in changed),
        ]
    if added:
        lines += [
            "",
            "Applications this generates:",
            *(f"- **{i.ref.name}** (`{i.ref.id}`): {i.app_name}" for i in added),
        ]
    if plan.findings:
        lines += ["", "Warnings:", *(f"- {f.message}" for f in plan.findings)]
    lines += ["", *plan.notes]
    if message:
        lines += ["", "Notes from the requester:", message]
    return "\n".join(lines)
