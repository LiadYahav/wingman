"""A team's operators, read for the Operators pages (ADR-0053).

An operator is a chart in the team's catalog (``operators/<chart>/``) and the
fleet defaults built from it (``defaults/<scope>/<chart>/``). One operator's
page shows its two files, its OCP-version pins, and per scope: whether it is a
default there, and for each destination of that scope the team registers
whether the default deploys it (:class:`DestinationState`), its value
override and its own deploy config, if any.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from wingman_core.domain.git import RepoPath
from wingman_day2.application.access import AccessService
from wingman_day2.application.apps import LoadedLayer, load_deploy, load_layers
from wingman_day2.application.authoring import AuthoringService
from wingman_day2.application.catalog import CatalogEntry, CatalogService
from wingman_day2.application.plan_writer import SCOPE_ORDER, fleet_apps, tweak_path
from wingman_day2.application.topology import TeamState, Topology, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ALLOWED_ENVS, ClusterKind, ClusterRef, DefaultsScope
from wingman_day2.domain.deploy_config import TARGET_REVISION, truthy
from wingman_day2.domain.errors import UnknownChartError
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.platform import AppSource, scope_exclusions
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.sync_policy import SyncSettings
from wingman_day2.domain.teams import TeamAccess
from wingman_day2.ports import SigsRepository


class DestinationState(StrEnum):
    """How a fleet default stands on one destination of its scope."""

    DEFAULT = "default"
    EXCLUDED = "excluded"
    OWN_DEPLOY = "own-deploy"
    OWN_FOLDER = "own-folder"
    DUPLICATE = "duplicate"
    NONE = "none"
    NOT_RENDERED = "not-rendered"


@dataclass(frozen=True, slots=True)
class OcpVersionPin:
    """``operators/<chart>/ocp-versions/<v>/``: its files and the revision it pins."""

    version: str
    deploy: LoadedLayer
    values: LoadedLayer

    @property
    def target_revision(self) -> str | None:
        """The pinned ``targetRevision``, if the pin sets one."""
        value = self.deploy.values.get(TARGET_REVISION)
        return str(value) if truthy(value) else None


@dataclass(frozen=True, slots=True)
class ExclusionsView:
    """The scope's ``exclusions.yaml`` as it concerns one chart, read as the platform reads it.

    Wingman never writes it (ADR-0053's amendment); a repo that has one still
    renders and shows as it is.
    """

    file: LoadedLayer
    names: tuple[str, ...]
    unknown_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DestinationView:
    """One destination of a scope, and how the chart's default stands there."""

    ref: ClusterRef
    ocp_version: str | None
    renders: bool
    state: DestinationState
    app_name: str | None
    override: LoadedLayer | None
    shared_with: tuple[ClusterRef, ...]
    own_folder: RepoPath | None
    own_deploy: LoadedLayer | None

    @property
    def deployed(self) -> bool:
        """Whether an app of the chart exists there."""
        return self.app_name is not None


@dataclass(frozen=True, slots=True)
class ScopeView:
    """One scope of an operator: the default there, if any, and every destination of it."""

    scope: DefaultsScope
    is_default: bool
    folder: RepoPath
    values: LoadedLayer
    deploy: LoadedLayer
    sync: SyncSettings
    sync_overridden: bool
    env_files: tuple[tuple[str, LoadedLayer], ...]
    exclusions: ExclusionsView | None
    destinations: tuple[DestinationView, ...]
    unregistered: tuple[ClusterRef, ...]
    last_commit_id: str | None


@dataclass(frozen=True, slots=True)
class OperatorView:
    """One operator of a team."""

    team: str
    chart: str
    access: TeamAccess
    catalog: CatalogEntry | None
    deploy: LoadedLayer
    values: LoadedLayer
    ocp_versions: tuple[OcpVersionPin, ...]
    scopes: tuple[ScopeView, ...]
    findings: tuple[Finding, ...]

    @property
    def in_catalog(self) -> bool:
        """Whether ``operators/<chart>/`` exists."""
        return self.catalog is not None


@dataclass(frozen=True, slots=True)
class DefaultSummary:
    """Where an operator is a default, and how many destinations it reaches and skips."""

    scope: DefaultsScope
    reach: int
    excluded: int


@dataclass(frozen=True, slots=True)
class OperatorSummary:
    """One line of a team's operators list."""

    team: str
    chart: str
    catalog: CatalogEntry | None
    ocp_versions: tuple[str, ...]
    defaults: tuple[DefaultSummary, ...]
    installed_on: int
    warnings: int
    access: TeamAccess


def _read_commit(layers: Sequence[LoadedLayer]) -> str | None:
    """The commit the repo was read at: every file read in one pass has it (ADR-0035)."""
    return next((x.file.last_commit_id for x in layers if x.file is not None), None)


class OperatorService:
    """Read a team's operators."""

    def __init__(
        self,
        topology: TopologyService,
        sigs: SigsRepository,
        catalog: CatalogService,
        authoring: AuthoringService,
        access: AccessService,
    ) -> None:
        """Discover through ``topology``; read through ``sigs``, ``catalog`` and ``authoring``."""
        self._topology = topology
        self._sigs = sigs
        self._catalog = catalog
        self._authoring = authoring
        self._access = access

    @staticmethod
    def charts(state: TeamState) -> list[str]:
        """Every chart in ``operators/`` or in a defaults folder of the team, by name."""
        tree = state.repo.tree
        names = set(tree.subdirs(RepoPath.of(layout.OPERATORS)))
        for scope in DefaultsScope:
            names.update(tree.subdirs(layout.defaults_dir(scope)))
        return sorted(names)

    async def summaries(self, team: str) -> list[OperatorSummary]:
        """The team's operators."""
        topology = await self._topology.load()
        state = topology.team(team)
        access = await self._access.of(state.team)
        entries = {e.chart: e for e in await self._catalog.entries(team)}
        tree = state.repo.tree
        found = []
        for chart in self.charts(state):
            defaults = tuple(
                DefaultSummary(
                    scope,
                    len(fleet_apps(state.plan, chart, scope)),
                    sum(
                        1
                        for e in state.plan.excluded
                        if e.chart == chart and e.ref.defaults_scope is scope
                    ),
                )
                for scope in SCOPE_ORDER
                if tree.is_dir(layout.defaults_dir(scope).child(chart))
            )
            entry = entries.get(chart)
            found.append(
                OperatorSummary(
                    team=state.team.name,
                    chart=chart,
                    catalog=entry,
                    ocp_versions=tuple(tree.subdirs(layout.ocp_versions_dir(chart))),
                    defaults=defaults,
                    installed_on=sum(
                        1
                        for a in state.plan.apps
                        if a.chart == chart
                        and a.source is AppSource.CLUSTER
                        and a.ref.kind is not ClusterKind.HUB
                    ),
                    warnings=len(entry.findings) if entry else 0,
                    access=access,
                )
            )
        return found

    async def detail(self, team: str, chart: str) -> OperatorView:
        """One operator of the team; 404 when neither its catalog folder nor a default exists."""
        topology = await self._topology.load()
        state = topology.team(team)
        if chart not in self.charts(state):
            raise UnknownChartError(
                f"team {team} has no operators/{chart}/ and no fleet default of it",
                details={"team": team, "chart": chart},
            )
        tree = state.repo.tree
        access = await self._access.of(state.team)
        catalog = (
            await self._catalog.entry(team, chart)
            if tree.is_dir(layout.operators_dir(chart))
            else None
        )
        name = layout.deploy_config_name(chart)
        folder = layout.operators_dir(chart)
        deploy, values = await load_layers(
            self._sigs,
            state.team,
            tree,
            [
                Layer(LayerRole.TEAM, folder.child(name)),
                Layer(LayerRole.TEAM, folder.child(layout.VALUES_FILE)),
            ],
        )
        pins = []
        for version in tree.subdirs(layout.ocp_versions_dir(chart)):
            pin = layout.ocp_version_dir(chart, version)
            pin_deploy, pin_values = await load_layers(
                self._sigs,
                state.team,
                tree,
                [
                    Layer(LayerRole.TEAM_OCP_VERSION, pin.child(name)),
                    Layer(LayerRole.TEAM_OCP_VERSION, pin.child(layout.VALUES_FILE)),
                ],
            )
            pins.append(OcpVersionPin(version, pin_deploy, pin_values))
        scopes = await asyncio.gather(
            *(self._scope(topology, state, chart, scope, access) for scope in SCOPE_ORDER)
        )
        return OperatorView(
            team=state.team.name,
            chart=chart,
            access=access,
            catalog=catalog,
            deploy=deploy,
            values=values,
            ocp_versions=tuple(pins),
            scopes=tuple(scopes),
            findings=tuple(
                f for f in state.findings if f.chart == chart or f"/{chart}/" in f"/{f.path}/"
            ),
        )

    async def _scope(
        self,
        topology: Topology,
        state: TeamState,
        chart: str,
        scope: DefaultsScope,
        access: TeamAccess,
    ) -> ScopeView:
        tree = state.repo.tree
        fleet = layout.defaults_dir(scope).child(chart)
        is_default = tree.is_dir(fleet)
        default = await self._authoring.fleet_default(state, scope, chart, access)
        envs = [
            Layer(LayerRole.FLEET_ENV, fleet.child(f"values-{env}.yaml"))
            for env in sorted(ALLOWED_ENVS)
        ]
        env_files = [
            (layer.path.name.removeprefix("values-").removesuffix(".yaml"), loaded)
            for layer, loaded in zip(
                envs, await load_layers(self._sigs, state.team, tree, envs), strict=True
            )
            if loaded.exists
        ]
        exclusions = await self._exclusions(state, chart, scope)
        excluded = set(exclusions.names) if exclusions else set()
        destinations = [d for d in state.plan.destinations if d.ref.defaults_scope is scope]
        views = []
        for destination in destinations:
            ref = destination.ref
            own = tree.is_dir(layout.chart_dir(ref, chart)) and ref.kind is not ClusterKind.HUB
            app = next((a for a in state.plan.apps if a.ref == ref and a.chart == chart), None)
            if not destination.renders:
                state_ = DestinationState.NOT_RENDERED
            elif ref.kind is ClusterKind.HUB:
                state_ = DestinationState.DEFAULT if is_default else DestinationState.NONE
            elif is_default:
                if own:
                    state_ = (
                        DestinationState.OWN_DEPLOY
                        if ref.exclusion_key in excluded
                        else DestinationState.DUPLICATE
                    )
                elif ref.exclusion_key in excluded:
                    state_ = DestinationState.EXCLUDED
                else:
                    state_ = DestinationState.DEFAULT
            else:
                state_ = DestinationState.OWN_FOLDER if own else DestinationState.NONE
            app_name = (
                (await load_deploy(self._sigs, state.team, tree, app)).leaf.name
                if app is not None
                else None
            )
            override = None
            if ref.kind is not ClusterKind.HUB:
                (override,) = await load_layers(
                    self._sigs,
                    state.team,
                    tree,
                    [Layer(LayerRole.FLEET_TARGET, tweak_path(scope, chart, ref))],
                )
            own_deploy = None
            if own:
                (own_deploy,) = await load_layers(
                    self._sigs,
                    state.team,
                    tree,
                    [
                        Layer(
                            LayerRole.CLUSTER,
                            layout.chart_dir(ref, chart).child(layout.deploy_config_name(chart)),
                        )
                    ],
                )
            views.append(
                DestinationView(
                    ref=ref,
                    ocp_version=destination.ocp_version,
                    renders=destination.renders,
                    state=state_,
                    app_name=app_name,
                    override=override,
                    shared_with=tuple(
                        d.ref
                        for d in destinations
                        if d.ref != ref
                        and ref.kind is not ClusterKind.HUB
                        and d.ref.exclusion_key == ref.exclusion_key
                    ),
                    own_folder=layout.chart_dir(ref, chart) if own else None,
                    own_deploy=own_deploy,
                )
            )
        registered = {d.ref for d in destinations}
        unregistered = tuple(
            s.ref
            for s in topology.clusters
            if s.ref.defaults_scope is scope
            and s.ref.kind is not ClusterKind.HUB
            and s.ref not in registered
        )
        files = [default.values, default.deploy, *(x for _, x in env_files)]
        if exclusions is not None:
            files.append(exclusions.file)
        read_at = _read_commit(files) or await self._read_commit(state)
        return ScopeView(
            scope=scope,
            is_default=is_default,
            folder=fleet,
            values=default.values,
            deploy=default.deploy,
            # Not a default: the team default's, which a new default starts from.
            sync=default.sync,
            sync_overridden=default.sync_overridden,
            env_files=tuple(env_files),
            exclusions=exclusions,
            destinations=tuple(views),
            unregistered=unregistered,
            last_commit_id=read_at,
        )

    async def _read_commit(self, state: TeamState) -> str | None:
        """The commit the team repo was read at, from any file of it."""
        for path in sorted(state.repo.tree.files)[:1]:
            file = await self._sigs.read(state.team, RepoPath(path))
            if file is not None:
                return file.last_commit_id
        return None

    async def _exclusions(
        self, state: TeamState, chart: str, scope: DefaultsScope
    ) -> ExclusionsView | None:
        if scope is DefaultsScope.HUB:
            return None
        path = layout.exclusions_file(scope)
        (file,) = await load_layers(
            self._sigs, state.team, state.repo.tree, [Layer(LayerRole.FLEET, path)]
        )
        current = scope_exclusions(state.repo, scope)
        names = current.names(chart) if current else ()
        keys = {
            d.ref.exclusion_key for d in state.plan.destinations if d.ref.defaults_scope is scope
        }
        return ExclusionsView(
            file=file,
            names=tuple(names),
            unknown_names=tuple(n for n in names if n not in keys),
        )
