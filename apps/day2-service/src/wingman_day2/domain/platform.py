"""The ApplicationSet chain, simulated: which leaf apps a team repo produces (ADR-0020).

The platform charts (``argocd-day2-platform``) generate, per team:

- the hub: one app per ``defaults/hub/<chart>/``;
- per ``sites/<site>/<env>/mces/<mce>/`` folder: the MCE hub's apps, from
  ``<mce>/in-cluster/<chart>/`` plus ``defaults/mces/<chart>/`` minus exclusions;
- per other folder in an MCE folder (a hosted cluster): its ``<chart>/``
  folders plus ``defaults/hosted-clusters/<chart>/`` minus exclusions;
- per ``sites/<site>/<env>/upi/<cluster>/``: its charts plus ``defaults/upi/``.

A destination whose required OCP version is missing renders nothing (the
templates ``required`` it): an MCE needs day1 ``version.yaml``, a hosted
cluster its day1 file. A malformed exclusions file fails the whole scope.
The THE ONE INVARIANT is that each (Argo, app name) comes out once; a chart
in both a defaults folder and a cluster folder breaks it (the XOR rule).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from wingman_core.domain.git import RepoPath
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import IN_CLUSTER, ClusterKind, ClusterRef, DefaultsScope
from wingman_day2.domain.day1 import Day1Index
from wingman_day2.domain.exclusions import Exclusions, platform_exclusions
from wingman_day2.domain.findings import Finding, Rule, error
from wingman_day2.domain.stacks import Layer, deploy_config_layers, workload_layers
from wingman_day2.domain.teams import TeamRepo
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.versions import read_version_file
from wingman_day2.domain.yaml_values import parse_yaml


class AppSource(StrEnum):
    """Which folder put a chart on a destination."""

    CLUSTER = "cluster"
    FLEET_DEFAULT = "fleet-default"


@dataclass(frozen=True, slots=True)
class Destination:
    """A destination a team repo registers, its OCP version, and whether it renders at all."""

    ref: ClusterRef
    ocp_version: str | None
    renders: bool = True


@dataclass(frozen=True, slots=True)
class PlannedApp:
    """One chart on one destination, as the platform would generate it."""

    team: str
    ref: ClusterRef
    chart: str
    source: AppSource
    ocp_version: str | None

    @property
    def folder(self) -> RepoPath:
        """The chart folder that generated this app."""
        if self.source is AppSource.FLEET_DEFAULT:
            return layout.defaults_dir(self.ref.defaults_scope).child(self.chart)
        return layout.chart_dir(self.ref, self.chart)

    @property
    def generator_app(self) -> str:
        """The wrapper app, ``<team>-<cluster>-<chart>``; unique per Argo unless XOR is broken."""
        return f"{self.team}-{self.ref.argo_cluster}-{self.chart}"

    @property
    def workload_layers(self) -> tuple[Layer, ...]:
        """The workload value files, lowest first."""
        return workload_layers(self.ref, self.chart, self.ocp_version)

    @property
    def deploy_config_layers(self) -> tuple[Layer, ...]:
        """The deploy-config files, lowest first."""
        return deploy_config_layers(self.ref, self.chart, self.ocp_version)


@dataclass(frozen=True, slots=True)
class ExcludedDefault:
    """A fleet default that ``exclusions.yaml`` keeps off a destination."""

    team: str
    ref: ClusterRef
    chart: str


@dataclass(frozen=True, slots=True)
class TeamPlan:
    """Everything one team repo makes the platform generate."""

    team: str
    destinations: tuple[Destination, ...]
    apps: tuple[PlannedApp, ...]
    excluded: tuple[ExcludedDefault, ...]

    def apps_on(self, ref: ClusterRef) -> list[PlannedApp]:
        """The apps on ``ref``."""
        return [app for app in self.apps if app.ref == ref]

    def destination(self, ref: ClusterRef) -> Destination | None:
        """``ref``'s entry, if this team registers it."""
        return next((d for d in self.destinations if d.ref == ref), None)

    def duplicates(self) -> list[Finding]:
        """One error per wrapper app generated more than once (the XOR rule)."""
        counts = Counter((app.ref.argo_instance, app.generator_app) for app in self.apps)
        found = []
        for app in self.apps:
            key = (app.ref.argo_instance, app.generator_app)
            if counts[key] > 1 and app.source is AppSource.CLUSTER:
                fleet = layout.defaults_dir(app.ref.defaults_scope).child(app.chart)
                found.append(
                    error(
                        Rule.DUPLICATE_APP,
                        f"{app.chart} is both a fleet default ({fleet}/) and in {app.folder}/: "
                        f"the platform generates {app.generator_app} twice on {key[0]}. Keep one "
                        f"(a per-cluster tweak of a fleet default is {fleet}/values-"
                        f"{app.ref.exclusion_key}.yaml), or exclude the cluster in "
                        f"{layout.exclusions_file(app.ref.defaults_scope)}.",
                        team=self.team,
                        path=str(app.folder),
                        cluster=app.ref.id,
                        chart=app.chart,
                    )
                )
        return found


