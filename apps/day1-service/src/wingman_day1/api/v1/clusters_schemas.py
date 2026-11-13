"""The bodies of ``/api/day1/clusters``: the list, a cluster's file, create and edit.

The router's other sub-resources have a module each: live status
(``cluster_status_schemas.py``), the network (``cluster_network_schemas.py``),
sync (``cluster_sync_schemas.py``), nodes (``cluster_nodes_schemas.py``) and
the provision and delete workflows (``cluster_workflows_schemas.py``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import MAX_FILE_BYTES, DriftStateOut, FlavorUpdateOut, _In, _iso
from wingman_day1.application.clusters import ClusterFile
from wingman_day1.application.drift import ClusterDrift
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.cluster_file import ClusterValues, NodePoolValues
from wingman_day1.domain.names import ClusterNaming, HostedClusterRef, NameSuggestion
from wingman_day1.domain.network import segment_of
from wingman_day1.domain.placement import MAX_REASON
from wingman_day1.domain.segments_manager import SegmentsManagerLinks


class NamingOut(BaseModel):
    """Whether a cluster name follows ``ocp4-<env>-<name>-<site>[-<seq>]``."""

    follows_convention: bool
    env: str | None
    short_name: str | None
    sequence: str | None
    problems: list[str]

    @classmethod
    def of(cls, naming: ClusterNaming) -> NamingOut:
        """From a naming reading."""
        return cls(
            follows_convention=naming.follows_convention,
            env=naming.env.value if naming.env else None,
            short_name=naming.short_name,
            sequence=naming.sequence,
            problems=list(naming.problems),
        )


class NameSuggestionOut(BaseModel):
    """``GET /clusters/name-suggestion``: a free name from a flavor (ADR-0040)."""

    name: str | None
    """``ocp4-<env>-<flavor>-<site>-<letter>``; ``None`` when there is none (``problems``)."""
    env: str | None
    short_name: str
    sequence: str | None
    problems: list[str]

    @classmethod
    def of(cls, suggestion: NameSuggestion) -> NameSuggestionOut:
        """From a suggestion."""
        return cls(
            name=suggestion.name,
            env=suggestion.env.value if suggestion.env else None,
            short_name=suggestion.short_name,
            sequence=suggestion.sequence,
            problems=list(suggestion.problems),
        )


class HostedClusterOut(BaseModel):
    """What the chart renders for the file."""

    cluster_name: str
    name: str
    namespace: str

    @classmethod
    def of(cls, ref: HostedClusterRef) -> HostedClusterOut:
        """From a hosted-cluster reference."""
        return cls(cluster_name=ref.cluster_name, name=ref.name, namespace=ref.namespace)


class ClusterStatusOut(BaseModel):
    """A cluster in the list (the legacy ``ClusterStatus`` plus file facts)."""

    name: str
    site: str
    mce: str
    phase: Literal["Provisioning", "Ready", "Error", "Deleting", "Unknown"] = "Unknown"
    spec_name: str | None
    spec_version: str | None
    created_by: str | None
    """Author of the file's last change (as the legacy service reported it)."""
    created_at: str | None
    is_drifted: bool = False
    mastertag: str | None
    path: str
    hosted_cluster: HostedClusterOut
    naming: NamingOut
    owner: dict[str, str]
    """The file's ``owner`` numbers (merkaz, anaf, mador) as text; ``{}`` when it has none."""
    problems: list[str]
    upgrade_available: str | None = None
    """While upgrades are on, the newest release the cluster's MCE offers above its
    ``mastertag`` (ADR-0034's list); ``null`` when none is, or upgrades are off. A
    suggestion: the upgrade-cluster workflow plans the path (ADR-0055)."""

    @classmethod
    def of(cls, cluster: ClusterFile, *, upgrade_available: str | None = None) -> ClusterStatusOut:
        """From a cluster file, and its upgrade hint."""
        change = cluster.last_change
        owner = cluster.values.owner if cluster.values and cluster.values.owner else {}
        return cls(
            name=cluster.ref.name,
            site=cluster.ref.site,
            mce=cluster.ref.mce,
            spec_name=cluster.provenance.spec_name,
            spec_version=cluster.provenance.spec_version,
            created_by=change.author_name if change else None,
            created_at=_iso(change.authored_at) if change else None,
            mastertag=cluster.values.mastertag if cluster.values else None,
            path=str(cluster.ref.path),
            hosted_cluster=HostedClusterOut.of(cluster.hosted_cluster),
            naming=NamingOut.of(cluster.naming),
            owner={
                str(key): str(value)
                for key, value in owner.items()
                if isinstance(value, str | int) and not isinstance(value, bool)
            },
            problems=list(cluster.problems),
            upgrade_available=upgrade_available,
        )


