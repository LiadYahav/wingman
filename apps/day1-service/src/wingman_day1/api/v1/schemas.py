"""Request and response bodies of the day1 API.

Request bodies forbid unknown fields, so a misspelt field is an error, not
a silently ignored value. Response shapes keep the legacy JSON wherever the
meaning is unchanged; every deliberate change is listed in
``docs/notes/2026-11-07-day1-api-changes.md``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from wingman_core.application.approvals import describe
from wingman_core.domain.git import Commit
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.users import User
from wingman_core.web.schemas import FileDiffOut
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.audit import AuditCommit
from wingman_day1.application.clusters import ClusterFile
from wingman_day1.application.drift import ClusterDrift
from wingman_day1.application.imports import ImportCandidate, ImportPreview
from wingman_day1.application.machine_configs import MachineConfigOverview
from wingman_day1.application.nodes import ClusterNodes
from wingman_day1.application.sites import MceView
from wingman_day1.application.specs import SpecEntry
from wingman_day1.application.sync import SyncPlan
from wingman_day1.domain.addons import AddonDrift, RequestedAddon, VersionDifference
from wingman_day1.domain.cluster_file import ClusterValues, NodePoolValues
from wingman_day1.domain.locks import MISSING
from wingman_day1.domain.machine_configs import NETWORK_CONFIG
from wingman_day1.domain.names import ClusterNaming, HostedClusterRef
from wingman_day1.domain.network import NetworkView, SegmentRecord, segment_of
from wingman_day1.domain.node_pools import NodePoolView, NodeView
from wingman_day1.domain.openshift_versions import OpenShiftVersions
from wingman_day1.domain.paths import NODEPOOL_DEFAULTS_FILE
from wingman_day1.domain.segments_manager import SegmentsManagerLinks
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.specs import ClusterSpec, SpecBody, SpecMetadata, rule_problems
from wingman_day1.domain.status import LiveStatus
from wingman_day1.domain.value_drift import ValueDrift
from wingman_day1.domain.workflows import WorkflowRun

MAX_FILE_BYTES = 256 * 1024


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# ── Auth ─────────────────────────────────────────────────────────────────────


class UserOut(BaseModel):
    """The legacy ``UserInfo``."""

    username: str
    groups: list[str]
    uid: str
    full_name: str
    role: Literal["admin", "viewer"]

    @classmethod
    def of(cls, user: User) -> UserOut:
        """From a session user."""
        return cls(
            username=user.username,
            groups=list(user.groups),
            uid=user.uid,
            full_name=user.full_name,
            role=user.role.value,
        )


class AuthConfigOut(BaseModel):
    """Where the login page sends the browser."""

    authorize_url: str
    dev_auth_enabled: bool = False


class CallbackIn(_In):
    """The OAuth code the login page received."""

    code: str = Field(min_length=1, max_length=4096)


class DevLoginIn(_In):
    """Dev login: the secret is required (``DEV_AUTH_SECRET``)."""

    username: str = Field(min_length=1, max_length=64)
    role: str = "admin"
    secret: str = Field(default="", max_length=1024)


class SessionOut(BaseModel):
    """A session token and its user."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth token type, not a secret
    user: UserOut


# ── Merge requests ───────────────────────────────────────────────────────────


class MRAuthorOut(BaseModel):
    """Who asked for the change (the description footer), not the service account."""

    username: str
    name: str
    avatar_url: str = ""


class MRDetailOut(BaseModel):
    """A merge request, in the legacy ``MRDetail`` shape plus ``project_id``, ``sha``."""

    iid: int
    project_id: int
    title: str
    description: str
    author: MRAuthorOut
    state: Literal["opened", "closed", "merged", "locked"]
    created_at: str
    updated_at: str
    merged_at: str | None
    web_url: str
    source_branch: str
    target_branch: str
    labels: list[str]
    repo: Literal["day1", "specs"]
    has_conflicts: bool | None
    sha: str
    """The source branch head: pass it back to approve exactly what was reviewed."""

    @classmethod
    def of(cls, change: Change) -> MRDetailOut:
        """From a managed change."""
        mr = change.pending.merge_request
        return cls(
            iid=mr.ref.iid,
            project_id=mr.ref.project_id,
            title=mr.title,
            description=mr.description,
            author=MRAuthorOut(
                username=change.pending.requested_by, name=change.pending.requested_by
            ),
            state=mr.state.value,
            created_at=mr.created_at.isoformat(),
            updated_at=mr.updated_at.isoformat(),
            merged_at=_iso(mr.merged_at),
            web_url=mr.web_url,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            labels=list(mr.labels),
            repo=change.repo.value,
            has_conflicts=mr.has_conflicts,
            sha=mr.sha,
        )


