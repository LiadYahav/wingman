"""The charts installed on a cluster: its own chart folders plus applicable fleet defaults.

"Installed" means "the platform generates an app for it", not "it is running":
leaf apps are manual-sync and Wingman has no ArgoCD access yet, so a chart
listed here may never have been synced.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from wingman_day2.application.apps import AppDeploy, LoadedLayer, load_deploy, load_layers
from wingman_day2.application.topology import ClusterSummary, TeamState, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind
from wingman_day2.domain.deploy_config import TARGET_REVISION
from wingman_day2.domain.findings import Finding, Rule, error
from wingman_day2.domain.platform import AppSource, ExcludedDefault, PlannedApp
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.ports import SigsRepository


def override_layer(app: PlannedApp) -> Layer:
    """The values file Wingman edits for ``app`` on its cluster.

    The chart folder's ``values.yaml`` for a chart of the cluster's own; for a
    fleet default, ``defaults/<scope>/<chart>/values-<cluster>.yaml``, because
    the XOR rule keeps the chart out of the cluster folder.
    """
    if app.source is AppSource.FLEET_DEFAULT:
        return Layer(
            LayerRole.FLEET_TARGET, app.folder.child(f"values-{app.ref.exclusion_key}.yaml")
        )
    return Layer(LayerRole.CLUSTER, app.folder.child(layout.VALUES_FILE))


def tree_url(state: TeamState, branch: str, path: str) -> str:
    """The GitLab page of a folder in a team repo."""
    return f"{state.team.project.web_url}/-/tree/{branch}/{path}"


@dataclass(frozen=True, slots=True)
class InstalledChart:
    """One app on a cluster: its deploy config, the values file Wingman edits, and its page."""

    deploy: AppDeploy
    override: LoadedLayer
    web_url: str

    @property
    def app(self) -> PlannedApp:
        """The planned app."""
        return self.deploy.app

    @property
    def pinned(self) -> bool:
        """Whether the cluster's own deploy config pins ``targetRevision`` (an emergency pin)."""
        own = self.deploy.layers[-1]
        return (
            self.app.ref.kind is not ClusterKind.HUB
            and own.layer.role is LayerRole.CLUSTER
            and TARGET_REVISION in own.values
        )

    @property
    def findings(self) -> tuple[Finding, ...]:
        """Deploy-config findings plus a YAML problem in the override file."""
        problem = self.override.problem
        if problem is None:
            return self.deploy.findings
        app = self.app
        return (
            *self.deploy.findings,
            error(
                Rule.YAML_INVALID,
                problem.message,
                team=app.team,
                path=problem.path,
                cluster=app.ref.id,
                chart=app.chart,
            ),
        )


@dataclass(frozen=True, slots=True)
class ClusterCharts:
    """Everything deployed to one cluster, across teams."""

    cluster: ClusterSummary
    installed: tuple[InstalledChart, ...]
    excluded: tuple[ExcludedDefault, ...]
    findings: tuple[Finding, ...]


class InstalledService:
    """List the charts on a cluster."""

    def __init__(self, topology: TopologyService, sigs: SigsRepository) -> None:
        """Discover through ``topology``; read files through ``sigs``."""
        self._topology = topology
        self._sigs = sigs

    async def installed_chart(self, state: TeamState, app: PlannedApp) -> InstalledChart:
        """Load one app's deploy config and override file."""
        deploy, (override,) = await asyncio.gather(
            load_deploy(self._sigs, state.team, state.repo.tree, app),
            load_layers(self._sigs, state.team, state.repo.tree, [override_layer(app)]),
        )
        return InstalledChart(deploy, override, tree_url(state, self._sigs.branch, str(app.folder)))

    async def for_cluster(
        self, key: str, *, mce: str | None = None, team: str | None = None
    ) -> ClusterCharts:
        """The charts on the cluster ``key`` names, optionally only one team's."""
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        states = [topology.team(team)] if team else list(topology.teams)
        pairs = [(s, app) for s in states for app in s.plan.apps_on(summary.ref)]
        installed = await asyncio.gather(*(self.installed_chart(s, a) for s, a in pairs))
        excluded = tuple(e for s in states for e in s.plan.excluded if e.ref == summary.ref)
        findings = (*summary.findings, *(f for chart in installed for f in chart.findings))
        return ClusterCharts(summary, tuple(installed), excluded, tuple(findings))
