"""The values preview: the exact layered merge the platform renders, and who set each value.

The chart's own ``values.yaml`` (at the resolved ``targetRevision`` and
``path``) is the bottom layer, then the destination kind's stack from
``deployApp.yaml``. Provenance labels are layer roles (``chart``, ``team``,
``site``, ... ``cluster``); ``layers`` maps each role to its file. A preview
works for a chart that is not installed yet too: it shows what an install
into the cluster's own folder would render.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from wingman_day2.application.apps import AppDeploy, LoadedLayer, load_deploy, load_layers
from wingman_day2.application.catalog import ChartValues, chart_values
from wingman_day2.application.installed import override_layer
from wingman_day2.application.topology import ClusterSummary, TeamState, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind
from wingman_day2.domain.errors import UnknownChartError
from wingman_day2.domain.findings import Finding, Rule, error
from wingman_day2.domain.merge import MergeResult, merge_values
from wingman_day2.domain.platform import AppSource, PlannedApp
from wingman_day2.domain.stacks import LayerRole
from wingman_day2.ports import ChartRepository, SigsRepository


@dataclass(frozen=True, slots=True)
class ValuesPreview:
    """What one chart renders with on one cluster, layer by layer."""

    cluster: ClusterSummary
    app: PlannedApp
    installed: bool
    deploy: AppDeploy
    chart: ChartValues
    layers: tuple[LoadedLayer, ...]
    merged: MergeResult
    findings: tuple[Finding, ...]

    def role_values(self, role: LayerRole) -> dict[str, object]:
        """The values one layer contributes (``{}`` when it has no file)."""
        if role is LayerRole.CHART:
            return self.chart.values
        return next((x.values for x in self.layers if x.layer.role is role), {})

    @property
    def revision(self) -> str:
        """The chart revision the preview used."""
        return self.chart.revision


def team_version(state: TeamState, summary: ClusterSummary) -> str | None:
    """The OCP version ``state``'s render uses for the cluster.

    A UPI cluster's version is per team (each team's own ``version.yaml``), so
    a team that does not place it yet renders it version-less.
    """
    destination = state.plan.destination(summary.ref)
    if destination is not None:
        return destination.ocp_version
    if summary.ref.kind is ClusterKind.UPI:
        return None
    return summary.ocp_version


def find_app(state: TeamState, summary: ClusterSummary, chart: str) -> PlannedApp | None:
    """The app ``state`` generates for ``chart`` on the cluster (its own folder wins a tie)."""
    apps = [a for a in state.plan.apps_on(summary.ref) if a.chart == chart]
    return next((a for a in apps if a.source is AppSource.CLUSTER), apps[0] if apps else None)


class PreviewService:
    """Render the values preview."""

    def __init__(
        self, topology: TopologyService, sigs: SigsRepository, charts: ChartRepository
    ) -> None:
        """Discover through ``topology``; read through ``sigs`` and ``charts``."""
        self._topology = topology
        self._sigs = sigs
        self._charts = charts

    async def preview(
        self,
        key: str,
        team: str,
        chart: str,
        *,
        mce: str | None = None,
        version: str | None = None,
        override_values: Mapping[str, object] | None = None,
    ) -> ValuesPreview:
        """The merged values of ``team``'s ``chart`` on cluster ``key``.

        ``version`` previews another chart revision; ``override_values``
        previews an edit of the cluster's own values file.
        """
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        state = topology.team(team)
        app = find_app(state, summary, chart)
        installed = app is not None
        if app is None:
            if not state.repo.tree.is_dir(layout.operators_dir(chart)):
                raise UnknownChartError(
                    f"{chart} is neither installed on {summary.ref.name} by {team} nor in its "
                    "catalog",
                    details={"team": team, "chart": chart, "cluster": summary.ref.id},
                )
            app = PlannedApp(
                team, summary.ref, chart, AppSource.CLUSTER, team_version(state, summary)
            )
        tree = state.repo.tree
        deploy = await load_deploy(self._sigs, state.team, tree, app)
        revision = version or deploy.leaf.target_revision
        chart_defaults = await chart_values(
            self._charts, deploy.leaf.repo_url, revision, deploy.leaf.path
        )
        layers = await load_layers(self._sigs, state.team, tree, app.workload_layers)
        edited = override_layer(app).path
        inputs = []
        for loaded in layers:
            if override_values is not None and loaded.layer.path == edited:
                inputs.append((str(loaded.layer.role), dict(override_values)))
            elif loaded.exists:
                inputs.append((str(loaded.layer.role), loaded.values))
        merged = merge_values(chart_defaults.values, inputs, chart_label=str(LayerRole.CHART))
        findings = [
            *deploy.findings,
            *(
                error(
                    Rule.YAML_INVALID,
                    x.problem.message,
                    team=team,
                    path=x.problem.path,
                    cluster=summary.ref.id,
                    chart=chart,
                )
                for x in layers
                if x.problem is not None
            ),
        ]
        return ValuesPreview(
            summary, app, installed, deploy, chart_defaults, layers, merged, tuple(findings)
        )