def change_out(repo: RepoKey, merge_request: MergeRequest) -> MRDetailOut:
    """The response for an MR a change just opened."""
    return MRDetailOut.of(Change(repo, describe(merge_request)))


class ApprovalDetailOut(BaseModel):
    """An MR and its diff."""

    mr: MRDetailOut
    diffs: list[FileDiffOut]


class ApproveIn(_In):
    """The commit the approver reviewed (``mr.sha`` from the detail)."""

    sha: str = Field(min_length=7, max_length=64)


class UpdateMRFileIn(_In):
    """One edited file."""

    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=MAX_FILE_BYTES)


class UpdateMRIn(_In):
    """Edited files to commit on the MR's branch."""

    files: list[UpdateMRFileIn] = Field(min_length=1, max_length=50)
    message: str = Field(default="", max_length=2000)
    sha: str | None = Field(default=None, min_length=7, max_length=64)
    """The head the editor reviewed; the commit is refused if the branch moved."""


# ── History ──────────────────────────────────────────────────────────────────


class CommitOut(BaseModel):
    """A commit in a file's history (the legacy shape)."""

    sha: str
    short_sha: str
    message: str
    author: str
    date: str
    web_url: str

    @classmethod
    def of(cls, commit: Commit) -> CommitOut:
        """From a domain commit."""
        return cls(
            sha=commit.id,
            short_sha=commit.short_id,
            message=commit.title,
            author=commit.author_name,
            date=commit.authored_at.isoformat(),
            web_url=commit.web_url,
        )


class CommitRecordOut(BaseModel):
    """A commit in the audit list (the legacy ``CommitRecord`` plus ``repo``)."""

    id: str
    short_id: str
    title: str
    author_name: str
    author_email: str
    authored_date: str
    message: str
    web_url: str
    repo: Literal["day1", "specs"]

    @classmethod
    def of(cls, item: AuditCommit) -> CommitRecordOut:
        """From an audit commit."""
        commit = item.commit
        return cls(
            id=commit.id,
            short_id=commit.short_id,
            title=commit.title,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_date=commit.authored_at.isoformat(),
            message=commit.message,
            web_url=commit.web_url,
            repo=item.repo.value,
        )


# ── Sites and MCEs ───────────────────────────────────────────────────────────


class MceOut(BaseModel):
    """An MCE folder (read-only) and what its files say."""

    name: str
    site: str
    env: str | None
    letter: str | None
    follows_convention: bool
    naming_problems: list[str]
    default_mastertag: str | None
    hub_version: str | None
    cluster_count: int
    stray_files: list[str]
    problems: list[str]

    @classmethod
    def of(cls, view: MceView) -> MceOut:
        """From an MCE view."""
        return cls(
            name=view.name,
            site=view.site,
            env=view.naming.env.value if view.naming.env else None,
            letter=view.naming.letter,
            follows_convention=view.naming.follows_convention,
            naming_problems=list(view.naming.problems),
            default_mastertag=view.default_mastertag,
            hub_version=view.hub_version,
            cluster_count=view.cluster_count,
            stray_files=list(view.stray_files),
            problems=list(view.problems),
        )


class OpenShiftVersionsOut(BaseModel):
    """The releases a new cluster on an MCE may use, newest first (ADR-0034)."""

    mce: str
    versions: list[str]
    problems: list[str]
    """Why ``versions`` may be short or empty: a missing or broken ``upgrade/`` file."""

    @classmethod
    def of(cls, offered: OpenShiftVersions) -> OpenShiftVersionsOut:
        """From the domain result."""
        return cls(
            mce=offered.mce, versions=list(offered.versions), problems=list(offered.problems)
        )


# ── Clusters ─────────────────────────────────────────────────────────────────


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

    @classmethod
    def of(cls, cluster: ClusterFile) -> ClusterStatusOut:
        """From a cluster file."""
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


class SegmentLedgerOut(BaseModel):
    """What segments-manager records for the cluster's segment."""

    vlan_id: int | None
    cluster_name: str | list[str] | None
    """The cluster it is allocated to; a list for a shared ``UPI`` segment."""
    status: str | None
    type: str | None
    site: str | None

    @classmethod
    def of(cls, record: SegmentRecord) -> SegmentLedgerOut:
        """From segments-manager's record."""
        holder = record.cluster_name
        return cls(
            vlan_id=record.vlan_id,
            cluster_name=list(holder) if isinstance(holder, tuple) else holder,
            status=record.status,
            type=record.type,
            site=record.site,
        )