def discover(tree: RepoTree) -> list[ClusterRef]:
    """Every MCE, hosted-cluster and UPI folder of a team repo, whatever its env."""
    refs: list[ClusterRef] = []
    sites = RepoPath.of(layout.SITES)
    for site in tree.subdirs(sites):
        for env in tree.subdirs(sites.child(site)):
            mces = sites.child(site, env, layout.MCES)
            for mce in tree.subdirs(mces):
                refs.append(ClusterRef.mce_hub(site, env, mce))
                refs += [
                    ClusterRef.hosted(site, env, mce, name)
                    for name in tree.subdirs(mces.child(mce))
                    if name != IN_CLUSTER
                ]
            refs += [
                ClusterRef.upi(site, env, name)
                for name in tree.subdirs(sites.child(site, env, layout.UPI))
                if name != IN_CLUSTER
            ]
    return refs


def scope_exclusions(repo: TeamRepo, scope: DefaultsScope) -> Exclusions | None:
    """The platform's reading of ``defaults/<scope>/exclusions.yaml``; ``None`` if it fails."""
    text = repo.files.get(str(layout.exclusions_file(scope)))
    if text is None:
        return Exclusions()
    doc, problem = parse_yaml(text, path=str(layout.exclusions_file(scope)))
    return None if problem is not None else platform_exclusions(doc)


def _version(repo: TeamRepo, ref: ClusterRef, day1: Day1Index) -> tuple[str | None, bool]:
    """``ref``'s OCP version and whether the templates can render it at all."""
    if ref.kind is ClusterKind.HUB:
        return None, True
    if ref.kind is ClusterKind.UPI:
        path = str(layout.upi_version_file(ref))
        text = repo.files.get(path)
        if text is None:
            return None, True
        return read_version_file(text, path=path).ocp_version, True
    mce = day1.mce(ref.site, ref.mce)
    if mce is None or mce.ocp_version is None:
        return None, False
    if ref.kind is ClusterKind.MCE:
        return mce.ocp_version, True
    hosted = day1.hosted_cluster(ref.site, ref.mce, ref.name)
    if hosted is None or hosted.ocp_version is None:
        return None, False
    return hosted.ocp_version, True


def plan_team(repo: TeamRepo, day1: Day1Index) -> TeamPlan:
    """The destinations and apps ``repo`` makes the platform generate."""
    tree = repo.tree
    destinations = [Destination(ClusterRef.hub(), None)]
    for ref in discover(tree):
        version, renders = _version(repo, ref, day1)
        destinations.append(Destination(ref, version, renders))
    apps: list[PlannedApp] = []
    excluded: list[ExcludedDefault] = []
    scopes = {scope: scope_exclusions(repo, scope) for scope in DefaultsScope}
    for destination in destinations:
        ref = destination.ref
        # The hub never passes through the operators chart, so no exclusions file affects it.
        exclusions = Exclusions() if ref.kind is ClusterKind.HUB else scopes[ref.defaults_scope]
        if not destination.renders or exclusions is None:
            continue
        own = tree.subdirs(layout.cluster_dir(ref))
        apps += [
            PlannedApp(repo.team, ref, chart, AppSource.CLUSTER, destination.ocp_version)
            for chart in own
        ]
        if ref.kind is ClusterKind.HUB:
            continue
        opted_out = exclusions.excluded_charts(ref.exclusion_key or "")
        for chart in tree.subdirs(layout.defaults_dir(ref.defaults_scope)):
            if chart in opted_out:
                excluded.append(ExcludedDefault(repo.team, ref, chart))
            else:
                apps.append(
                    PlannedApp(
                        repo.team, ref, chart, AppSource.FLEET_DEFAULT, destination.ocp_version
                    )
                )
    return TeamPlan(repo.team, tuple(destinations), tuple(apps), tuple(excluded))
