"""The value stacks the platform renders, per destination kind, lowest layer first (ADR-0021).

Workload values come from ``deploy/templates/deployApp.yaml``; the deploy
config from ``operators/templates/operators.yaml`` (and ``inClusterAppset.yaml``
for the hub). Every layer is optional (``ignoreMissingValueFiles``). The order
here is checked against ``render_chain.py`` by the oracle test, so a change to
the platform templates that moves a layer fails a test instead of silently
mislabelling provenance.

Hosted cluster, workload values (10 layers):

1. ``operators/<c>/values.yaml``                         team
2. ``operators/<c>/ocp-versions/<v>/values.yaml``        team-ocp-version (only with a version)
3. ``sites/<site>/values.yaml``                          site
4. ``sites/<site>/<env>/values.yaml``                    site-env
5. ``defaults/hosted-clusters/<c>/values.yaml``          fleet
6. ``defaults/hosted-clusters/<c>/values-<env>.yaml``    fleet-env
7. ``defaults/hosted-clusters/<c>/values-<cluster>.yaml``  fleet-target
8. ``<mce folder>/values.yaml``                          mce
9. ``<cluster folder>/values.yaml``                      cluster-wide
10. ``<cluster folder>/<c>/values.yaml``                 cluster (always wins)

An MCE hub uses ``defaults/mces`` and ``values-<mce>``; a UPI cluster uses
``defaults/upi`` and ``sites/<site>/<env>/upi/values.yaml`` at 8 (upi-wide).
The hub has three: ``defaults/hub/values.yaml``, ``operators/<c>/values.yaml``,
``defaults/hub/<c>/values.yaml``. Below all of them sits the chart's own
``values.yaml`` (the ``chart`` layer), which Helm loads itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from wingman_core.domain.git import RepoPath
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind, ClusterRef


class LayerRole(StrEnum):
    """What a layer is; also the label provenance reports for the values it set."""

    CHART = "chart"
    HUB = "hub"
    TEAM = "team"
    TEAM_OCP_VERSION = "team-ocp-version"
    SITE = "site"
    SITE_ENV = "site-env"
    FLEET = "fleet"
    FLEET_ENV = "fleet-env"
    FLEET_TARGET = "fleet-target"
    MCE = "mce"
    UPI_WIDE = "upi-wide"
    CLUSTER_WIDE = "cluster-wide"
    CLUSTER = "cluster"


@dataclass(frozen=True, slots=True)
class Layer:
    """One value file in a stack."""

    role: LayerRole
    path: RepoPath


def workload_layers(ref: ClusterRef, chart: str, ocp_version: str | None) -> tuple[Layer, ...]:
    """The workload value files of ``chart`` on ``ref``, lowest first."""
    team = layout.operators_dir(chart).child(layout.VALUES_FILE)
    chart_folder = layout.chart_dir(ref, chart)
    if ref.kind is ClusterKind.HUB:
        hub = layout.defaults_dir(ref.defaults_scope)
        return (
            Layer(LayerRole.HUB, hub.child(layout.VALUES_FILE)),
            Layer(LayerRole.TEAM, team),
            Layer(LayerRole.CLUSTER, chart_folder.child(layout.VALUES_FILE)),
        )
    fleet = layout.defaults_dir(ref.defaults_scope).child(chart)
    target = ref.exclusion_key
    layers = [Layer(LayerRole.TEAM, team)]
    if ocp_version:
        layers.append(
            Layer(
                LayerRole.TEAM_OCP_VERSION,
                layout.ocp_version_dir(chart, ocp_version).child(layout.VALUES_FILE),
            )
        )
    layers += [
        Layer(LayerRole.SITE, layout.site_dir(ref.site).child(layout.VALUES_FILE)),
        Layer(LayerRole.SITE_ENV, layout.site_env_dir(ref.site, ref.env).child(layout.VALUES_FILE)),
        Layer(LayerRole.FLEET, fleet.child(layout.VALUES_FILE)),
        Layer(LayerRole.FLEET_ENV, fleet.child(f"values-{ref.env}.yaml")),
        Layer(LayerRole.FLEET_TARGET, fleet.child(f"values-{target}.yaml")),
    ]
    if ref.kind is ClusterKind.UPI:
        layers.append(
            Layer(LayerRole.UPI_WIDE, layout.upi_dir(ref.site, ref.env).child(layout.VALUES_FILE))
        )
    else:
        layers.append(
            Layer(
                LayerRole.MCE,
                layout.mce_dir(ref.site, ref.env, ref.mce).child(layout.VALUES_FILE),
            )
        )
    layers += [
        Layer(LayerRole.CLUSTER_WIDE, layout.cluster_dir(ref).child(layout.VALUES_FILE)),
        Layer(LayerRole.CLUSTER, chart_folder.child(layout.VALUES_FILE)),
    ]
    return tuple(layers)


def deploy_config_layers(ref: ClusterRef, chart: str, ocp_version: str | None) -> tuple[Layer, ...]:
    """The deploy-config files of ``chart`` on ``ref``, lowest first.

    Team default, per-OCP-version pin, fleet default, the cluster's own folder.
    A ``targetRevision`` in the fleet default therefore overrides an
    OCP-version pin (a known footgun, linted), and one in the cluster folder
    is an emergency pin that detaches the cluster from both.
    """
    name = layout.deploy_config_name(chart)
    team = Layer(LayerRole.TEAM, layout.operators_dir(chart).child(name))
    own = Layer(LayerRole.CLUSTER, layout.chart_dir(ref, chart).child(name))
    if ref.kind is ClusterKind.HUB:
        return (team, own)
    layers = [team]
    if ocp_version:
        layers.append(
            Layer(
                LayerRole.TEAM_OCP_VERSION, layout.ocp_version_dir(chart, ocp_version).child(name)
            )
        )
    fleet = layout.defaults_dir(ref.defaults_scope).child(chart, name)
    layers += [Layer(LayerRole.FLEET, fleet), own]
    return tuple(layers)