class ClusterNetworkOut(BaseModel):
    """``GET /clusters/{name}/network``: the file's network, the EPG, and what disagrees."""

    vlan_id: int | None
    """The file's ``vlanId``."""
    segment: str | None
    """The file's ``dhcp_values.network`` as its /24; ``None`` until it is allocated."""
    epg: str | None
    """segments-manager's ``epg_name`` for the segment."""
    ledger: SegmentLedgerOut | None
    """``None`` when segments-manager is off, failed (``ledger_error``) or has no such segment."""
    problems: list[str]
    """What segments-manager says that disagrees with the file, one sentence each."""
    ledger_error: str | None

    @classmethod
    def of(cls, view: NetworkView) -> ClusterNetworkOut:
        """From the network view."""
        return cls(
            vlan_id=view.vlan_id,
            segment=view.segment,
            epg=view.epg,
            ledger=SegmentLedgerOut.of(view.ledger) if view.ledger else None,
            problems=list(view.problems),
            ledger_error=view.ledger_error,
        )


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


class BulkStatusItemIn(_In):
    """One cluster to read live status for."""

    name: str = Field(min_length=1, max_length=63)
    mce: str = Field(min_length=1, max_length=63)


class BulkStatusIn(_In):
    """Many clusters at once."""

    clusters: list[BulkStatusItemIn] = Field(max_length=500)


class NodePoolStatusOut(BaseModel):
    """A NodePool's replicas, problems, and the update rolling through it."""

    name: str
    ready_replicas: int
    desired_replicas: int
    problems: list[str]
    updating: str | None = None
    """``version``, ``config`` or ``machine_template`` while an update rolls through it."""


class ClusterLiveStatusOut(BaseModel):
    """The legacy ``ClusterLiveStatus`` plus the HostedCluster that was read."""

    cluster_name: str
    hosted_cluster: str
    namespace: str
    hc_phase: str | None
    ocp_version: str | None
    hc_problems: list[str]
    node_pools: list[NodePoolStatusOut]
    error: str | None

    @classmethod
    def of(cls, status: LiveStatus) -> ClusterLiveStatusOut:
        """From a live status."""
        return cls(
            cluster_name=status.cluster_name,
            hosted_cluster=status.hosted_cluster,
            namespace=status.namespace,
            hc_phase=status.hc_phase,
            ocp_version=status.ocp_version,
            hc_problems=list(status.hc_problems),
            node_pools=[
                NodePoolStatusOut(
                    name=p.name,
                    ready_replicas=p.ready_replicas,
                    desired_replicas=p.desired_replicas,
                    problems=list(p.problems),
                    updating=p.updating,
                )
                for p in status.node_pools
            ],
            error=status.error,
        )


# ── Specs ────────────────────────────────────────────────────────────────────


class SpecOut(ClusterSpec):
    """A spec as the API returns it: ``day1.template`` filled, plus any load error."""

    load_error: str | None = None
    """Set for a spec file that does not parse; the rest is then a placeholder."""
    load_problems: list[str] = Field(default_factory=list)
    last_commit_id: str | None = None
    """The commit that last changed the file: send it back with an edit or delete."""
    warnings: list[str] = Field(default_factory=list)
    """Flavor rules the stored spec breaks: it loads, but a save would be refused."""
    enforced_locks: list[str] = Field(default_factory=list)
    """The ``locked_paths`` a create enforces: a stored lock that breaks the rules is not one."""

    @classmethod
    def of(cls, entry: SpecEntry) -> SpecOut:
        """From a catalog entry."""
        if entry.spec is not None:
            return cls.model_validate(
                {
                    **entry.spec.model_dump(),
                    "last_commit_id": entry.last_commit_id,
                    "warnings": rule_problems(entry.spec),
                    "enforced_locks": [str(lock.path) for lock in entry.spec.locks()],
                }
            )
        error = entry.error
        return cls.model_construct(
            metadata=SpecMetadata.model_construct(
                name=entry.name, description="", version="", labels={}
            ),
            spec=SpecBody(),
            load_error=str(error) if error else "unreadable",
            load_problems=list(error.problems) if error else [],
            last_commit_id=entry.last_commit_id,
        )


# ── Machine configs ──────────────────────────────────────────────────────────


