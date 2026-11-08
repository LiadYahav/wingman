"""The team catalog: ``operators/<chart>/`` folders, their pins, and the chart repos behind them.

A chart's versions are the branches of its chart repo (one frozen branch per
release); ``HEAD`` is the repo's default branch. Chart default values are the
chart's own ``<path>/values.yaml`` at the resolved revision (ADR-0024).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from wingman_core.domain.errors import GitError, GitUnavailableError, InvalidRepoPathError
from wingman_core.domain.git import Project, RepoPath
from wingman_day2.application.apps import LoadedLayer, load_layers
from wingman_day2.application.topology import TeamState, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.deploy_config import (
    DEFAULT_PATH,
    DEFAULT_REVISION,
    PATH,
    PROJECT_NAMESPACE,
    REPOURL,
    SYNC_POLICY,
    TARGET_REVISION,
    miscased_repourl_keys,
    repourl_moved_to,
    truthy,
)
from wingman_day2.domain.errors import UnknownChartError
from wingman_day2.domain.findings import Finding, Rule, error, warning
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.yaml_values import parse_values
from wingman_day2.ports import ChartRepository, SigsRepository

_NUMBER = re.compile(r"(\d+)")


def version_order(default_branch: str, branches: list[str]) -> list[str]:
    """The default branch first, then the rest newest release first (natural order)."""

    def key(name: str) -> tuple[tuple[int, int | str], ...]:
        return tuple((0, int(p)) if p.isdigit() else (1, p) for p in _NUMBER.split(name) if p)

    rest = sorted((b for b in branches if b != default_branch), key=key, reverse=True)
    return [default_branch, *rest] if default_branch in branches else rest


@dataclass(frozen=True, slots=True)
class ChartValues:
    """A chart's own default values at a revision, or why they could not be read."""

    project: Project | None
    revision: str
    path: str
    values: dict[str, object] = field(default_factory=dict)
    problem: str | None = None


def _chart_path(text: str) -> RepoPath:
    return RepoPath.root() if text in ("", DEFAULT_PATH) else RepoPath(text.strip("/"))


def unreadable(repo_url: str, exc: GitError) -> str:
    """Why one chart repo could not be read, for that chart alone.

    A chart repo GitLab refuses (no access, an answer Wingman does not expect)
    is a problem of that chart, shown on it; the rest of the page still loads.
    GitLab being unreachable is not caught: then every read fails, and the page
    says so (ADR-0004).
    """
    return f"{repo_url} could not be read, so its versions and default values are not shown: {exc}"


@dataclass(frozen=True, slots=True)
class ChartRepoCheck:
    """A ``repourl`` looked up: its project, or why it could not be read."""

    repo_url: str
    project: Project | None
    problem: str | None = None


async def check_chart_repo(charts: ChartRepository, repo_url: str) -> ChartRepoCheck:
    """Look ``repo_url`` up; only GitLab being unreachable raises (see :func:`unreadable`)."""
    try:
        return ChartRepoCheck(repo_url, await charts.resolve(repo_url))
    except GitUnavailableError:
        raise
    except GitError as exc:
        return ChartRepoCheck(repo_url, None, unreadable(repo_url, exc))


def chart_repo_findings(check: ChartRepoCheck, *, path: str, **where: str) -> list[Finding]:
    """What is wrong with the ``repourl`` that ``path`` sets: unreadable, or moved."""
    if check.problem is not None:
        return [error(Rule.CHART_REPO_UNREADABLE, check.problem, path=path, **where)]
    moved_to = repourl_moved_to(check.repo_url, check.project) if check.project else None
    if moved_to is None:
        return []
    message = (
        f"{path} sets `repourl: {check.repo_url}`, but GitLab moved that project to "
        f"{check.project.path_with_namespace if check.project else ''} (renamed or "
        "transferred). The old path only redirects, until a new project takes it: "
        f"set `repourl: {moved_to}`"
    )
    return [warning(Rule.REPOURL_MOVED, message, path=path, **where)]


