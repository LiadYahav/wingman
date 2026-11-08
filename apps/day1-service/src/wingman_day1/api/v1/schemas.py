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
from wingman_core.domain.git import Commit, FileDiff
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.users import User
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.audit import AuditCommit
from wingman_day1.application.clusters import ClusterFile
from wingman_day1.application.drift import ClusterDrift
from wingman_day1.application.machine_configs import MachineConfigOverview
from wingman_day1.application.sites import MceView
from wingman_day1.application.specs import SpecEntry
from wingman_day1.domain.addons import AddonDrift, RequestedAddon, VersionDifference
from wingman_day1.domain.cluster_file import ClusterValues, NodePoolValues
from wingman_day1.domain.machine_configs import NETWORK_CONFIG
from wingman_day1.domain.names import ClusterNaming, HostedClusterRef
from wingman_day1.domain.paths import NODEPOOL_DEFAULTS_FILE
from wingman_day1.domain.specs import ClusterSpec, SpecBody, SpecMetadata, rule_problems
from wingman_day1.domain.status import LiveStatus

MAX_FILE_BYTES = 256 * 1024
NO_SPEC = None


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


class FileDiffOut(BaseModel):
    """One file of a diff."""

    old_path: str
    new_path: str
    diff: str
    new_file: bool
    renamed_file: bool
    deleted_file: bool

    @classmethod
    def of(cls, diff: FileDiff) -> FileDiffOut:
        """From a domain diff."""
        return cls(
            old_path=str(diff.old_path),
            new_path=str(diff.new_path),
            diff=diff.diff,
            new_file=diff.new_file,
            renamed_file=diff.renamed_file,
            deleted_file=diff.deleted_file,
        )


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
    problems: list[str]

    @classmethod
    def of(cls, cluster: ClusterFile) -> ClusterStatusOut:
        """From a cluster file."""
        change = cluster.last_change
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
            network=NetworkOut(vlan_id=values.vlan_id, dhcp_network=values.dhcp_network),
            cluster_name=values.cluster_name,
            automation_keys=list(values.automation_keys),
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


def cluster_detail(
    cluster: ClusterFile, *, gitlab_url: str, mce_default_mastertag: str | None
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
    """A NodePool's replicas and problems."""

    name: str
    ready_replicas: int
    desired_replicas: int
    problems: list[str]


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

    @classmethod
    def of(cls, entry: SpecEntry) -> SpecOut:
        """From a catalog entry."""
        if entry.spec is not None:
            return cls.model_validate(
                {
                    **entry.spec.model_dump(),
                    "last_commit_id": entry.last_commit_id,
                    "warnings": rule_problems(entry.spec),
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
    installed_version: str
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
            installed_version=drift.installed_version,
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
    unified_diff: str = ""
    addon_drift: list[AddonDriftOut]
    """Spec addons the cluster does not have: what makes it ``drifted``."""
    version_differences: list[VersionDifferenceOut] = Field(default_factory=list)
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


class SpecDriftOut(BaseModel):
    """A spec's cluster drift (``GET /specs/{name}/drift``)."""

    cluster: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    spec_version: str | None
    unified_diff: str = ""
    error: str | None