class StaticConfigOut(BaseModel):
    """A static config a nodepool may name: ``{name: <name>}``."""

    name: str
    folder: str
    """Its folder under ``mc-files/``; ``""`` for the root."""
    path: str


class HardwareTypeOut(BaseModel):
    """A hardware type for ``{name: nm-conf, hardware: <name>}``."""

    name: str
    template: str


class NodepoolDefaultsOut(BaseModel):
    """``nodepool-defaults.yaml``: the entries a new nodepool starts with."""

    path: str
    found: bool
    """``false``: the specs project has no such file, so there are no defaults."""
    configs: list[dict[str, str]]
    """Entries in the template-input shape; ``hardware`` is absent when the nodepool picks it."""
    error: str | None
    """Set when the file exists but cannot be used; ``configs`` is then empty."""
    problems: list[str]
    """With ``error``: why. Without: the entries that would not resolve."""


class MachineConfigsOut(BaseModel):
    """``GET /api/day1/machine-configs``: the catalogue and the nodepool defaults."""

    network_config: str
    static_configs: list[StaticConfigOut]
    hardware_types: list[HardwareTypeOut]
    nodepool_defaults: NodepoolDefaultsOut
    problems: list[str]
    """Files in ``mc-files/`` that are not offered, and why."""

    @classmethod
    def of(cls, overview: MachineConfigOverview) -> MachineConfigsOut:
        """From the overview."""
        catalog, reading = overview.catalog, overview.defaults
        error = reading.error
        return cls(
            network_config=NETWORK_CONFIG,
            static_configs=[
                StaticConfigOut(name=c.name, folder=c.folder, path=str(c.path))
                for c in catalog.static_configs()
            ],
            hardware_types=[
                HardwareTypeOut(name=h.name, template=str(h.template))
                for h in catalog.hardware_types()
            ],
            nodepool_defaults=NodepoolDefaultsOut(
                path=str(NODEPOOL_DEFAULTS_FILE),
                found=reading.found,
                configs=[e.to_input() for e in reading.defaults.configs],
                error=str(error) if error else None,
                problems=list(error.problems) if error else list(overview.defaults_problems),
            ),
            problems=list(catalog.problems),
        )


# ── Drift ────────────────────────────────────────────────────────────────────


class AddonDriftOut(BaseModel):
    """A spec addon the cluster does not have; install it at the team default."""

    addon_name: str
    team: str
    reason: Literal["missing"]
    expected_version: str
    override_values: dict[str, Any]
    """The values requested at create; install with them."""

    @classmethod
    def of(cls, drift: AddonDrift) -> AddonDriftOut:
        """From addon drift."""
        return cls(
            addon_name=drift.name,
            team=drift.team,
            reason=drift.reason.value,
            expected_version=drift.expected_version,
            override_values=dict(drift.override_values),
        )


class VersionDifferenceOut(BaseModel):
    """A spec addon installed at another version: information, not drift (ADR-0025)."""

    addon_name: str
    team: str
    spec_version: str
    installed_version: str

    @classmethod
    def of(cls, difference: VersionDifference) -> VersionDifferenceOut:
        """From a version difference."""
        return cls(
            addon_name=difference.name,
            team=difference.team,
            spec_version=difference.spec_version,
            installed_version=difference.installed_version,
        )


class NodepoolRefOut(BaseModel):
    """A nodepool of the cluster file: its position and the NodePool the chart renders."""

    index: int
    name: str


class ValueDriftOut(BaseModel):
    """A locked value the cluster file does not hold (ADR-0036)."""

    path: str
    """The flavor's locked path: ``owner_anaf``, ``nodepools[0].configs`` or the rule."""
    file_key: str
    """Where it is in the file: ``owner.anaf``, ``nodepool[1].configs``."""
    nodepool: NodepoolRefOut | None
    flavor_value: Any
    """The locked value in the file's form (``nm-conf`` expanded for this cluster)."""
    cluster_value: Any
    """What the file holds; ``null`` with ``in_file: false`` when the key is absent."""
    in_file: bool
    added: list[str]
    """Configs only: the names a sync adds."""
    removed: list[str]
    """Configs only: the names a sync removes."""
    needs_decision: str | None
    """Set when a person must decide before sync can set this value."""
    needs_hardware: bool
    """The decision is the nodepool's network hardware: a sync can send it in ``hardware``."""
    reboots: bool
    """A nodepool's configs: syncing them rolls its nodes (drain and reboot, or replace)."""

    @classmethod
    def of(cls, drift: ValueDrift) -> ValueDriftOut:
        """From a value drift."""
        in_file = drift.cluster_value is not MISSING
        return cls(
            path=str(drift.lock),
            file_key=str(drift.file_key),
            nodepool=NodepoolRefOut(index=drift.nodepool.index, name=drift.nodepool.name)
            if drift.nodepool
            else None,
            flavor_value=drift.flavor_value,
            cluster_value=drift.cluster_value if in_file else None,
            in_file=in_file,
            added=list(drift.added),
            removed=list(drift.removed),
            needs_decision=drift.needs_decision,
            needs_hardware=drift.needs_hardware,
            reboots=drift.is_configs,
        )