async def chart_values(
    charts: ChartRepository, repo_url: str, revision: str, path: str
) -> ChartValues:
    """The chart's ``values.yaml`` at ``revision`` under ``path``, from its repo on this GitLab."""
    if not repo_url:
        return ChartValues(None, revision, path, problem="no repourl: the chart repo is unknown")
    check = await check_chart_repo(charts, repo_url)
    project = check.project
    if check.problem is not None:
        return ChartValues(None, revision, path, problem=check.problem)
    if project is None:
        return ChartValues(
            None,
            revision,
            path,
            problem=f"{repo_url} is not a project on this GitLab; chart defaults are not shown",
        )
    try:
        folder = _chart_path(path)
    except InvalidRepoPathError:
        return ChartValues(project, revision, path, problem=f"invalid chart path {path!r}")
    try:
        file = await charts.values(project, revision, folder)
    except GitUnavailableError:
        raise
    except GitError as exc:
        return ChartValues(project, revision, path, problem=unreadable(repo_url, exc))
    if file is None:
        return ChartValues(
            project,
            revision,
            path,
            problem=f"{project.path_with_namespace} has no {folder.child('values.yaml')} at "
            f"{revision}",
        )
    values, problem = parse_values(file.content, path=str(file.path))
    return ChartValues(project, revision, path, values, problem.message if problem else None)


@dataclass(frozen=True, slots=True)
class OcpPin:
    """``operators/<chart>/ocp-versions/<version>/`` and the revision it pins, if any."""

    version: str
    target_revision: str | None


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One ``operators/<chart>/`` of a team."""

    team: str
    chart: str
    deploy: LoadedLayer
    values: LoadedLayer
    pins: tuple[OcpPin, ...]
    fleet_defaults: tuple[DefaultsScope, ...]
    versions: tuple[str, ...] | None
    chart_project: Project | None
    findings: tuple[Finding, ...]

    @property
    def repo_url(self) -> str:
        """The team default ``repourl`` (lowercase key only), or ``""``."""
        value = self.deploy.values.get(REPOURL)
        return str(value) if truthy(value) else ""

    @property
    def team_revision(self) -> str:
        """The team default ``targetRevision``, ``HEAD`` when unset."""
        value = self.deploy.values.get(TARGET_REVISION)
        return str(value) if truthy(value) else DEFAULT_REVISION

    @property
    def path(self) -> str:
        """The chart's path in its repo, ``.`` when unset."""
        value = self.deploy.values.get(PATH)
        return str(value) if truthy(value) else DEFAULT_PATH

    @property
    def project_namespace(self) -> str:
        """The team default destination namespace, or ``""``."""
        value = self.deploy.values.get(PROJECT_NAMESPACE)
        return str(value) if truthy(value) else ""

    @property
    def sync_policy(self) -> dict[str, object]:
        """The team default sync policy."""
        value = self.deploy.values.get(SYNC_POLICY)
        return dict(value) if isinstance(value, dict) else {}