class RequestedAddonOut(BaseModel):
    """A spec addon requested at create, with the user's override values."""

    team: str
    name: str
    version: str
    override_values: dict[str, Any]

    @classmethod
    def of(cls, addon: RequestedAddon) -> RequestedAddonOut:
        """From a requested addon."""
        return cls(
            team=addon.team,
            name=addon.name,
            version=addon.version,
            override_values=dict(addon.override_values),
        )


class ClusterMetadataOut(BaseModel):
    """The legacy ``metadata`` block, from the file header and its last commit."""

    spec_name: str | None
    spec_version: str | None
    created_by: str
    created_at: str | None
    site: str
    mce: str
    variables: dict[str, Any] = Field(default_factory=dict)
    """Always empty: the inputs of a render are not stored (see the API-changes note)."""
    immutable_paths: list[str] = Field(default_factory=list)
    requested_addons: list[RequestedAddonOut] = Field(default_factory=list)


class NodePoolOut(BaseModel):
    """A ``nodepool[]`` entry."""

    name: str | None
    infra_env_name: str | None
    replicas: int | None
    allow_deletion: Any
    configs: list[str]
    node_labels: dict[str, Any]
    tuning_config: Any

    @classmethod
    def of(cls, pool: NodePoolValues) -> NodePoolOut:
        """From a nodepool entry."""
        return cls(
            name=pool.name,
            infra_env_name=pool.infra_env_name,
            replicas=pool.replicas,
            allow_deletion=pool.allow_deletion,
            configs=list(pool.configs),
            node_labels=dict(pool.node_labels),
            tuning_config=pool.tuning_config,
        )


class NetworkOut(BaseModel):
    """What automation allocated (``vlanId`` and ``dhcp_values.network``), if it has yet."""

    vlan_id: Any
    dhcp_network: str | None
    segment: str | None
    """``dhcp_network`` as its /24 (``10.20.90.0/24``); ``None`` without one (ADR-0039)."""


class ClusterValuesOut(BaseModel):
    """What the cluster file sets."""

    owner: dict[str, Any] | None
    mastertag: str | None
    platform: str
    nodepools: list[NodePoolOut]
    network: NetworkOut
    cluster_name: str | None
    """An explicit ``clusterName`` key, if the file has one."""
    automation_keys: list[str]

    @classmethod
    def of(cls, values: ClusterValues) -> ClusterValuesOut:
        """From cluster values."""
        return cls(
            owner=dict(values.owner) if values.owner is not None else None,
            mastertag=values.mastertag,
            platform=values.platform,
            nodepools=[NodePoolOut.of(p) for p in values.nodepools],
            network=NetworkOut(
                vlan_id=values.vlan_id,
                dhcp_network=values.dhcp_network,
                segment=segment_of(values.dhcp_network),
            ),
            cluster_name=values.cluster_name,
            automation_keys=list(values.automation_keys),
        )


class SegmentsManagerOut(BaseModel):
    """Links to segments-manager for one cluster; its UI cannot open one cluster's segment."""

    url: str
    """The UI: search there for the cluster's ``name``."""
    search_url: str
    """``GET /api/segments/search?q=<name>``: the cluster's segment as JSON."""

    @classmethod
    def of(cls, links: SegmentsManagerLinks) -> SegmentsManagerOut:
        """From the domain links."""
        return cls(url=links.url, search_url=links.search_url)