DriftStateOut = Literal["in_sync", "drifted", "unknown", "not_linked"]


class ClusterDriftOut(BaseModel):
    """A cluster's drift (``GET /clusters/{name}/drift``)."""

    cluster: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    """``null`` when it could not be determined; ``error`` says why."""
    spec_name: str | None
    spec_version: str | None
    current_spec_version: str | None
    value_drift: list[ValueDriftOut]
    """Locked values the file does not hold: one of the two things that make it ``drifted``."""
    addon_drift: list[AddonDriftOut]
    """Spec addons the cluster does not have: the other thing that makes it ``drifted``."""
    version_differences: list[VersionDifferenceOut]
    """Spec addons at another version; reported only, never fixed (ADR-0025)."""
    error: str | None

    @classmethod
    def of(cls, drift: ClusterDrift) -> ClusterDriftOut:
        """From a drift verdict."""
        return cls(
            cluster=drift.ref.name,
            site=drift.ref.site,
            mce=drift.ref.mce,
            state=drift.state.value,
            is_drifted=drift.is_drifted,
            spec_name=drift.spec_name,
            spec_version=drift.spec_version,
            current_spec_version=drift.current_spec_version,
            value_drift=[ValueDriftOut.of(d) for d in drift.value_drift],
            addon_drift=[AddonDriftOut.of(d) for d in drift.addon_drift],
            version_differences=[VersionDifferenceOut.of(d) for d in drift.version_differences],
            error=drift.error,
        )


class DriftSummaryItemOut(BaseModel):
    """One row of ``GET /clusters/drift-summary``."""

    name: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    error: str | None

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
        )


class SpecClusterOut(BaseModel):
    """A cluster created from a spec (``GET /specs/{name}/clusters``)."""

    name: str
    site: str
    mce: str
    phase: str = "Unknown"
    state: DriftStateOut
    is_drifted: bool | None
    error: str | None


MAX_PICKED = 500
"""A request-size bound; the import itself takes at most ``imports.MAX_IMPORT``."""


class ClusterPickIn(_In):
    """A cluster to compare with a flavor; ``site`` and ``mce`` only when the name is ambiguous."""

    name: str = Field(min_length=1, max_length=63)
    site: str | None = Field(default=None, min_length=1, max_length=63)
    mce: str | None = Field(default=None, min_length=1, max_length=63)


class ImportPreviewIn(_In):
    """The clusters to preview an import of."""

    clusters: list[ClusterPickIn] = Field(min_length=1, max_length=MAX_PICKED)


class ImportPickIn(_In):
    """A cluster to import, as the preview returned it."""

    name: str = Field(min_length=1, max_length=63)
    site: str = Field(min_length=1, max_length=63)
    mce: str = Field(min_length=1, max_length=63)
    last_commit_id: str = Field(min_length=7, max_length=64)
    """The preview's ``last_commit_id``: a file that moved since fails the import."""
    relink: bool = False
    """``true`` to link a cluster that follows another flavor to this one instead."""


class ImportIn(_In):
    """Link existing clusters to the flavor: one day1 MR."""

    spec_version: str = Field(min_length=1, max_length=64)
    """The flavor version the preview showed."""
    clusters: list[ImportPickIn] = Field(min_length=1, max_length=MAX_PICKED)


class LinkedSpecOut(BaseModel):
    """The flavor a cluster file's header names."""

    name: str
    version: str | None