class CatalogService:
    """Browse the team catalogs."""

    def __init__(
        self, topology: TopologyService, sigs: SigsRepository, charts: ChartRepository
    ) -> None:
        """Discover through ``topology``, read through ``sigs`` and ``charts``."""
        self._topology = topology
        self._sigs = sigs
        self._charts = charts

    async def _entry(self, state: TeamState, chart: str, *, with_versions: bool) -> CatalogEntry:
        tree = state.repo.tree
        deploy_path = layout.operators_dir(chart).child(layout.deploy_config_name(chart))
        values_path = layout.operators_dir(chart).child(layout.VALUES_FILE)
        deploy, values = await load_layers(
            self._sigs,
            state.team,
            tree,
            [Layer(LayerRole.TEAM, deploy_path), Layer(LayerRole.TEAM, values_path)],
        )
        pin_layers = [
            Layer(
                LayerRole.TEAM_OCP_VERSION,
                layout.ocp_version_dir(chart, v).child(layout.deploy_config_name(chart)),
            )
            for v in tree.subdirs(layout.ocp_versions_dir(chart))
        ]
        pin_files = await load_layers(self._sigs, state.team, tree, pin_layers)
        pins = tuple(
            OcpPin(
                pin.layer.path.parent.name,
                str(pin.values[TARGET_REVISION]) if TARGET_REVISION in pin.values else None,
            )
            for pin in pin_files
        )
        fleet = tuple(
            scope for scope in DefaultsScope if tree.is_dir(layout.defaults_dir(scope).child(chart))
        )
        findings = self._findings(state.team.name, chart, deploy, values)
        repo_url = deploy.values.get(REPOURL)
        project, versions, repo_findings = await self._chart_repo(
            str(repo_url) if truthy(repo_url) else "",
            with_versions=with_versions,
            path=str(deploy.layer.path),
            where={"team": state.team.name, "chart": chart},
        )
        findings += repo_findings
        return CatalogEntry(
            state.team.name,
            chart,
            deploy,
            values,
            pins,
            fleet,
            versions,
            project,
            tuple(findings),
        )

    async def _chart_repo(
        self, repo_url: str, *, with_versions: bool, path: str, where: dict[str, str]
    ) -> tuple[Project | None, tuple[str, ...] | None, list[Finding]]:
        """The chart repo, its versions, and what is wrong with the ``repourl``."""
        if not repo_url:
            return None, None, []
        check = await check_chart_repo(self._charts, repo_url)
        project = check.project
        if with_versions and project is not None:
            try:
                branches = await self._charts.branches(project)
            except GitUnavailableError:
                raise
            except GitError as exc:
                check = ChartRepoCheck(repo_url, None, unreadable(repo_url, exc))
                project = None
            else:
                versions = tuple(version_order(project.default_branch, branches))
                return project, versions, chart_repo_findings(check, path=path, **where)
        return project, None, chart_repo_findings(check, path=path, **where)

    @staticmethod
    def _findings(team: str, chart: str, deploy: LoadedLayer, values: LoadedLayer) -> list[Finding]:
        where = {"team": team, "chart": chart}
        found = [
            error(Rule.YAML_INVALID, x.problem.message, path=x.problem.path, **where)
            for x in (deploy, values)
            if x.problem is not None
        ]
        found += [
            warning(
                Rule.REPOURL_MISCASED,
                f"{deploy.layer.path} sets `{key}`; the platform reads only lowercase `repourl`, "
                "so every cluster folder of this chart must set `repourl` itself",
                path=str(deploy.layer.path),
                **where,
            )
            for key in miscased_repourl_keys(deploy.values)
        ]
        if not truthy(deploy.values.get(REPOURL)):
            found.append(
                warning(
                    Rule.REPOURL_MISSING,
                    f"{deploy.layer.path} sets no lowercase `repourl`: an install must give one",
                    path=str(deploy.layer.path),
                    **where,
                )
            )
        return found

    async def entries(self, team: str | None = None) -> list[CatalogEntry]:
        """Every catalog entry (of one team, or all), with chart versions."""
        topology = await self._topology.load()
        states = [topology.team(team)] if team else list(topology.teams)
        pairs = [
            (state, chart)
            for state in states
            for chart in state.repo.tree.subdirs(RepoPath.of(layout.OPERATORS))
        ]
        return list(
            await asyncio.gather(*(self._entry(s, c, with_versions=True) for s, c in pairs))
        )

    async def entry(self, team: str, chart: str, *, with_versions: bool = True) -> CatalogEntry:
        """One team's ``operators/<chart>/``."""
        state = (await self._topology.load()).team(team)
        if not state.repo.tree.is_dir(layout.operators_dir(chart)):
            raise UnknownChartError(
                f"team {team} has no operators/{chart}/",
                details={"team": team, "chart": chart},
            )
        return await self._entry(state, chart, with_versions=with_versions)

    async def versions(self, team: str, chart: str) -> list[str]:
        """The chart repo's branches, default first (empty if the repo is not on this GitLab)."""
        return list((await self.entry(team, chart)).versions or ())

    async def default_values(self, team: str, chart: str, version: str) -> ChartValues:
        """The chart's own ``values.yaml`` at ``version``."""
        entry = await self.entry(team, chart, with_versions=False)
        return await chart_values(self._charts, entry.repo_url, version, entry.path)