class ClusterDetailOut(BaseModel):
    """A cluster's file, its values, and where it lives."""

    name: str
    site: str
    mce: str
    yaml: str
    gitlab_url: str
    path: str
    last_commit_id: str
    """Send it back with an edit or delete: a stale one is refused (409)."""
    metadata: ClusterMetadataOut
    values: ClusterValuesOut | None
    hosted_cluster: HostedClusterOut
    naming: NamingOut
    mce_default_mastertag: str | None
    problems: list[str]
    segments_manager: SegmentsManagerOut | None
    """``None`` when neither ``SEGMENTS_MANAGER_UI_URL`` nor ``SEGMENTS_MANAGER_URL`` is set."""


def cluster_detail(
    cluster: ClusterFile,
    *,
    gitlab_url: str,
    mce_default_mastertag: str | None,
    segments_manager: SegmentsManagerLinks | None,
) -> ClusterDetailOut:
    """The detail body for a cluster file."""
    change = cluster.last_change
    return ClusterDetailOut(
        name=cluster.ref.name,
        site=cluster.ref.site,
        mce=cluster.ref.mce,
        yaml=cluster.content,
        gitlab_url=gitlab_url,
        path=str(cluster.ref.path),
        last_commit_id=cluster.last_commit_id,
        metadata=ClusterMetadataOut(
            spec_name=cluster.provenance.spec_name,
            spec_version=cluster.provenance.spec_version,
            created_by=change.author_name if change else "",
            created_at=_iso(change.authored_at) if change else None,
            site=cluster.ref.site,
            mce=cluster.ref.mce,
            requested_addons=[RequestedAddonOut.of(a) for a in cluster.provenance.requested_addons],
        ),
        values=ClusterValuesOut.of(cluster.values) if cluster.values else None,
        hosted_cluster=HostedClusterOut.of(cluster.hosted_cluster),
        naming=NamingOut.of(cluster.naming),
        mce_default_mastertag=mce_default_mastertag,
        problems=list(cluster.problems),
        segments_manager=SegmentsManagerOut.of(segments_manager) if segments_manager else None,
    )


class PlacementChoiceIn(_In):
    """What the form showed of MCE placement, and an override's reason (ADR-0050)."""

    pick: str | None = Field(default=None, min_length=1, max_length=63)
    """Wingman's pick when the form showed it."""
    reason: str | None = Field(default=None, max_length=2 * MAX_REASON)
    """Why an admin chose ``mce`` instead of the pick; folded to one line, at most 500."""


class CreateClusterIn(_In):
    """Create a cluster from a spec. ``variables`` are the template's inputs."""

    name: str = Field(min_length=1, max_length=63)
    site: str = Field(min_length=1, max_length=63)
    mce: str = Field(min_length=1, max_length=63)
    spec_name: str = Field(min_length=1, max_length=63)
    spec_version: str = Field(min_length=1, max_length=64)
    variables: dict[str, Any] = Field(default_factory=dict)
    addon_overrides: dict[str, dict[str, Any]] | None = None
    """Override values per spec addon, keyed ``team/name``."""
    placement: PlacementChoiceIn | None = None
    """With placement on: the pick the form showed and, to choose another MCE, a reason."""


class PreviewOut(BaseModel):
    """The file a create would commit."""

    yaml: str
    path: str


class ModifyClusterIn(_In):
    """A new content for a cluster file (the raw editor)."""

    updated_yaml: str = Field(min_length=1, max_length=MAX_FILE_BYTES)
    change_summary: str = Field(default="Cluster modification", max_length=2000)
    last_commit_id: str | None = Field(default=None, min_length=7, max_length=64)
    """The ``last_commit_id`` of the detail the edit started from."""


class DriftSummaryItemOut(BaseModel):
    """One row of ``GET /clusters/drift-summary``."""

    name: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    error: str | None
    spec_name: str | None
    spec_version: str | None
    update: FlavorUpdateOut | None

    @classmethod
    def of(cls, drift: ClusterDrift) -> DriftSummaryItemOut:
        """From a drift verdict."""
        return cls(
            name=drift.ref.name,
            site=drift.ref.site,
            mce=drift.ref.mce,
            state=drift.state.value,
            is_drifted=drift.is_drifted,
            error=drift.error,
            spec_name=drift.spec_name,
            spec_version=drift.spec_version,
            update=FlavorUpdateOut.of(drift.update),
        )