class ImportCandidateOut(BaseModel):
    """One picked cluster in an import preview."""

    name: str
    site: str
    mce: str
    path: str
    last_commit_id: str
    """Send it back with the import."""
    status: Literal["ready", "relink", "linked", "refused"]
    linked_spec: LinkedSpecOut | None
    """The flavor the file follows now, if any."""
    problems: list[str]
    """Why it cannot be imported as it is (empty for ``ready``)."""
    drift: ClusterDriftOut
    """The cluster against this flavor: what will show as drift once it is linked."""

    @classmethod
    def of(cls, candidate: ImportCandidate) -> ImportCandidateOut:
        """From an import candidate."""
        cluster = candidate.cluster
        provenance = cluster.provenance
        return cls(
            name=cluster.ref.name,
            site=cluster.ref.site,
            mce=cluster.ref.mce,
            path=str(cluster.ref.path),
            last_commit_id=cluster.last_commit_id,
            status=candidate.status.value,
            linked_spec=LinkedSpecOut(name=provenance.spec_name, version=provenance.spec_version)
            if provenance.spec_name
            else None,
            problems=list(candidate.problems),
            drift=ClusterDriftOut.of(candidate.drift),
        )


class ImportPreviewOut(BaseModel):
    """``POST /specs/{name}/import/preview``."""

    spec_name: str
    spec_version: str
    """Send it back with the import."""
    warnings: list[str]
    """About the flavor: locks by nodepool position, which compare whichever nodepool is there."""
    clusters: list[ImportCandidateOut]

    @classmethod
    def of(cls, preview: ImportPreview) -> ImportPreviewOut:
        """From an import preview."""
        return cls(
            spec_name=preview.spec_name,
            spec_version=preview.spec_version,
            warnings=list(preview.warnings),
            clusters=[ImportCandidateOut.of(c) for c in preview.candidates],
        )


# ── Sync (ADR-0037) ──────────────────────────────────────────────────────────


class HardwareChoiceIn(_In):
    """A person's choice of network hardware for a nodepool whose own cannot be read."""

    nodepool: int = Field(ge=0, lt=100)
    """The nodepool's position in the file (``nodepool[i]``)."""
    hardware: str = Field(min_length=1, max_length=63)
    """A type from ``GET /machine-configs``; the file gets ``nm-conf-<clusterName>-<hw>``."""


class ConfigRemovalIn(_In):
    """A config the sync removes, confirmed by the person who asked for it."""

    nodepool: int = Field(ge=0, lt=100)
    name: str = Field(min_length=1, max_length=253)


class SyncPreviewIn(_In):
    """``POST /clusters/{name}/sync/preview``: the hardware choices, if drift needs them."""

    hardware: list[HardwareChoiceIn] = Field(default_factory=list, max_length=100)


class SyncIn(SyncPreviewIn):
    """``POST /clusters/{name}/sync``: what the preview showed, and the removals confirmed."""

    last_commit_id: str = Field(min_length=7, max_length=64)
    """The preview's: a file that changed since fails the sync."""
    spec_version: str = Field(min_length=1, max_length=64)
    """The flavor version the preview showed."""
    confirm_removals: list[ConfigRemovalIn] = Field(default_factory=list, max_length=1000)
    """Exactly the preview's ``removals``: the sync is refused otherwise."""


class ConfigRemovalOut(BaseModel):
    """A config a sync removes from a nodepool."""

    nodepool: NodepoolRefOut
    name: str


class RebootingOut(BaseModel):
    """A nodepool whose configs a sync changes: merging rolls its nodes."""

    nodepool: NodepoolRefOut
    replicas: int | None
    upgrade_type: str | None
    """The nodepool's ``upgradeType``; ``null`` when unset (the chart's ``InPlace``)."""
    max_unavailable: int | str | None
    """The nodepool's ``inPlace.maxUnavailable``; ``null`` when unset (one node at a time)."""
    replaces_nodes: bool
    """``upgradeType: Replace``: new nodes are provisioned and the old ones removed."""


class SyncPreviewOut(BaseModel):
    """``POST /clusters/{name}/sync/preview``: what syncing the cluster to its flavor would do."""

    cluster: str
    site: str
    mce: str
    path: str
    last_commit_id: str
    """Send it back with the sync."""
    spec_name: str
    spec_version: str
    """The flavor's current version; send it back with the sync."""
    file_spec_version: str | None
    """The version the file's header names now."""
    changes: list[ValueDriftOut]
    """Every locked value the file does not hold, with the hardware choices applied."""
    diff: str
    """The cluster file change, as a unified diff (empty when nothing changes)."""
    removals: list[ConfigRemovalOut]
    """Configs the sync removes; send each back in ``confirm_removals``."""
    rebooting: list[RebootingOut]
    """Nodepools whose configs change: merging reboots their nodes, rolling."""
    problems: list[str]
    """Why the sync cannot run now: a decision a person must make, a layout Wingman can't edit."""
    warnings: list[str]
    """Worth checking before merging; they do not block the sync."""
    can_sync: bool
    """No problems, and the file changes."""
    addons_to_install: list[AddonDriftOut]
    """Missing add-ons: not in the day1 MR; install them through day2."""
    version_differences: list[VersionDifferenceOut]
    addons_error: str | None
    """Set when day2 did not answer: missing add-ons are unknown."""

    @classmethod
    def of(cls, plan: SyncPlan) -> SyncPreviewOut:
        """From a sync plan."""
        ref = plan.cluster.ref

        def pool(index: int, name: str) -> NodepoolRefOut:
            return NodepoolRefOut(index=index, name=name)

        return cls(
            cluster=ref.name,
            site=ref.site,
            mce=ref.mce,
            path=str(ref.path),
            last_commit_id=plan.cluster.last_commit_id,
            spec_name=plan.spec.metadata.name,
            spec_version=plan.spec.metadata.version,
            file_spec_version=plan.cluster.provenance.spec_version,
            changes=[ValueDriftOut.of(d) for d in plan.changes],
            diff=plan.diff,
            removals=[
                ConfigRemovalOut(nodepool=pool(r.nodepool.index, r.nodepool.name), name=r.name)
                for r in plan.removals
            ],
            rebooting=[
                RebootingOut(
                    nodepool=pool(r.nodepool.index, r.nodepool.name),
                    replicas=r.replicas,
                    upgrade_type=r.upgrade_type,
                    max_unavailable=r.max_unavailable,
                    replaces_nodes=r.replaces_nodes,
                )
                for r in plan.rebooting
            ],
            problems=list(plan.problems),
            warnings=list(plan.warnings),
            can_sync=not plan.problems and plan.changes_file,
            addons_to_install=[AddonDriftOut.of(a) for a in plan.addons_to_install],
            version_differences=[VersionDifferenceOut.of(d) for d in plan.version_differences],
            addons_error=plan.addons_error,
        )


class SpecDriftOut(BaseModel):
    """A spec's cluster drift (``GET /specs/{name}/drift``)."""

    cluster: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    spec_version: str | None
    error: str | None


# ── The delete-cluster workflow (ADR-0033) ──────────────────────────────────


class WorkflowRunOut(BaseModel):
    """One run of a workflow that acts on a cluster."""

    workflow_id: str
    status: str
    phase: str | None
    error: str | None

    @classmethod
    def of(cls, run: WorkflowRun) -> WorkflowRunOut:
        """From a run."""
        return cls(workflow_id=run.workflow_id, status=run.status, phase=run.phase, error=run.error)


class DeleteWorkflowOut(BaseModel):
    """``GET /clusters/{name}/delete-workflow``: the newest run, if any."""

    run: WorkflowRunOut | None


class StartDeleteWorkflowIn(BaseModel):
    """``POST /clusters/{name}/delete-workflow``: deleting is not reversible, so say so."""

    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]


# ── Cluster nodes by NodePool, and node uninstall (ADR-0038) ─────────────────


class ServerOut(BaseModel):
    """A server, as server-scan reports it."""

    id: str
    name: str
    url: str
    """The server's page in server-scan's UI."""
    serial: str | None
    vendor: str | None
    model: str | None
    site: str | None
    mce: str | None
    state: str
    health: str
    maintenance: bool
    reachable: bool
    stale: bool
    contested: bool
    last_seen_at: str | None

    @classmethod
    def fields_of(cls, row: ServerRow, url: str) -> dict[str, Any]:
        """The server's fields, for this model and its subclasses."""
        return {
            "id": row.id,
            "name": row.name,
            "url": url,
            "serial": row.serial,
            "vendor": row.vendor,
            "model": row.model,
            "site": row.site,
            "mce": row.mce,
            "state": row.state,
            "health": row.health,
            "maintenance": row.maintenance,
            "reachable": row.reachable,
            "stale": row.stale,
            "contested": row.contested,
            "last_seen_at": _iso(row.last_seen_at),
        }


class UnassignedServerOut(ServerOut):
    """A server server-scan places in the cluster that no Machine leads to."""

    uninstall: WorkflowRunOut | None


class AgentOut(BaseModel):
    """The Agent reserved for a Machine."""

    name: str
    state: str | None
    stage: str | None


class NodeOut(BaseModel):
    """One node of a NodePool: a Machine, or one the pool wants and has not got."""

    machine: str | None
    node_name: str | None
    state: str
    current: bool
    activity: str | None
    waiting_for: str | None
    outdated: bool | None
    agent: AgentOut | None
    server_name: str | None
    server: ServerOut | None
    uninstall: WorkflowRunOut | None
    """The server's newest uninstall run; ``null`` when none, or when runs are unknown."""


class AutoscalingOut(BaseModel):
    """A NodePool's autoscaling bounds."""

    min: int
    max: int


class UpdateProgressOut(BaseModel):
    """An in-place update's ``Total Nodes`` and ``Upgraded``."""

    total: int
    updated: int


class PoolUpdateOut(BaseModel):
    """A NodePool update in progress."""

    kind: str
    message: str
    progress: UpdateProgressOut | None
    failed: bool


class FreeAgentsOut(BaseModel):
    """The Agents a NodePool's selector matches, and how many are free."""

    matching: int
    free: int


class NodePoolNodesOut(BaseModel):
    """A NodePool, its update and problems, and its nodes."""

    name: str
    wanted: int | None
    autoscaling: AutoscalingOut | None
    ready: int
    version: str | None
    upgrade_type: str | None
    agent_selector: str | None
    update: PoolUpdateOut | None
    problems: list[str]
    free_agents: FreeAgentsOut | None
    nodes: list[NodeOut]


class UninstallAvailabilityOut(BaseModel):
    """Whether the Uninstall button can be offered, and why not."""

    available: bool
    detail: str | None


class ClusterNodesOut(BaseModel):
    """``GET /clusters/{name}/nodes``: the docs/notes/2026-11-11-cluster-nodes-api.md shape."""

    hosted_cluster: str
    node_pools: list[NodePoolNodesOut]
    unassigned: list[UnassignedServerOut]
    uninstall: UninstallAvailabilityOut
    server_scan_error: str | None
    runs_error: str | None

    @classmethod
    def of(cls, found: ClusterNodes) -> ClusterNodesOut:
        """From a cluster's nodes."""

        def run_of(row: ServerRow | None) -> WorkflowRunOut | None:
            run = found.runs.get(row.id) if row is not None else None
            return WorkflowRunOut.of(run) if run is not None else None

        def server_of(row: ServerRow | None) -> ServerOut | None:
            if row is None:
                return None
            return ServerOut(**ServerOut.fields_of(row, found.server_urls[row.id]))

        def node_of(node: NodeView) -> NodeOut:
            agent = node.agent
            return NodeOut(
                machine=node.machine,
                node_name=node.node_name,
                state=node.state.value,
                current=node.current,
                activity=node.activity,
                waiting_for=node.waiting_for,
                outdated=node.outdated,
                agent=AgentOut(name=agent.name, state=agent.state, stage=agent.stage)
                if agent
                else None,
                server_name=node.server_name,
                server=server_of(node.server),
                uninstall=run_of(node.server),
            )

        def pool_of(pool: NodePoolView) -> NodePoolNodesOut:
            update = pool.update
            progress = update.progress if update else None
            return NodePoolNodesOut(
                name=pool.name,
                wanted=pool.wanted,
                autoscaling=AutoscalingOut(min=pool.autoscaling.min, max=pool.autoscaling.max)
                if pool.autoscaling
                else None,
                ready=pool.ready,
                version=pool.version,
                upgrade_type=pool.upgrade_type,
                agent_selector=pool.agent_selector,
                update=PoolUpdateOut(
                    kind=update.kind,
                    message=update.message,
                    progress=UpdateProgressOut(total=progress.total, updated=progress.updated)
                    if progress
                    else None,
                    failed=update.failed,
                )
                if update
                else None,
                problems=list(pool.problems),
                free_agents=FreeAgentsOut(
                    matching=pool.free_agents.matching, free=pool.free_agents.free
                )
                if pool.free_agents
                else None,
                nodes=[node_of(node) for node in pool.nodes],
            )

        return cls(
            hosted_cluster=found.hosted_cluster,
            node_pools=[pool_of(pool) for pool in found.node_pools],
            unassigned=[
                UnassignedServerOut(
                    **ServerOut.fields_of(row, found.server_urls[row.id]), uninstall=run_of(row)
                )
                for row in found.unassigned
            ],
            uninstall=UninstallAvailabilityOut(
                available=found.uninstall_available, detail=found.uninstall_detail
            ),
            server_scan_error=found.server_scan_error,
            runs_error=found.runs_error,
        )


class UninstallNodeIn(_In):
    """``POST /clusters/{name}/nodes/{server_id}/uninstall``: the node's name, typed again."""

    server_name: str = Field(min_length=1, max_length=253)
