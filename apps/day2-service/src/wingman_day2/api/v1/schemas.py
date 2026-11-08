"""Request and response bodies of ``/api/day2``.

Request bodies refuse unknown fields (``extra="forbid"``): a typo is a 422,
not a silently ignored setting. Response shapes keep the legacy field names
where the meaning is unchanged, and add fields; every change visible to the
web app is listed in ``docs/notes/2026-11-07-day2-api-changes.md``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wingman_core.application.approvals import PendingChange, describe
from wingman_core.domain.git import Commit, FileChange
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.web.schemas import FileDiffOut
from wingman_day2.application.catalog import CatalogEntry, ChartValues
from wingman_day2.application.changes import ChangeResult
from wingman_day2.application.installed import ClusterCharts, InstalledChart
from wingman_day2.application.preview import ValuesPreview
from wingman_day2.application.topology import ClusterSummary
from wingman_day2.domain.deploy_config import LeafApplication
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.platform import ExcludedDefault
from wingman_day2.domain.stacks import LayerRole
from wingman_day2.domain.teams import Team


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Requests ────────────────────────────────────────────────────────────────


class InstallBody(_Input):
    """Install a chart on a cluster."""

    override_values: dict[str, Any] = Field(default_factory=dict)
    version: str | None = Field(
        default=None,
        description="Only honoured if equal to the inherited revision, or with emergency_pin.",
    )
    emergency_pin: bool = False
    repourl: str | None = Field(
        default=None, description="Required only when the team default has no lowercase repourl."
    )
    project_namespace: str | None = None
    message: str | None = Field(default=None, description="Added to the MR description.")


class UpdateBody(_Input):
    """Change a chart's values (and its pin, when asked) on a cluster."""

    override_values: dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    emergency_pin: bool = False
    last_commit_id: str | None = Field(
        default=None, description="The commit the values file was read at; stale means 409."
    )
    message: str | None = None


class BulkItem(_Input):
    """One chart of a bulk install."""

    team: str
    addon: str
    version: str | None = None
    emergency_pin: bool = False
    override_values: dict[str, Any] = Field(default_factory=dict)


class BulkBody(_Input):
    """Several charts on one cluster; one MR per team."""

    addons: list[BulkItem] = Field(min_length=1)
    custom_message: str | None = None


class MergePreviewBody(_Input):
    """Preview a chart's merged values on a cluster, optionally with edited cluster values."""

    team: str
    addon: str
    cluster: str
    mce: str | None = None
    version: str | None = None
    override_values: dict[str, Any] | None = None


class ApproveBody(_Input):
    """Approve and merge the commit that was reviewed."""

    sha: str = Field(min_length=7, description="The MR head the approver reviewed (MRDetail.sha).")


class EditedFile(_Input):
    """New content for a file the MR changes."""

    path: str
    content: str
    last_commit_id: str | None = None


class EditMergeRequestBody(_Input):
    """Push edits onto an MR's branch; ``sha`` is the head the editor reviewed (409 if it moved)."""

    files: list[EditedFile] = Field(min_length=1)
    message: str = ""
    sha: str | None = Field(default=None, min_length=7, max_length=64)


# ── Responses ───────────────────────────────────────────────────────────────


class FindingOut(BaseModel):
    """A lint finding."""

    rule: str
    severity: str
    message: str
    team: str
    path: str
    cluster: str
    chart: str

    @classmethod
    def of(cls, finding: Finding) -> FindingOut:
        """From the domain finding."""
        return cls(
            rule=str(finding.rule),
            severity=str(finding.severity),
            message=finding.message,
            team=finding.team,
            path=finding.path,
            cluster=finding.cluster,
            chart=finding.chart,
        )


def findings(items: tuple[Finding, ...] | list[Finding]) -> list[FindingOut]:
    """Findings as response items."""
    return [FindingOut.of(f) for f in items]


class GitLabInfoOut(BaseModel):
    """Where the team repos live."""

    gitlab_url: str
    sigs_group_path: str
    sigs_group_url: str


class TeamOut(BaseModel):
    """A team and its project."""

    name: str
    project_id: int
    path_with_namespace: str
    web_url: str

    @classmethod
    def of(cls, team: Team) -> TeamOut:
        """From the domain team."""
        return cls(
            name=team.name,
            project_id=team.project.id,
            path_with_namespace=team.project.path_with_namespace,
            web_url=team.project.web_url,
        )


class ArgoMetadataOut(BaseModel):
    """The team default deploy config (legacy name and field spelling)."""

    model_config = ConfigDict(populate_by_name=True)

    project_namespace: str = Field(serialization_alias="projectNamespace")
    repourl: str
    target_revision: str = Field(serialization_alias="targetRevision")
    sync_policy: dict[str, Any] = Field(serialization_alias="syncPolicy")
    path: str


class OcpPinOut(BaseModel):
    """An ``ocp-versions/<version>/`` pin."""

    version: str
    target_revision: str | None


class CatalogEntryOut(BaseModel):
    """A team catalog entry (``operators/<chart>/``)."""

    team: str
    name: str
    available_versions: list[str]
    current_version: str
    default_values: dict[str, Any]
    argocd_metadata: ArgoMetadataOut
    dependencies: list[str] = Field(
        default_factory=list, description="Always empty: day2 has no dependency concept."
    )
    ocp_version_pins: list[OcpPinOut]
    fleet_defaults: list[str]
    chart_project: str | None
    warnings: list[FindingOut]

    @classmethod
    def of(cls, entry: CatalogEntry) -> CatalogEntryOut:
        """From the catalog entry."""
        return cls(
            team=entry.team,
            name=entry.chart,
            available_versions=list(entry.versions or ()),
            current_version=entry.team_revision,
            default_values=entry.values.values,
            argocd_metadata=ArgoMetadataOut(
                project_namespace=entry.project_namespace,
                repourl=entry.repo_url,
                target_revision=entry.team_revision,
                sync_policy=entry.sync_policy,
                path=entry.path,
            ),
            ocp_version_pins=[
                OcpPinOut(version=p.version, target_revision=p.target_revision) for p in entry.pins
            ],
            fleet_defaults=[str(s) for s in entry.fleet_defaults],
            chart_project=entry.chart_project.path_with_namespace if entry.chart_project else None,
            warnings=findings(entry.findings),
        )


class ChartValuesOut(BaseModel):
    """Where chart defaults were read from, or why they were not."""

    project: str | None
    revision: str
    path: str
    problem: str | None

    @classmethod
    def of(cls, chart: ChartValues) -> ChartValuesOut:
        """From the application value."""
        return cls(
            project=chart.project.path_with_namespace if chart.project else None,
            revision=chart.revision,
            path=chart.path,
            problem=chart.problem,
        )


class ClusterOut(BaseModel):
    """One day2 destination."""

    id: str
    kind: str
    name: str
    site: str
    env: str
    mce: str
    ocp_version: str | None
    argo: str
    teams: list[str]
    in_day1: bool
    warnings: list[FindingOut]

    @classmethod
    def of(cls, summary: ClusterSummary) -> ClusterOut:
        """From the cluster summary."""
        ref = summary.ref
        return cls(
            id=ref.id,
            kind=str(ref.kind),
            name=ref.name,
            site=ref.site,
            env=ref.env,
            mce=ref.mce,
            ocp_version=summary.ocp_version,
            argo=ref.argo_instance,
            teams=list(summary.teams),
            in_day1=summary.in_day1,
            warnings=findings(summary.findings),
        )


class LeafOut(BaseModel):
    """The leaf ArgoCD Application the platform generates."""

    app_name: str
    argo: str
    namespace: str
    repo_url: str
    target_revision: str
    path: str
    release_name: str
    destination: str
    destination_namespace: str | None
    sync_policy: Any
    auto_sync: bool

    @classmethod
    def of(cls, leaf: LeafApplication) -> LeafOut:
        """From the domain leaf."""
        return cls(
            app_name=leaf.name,
            argo=leaf.argo,
            namespace=leaf.namespace,
            repo_url=leaf.repo_url,
            target_revision=leaf.target_revision,
            path=leaf.path,
            release_name=leaf.release_name,
            destination=leaf.destination,
            destination_namespace=leaf.destination_namespace,
            sync_policy=leaf.sync_policy,
            auto_sync=leaf.auto_sync,
        )


class InstalledAddonOut(BaseModel):
    """One chart on a cluster (legacy fields first)."""

    team: str
    name: str
    version: str
    override_values: dict[str, Any]
    parse_errors: list[FindingOut] = Field(default_factory=list)
    gitlab_url: str
    source: str
    path: str
    override_path: str
    last_commit_id: str | None
    pinned: bool
    deploy: LeafOut
    warnings: list[FindingOut]

    @classmethod
    def of(cls, chart: InstalledChart) -> InstalledAddonOut:
        """From the installed chart."""
        app = chart.app
        all_findings = chart.findings
        return cls(
            team=app.team,
            name=app.chart,
            version=chart.deploy.leaf.target_revision,
            override_values=chart.override.values,
            parse_errors=findings([f for f in all_findings if str(f.rule) == "yaml-invalid"]),
            gitlab_url=chart.web_url,
            source=str(app.source),
            path=str(app.folder),
            override_path=str(chart.override.layer.path),
            last_commit_id=chart.override.file.last_commit_id if chart.override.file else None,
            pinned=chart.pinned,
            deploy=LeafOut.of(chart.deploy.leaf),
            warnings=findings(all_findings),
        )


class ExcludedOut(BaseModel):
    """A fleet default kept off the cluster by ``exclusions.yaml``."""

    team: str
    name: str
    scope: str

    @classmethod
    def of(cls, excluded: ExcludedDefault) -> ExcludedOut:
        """From the domain value."""
        return cls(team=excluded.team, name=excluded.chart, scope=str(excluded.ref.defaults_scope))


ARGOCD_NOTE = (
    "Installed means the platform generates an ArgoCD app for the chart. Wingman has no ArgoCD "
    "access yet: sync and health are not shown, and leaf apps are manual-sync unless their "
    "syncPolicy is automated."
)


class ClusterInstalledOut(BaseModel):
    """Every chart on a cluster (legacy ``cluster``/``mce``/``installed`` kept)."""

    cluster: str
    mce: str
    id: str
    kind: str
    site: str
    env: str
    ocp_version: str | None
    installed: list[InstalledAddonOut]
    excluded: list[ExcludedOut]
    warnings: list[FindingOut]
    argocd_note: str = ARGOCD_NOTE

    @classmethod
    def of(cls, charts: ClusterCharts) -> ClusterInstalledOut:
        """From the application value."""
        ref = charts.cluster.ref
        return cls(
            cluster=ref.name,
            mce=ref.mce,
            id=ref.id,
            kind=str(ref.kind),
            site=ref.site,
            env=ref.env,
            ocp_version=charts.cluster.ocp_version,
            installed=[InstalledAddonOut.of(c) for c in charts.installed],
            excluded=[ExcludedOut.of(e) for e in charts.excluded],
            warnings=findings(charts.findings),
        )


class LayerOut(BaseModel):
    """One layer of a value stack."""

    role: str
    path: str
    exists: bool
    values: dict[str, Any]
    last_commit_id: str | None
    problem: str | None


class DeployOut(LeafOut):
    """The leaf plus its deploy-config stack and which file set each key."""

    layers: list[LayerOut]
    provenance: dict[str, Any]


class ValuesPreviewOut(BaseModel):
    """The merged values of a chart on a cluster, with provenance (legacy fields first)."""

    merged: dict[str, Any]
    provenance: dict[str, Any]
    chart_values: dict[str, Any]
    team_values: dict[str, Any]
    cluster_values: dict[str, Any]
    addon_name: str
    team: str
    version: str
    cluster: str
    installed: bool
    source: str
    ocp_version: str | None
    chart: ChartValuesOut
    layers: list[LayerOut]
    deploy: DeployOut
    warnings: list[FindingOut]

    @classmethod
    def of(cls, preview: ValuesPreview) -> ValuesPreviewOut:
        """From the preview."""

        def layer(x: Any) -> LayerOut:
            return LayerOut(
                role=str(x.layer.role),
                path=str(x.layer.path),
                exists=x.exists,
                values=x.values,
                last_commit_id=x.file.last_commit_id if x.file else None,
                problem=x.problem.message if x.problem else None,
            )

        leaf = preview.deploy.leaf
        return cls(
            merged=preview.merged.values,
            provenance=preview.merged.provenance,
            chart_values=preview.chart.values,
            team_values=preview.role_values(LayerRole.TEAM),
            cluster_values=preview.role_values(LayerRole.CLUSTER),
            addon_name=preview.app.chart,
            team=preview.app.team,
            version=preview.revision,
            cluster=preview.cluster.ref.id,
            installed=preview.installed,
            source=str(preview.app.source),
            ocp_version=preview.app.ocp_version,
            chart=ChartValuesOut.of(preview.chart),
            layers=[layer(x) for x in preview.layers],
            deploy=DeployOut(
                **LeafOut.of(leaf).model_dump(),
                layers=[layer(x) for x in preview.deploy.layers],
                provenance=preview.deploy.merged.provenance,
            ),
            warnings=findings(preview.findings),
        )


class MRAuthorOut(BaseModel):
    """The person behind an MR (from its footer; GitLab shows Wingman's account)."""

    username: str
    name: str = ""
    avatar_url: str | None = None


class MRDetailOut(BaseModel):
    """A merge request (legacy shape plus ``team``, ``project_id``, ``sha``)."""

    iid: int
    title: str
    description: str
    author: MRAuthorOut
    state: str
    created_at: str
    updated_at: str
    web_url: str
    source_branch: str
    target_branch: str
    labels: list[str]
    repo: str = "day2"
    has_conflicts: bool | None
    team: str
    project_id: int
    sha: str
    gitlab_author: str

    @classmethod
    def of(cls, team: str, merge_request: MergeRequest) -> MRDetailOut:
        """From an MR. ``author`` is the requester its footer names (ADR-0007), not GitLab's."""
        return cls.of_change(team, describe(merge_request))

    @classmethod
    def of_change(cls, team: str, change: PendingChange) -> MRDetailOut:
        """From a described Wingman MR; ``gitlab_author`` keeps the account that opened it."""
        mr = change.merge_request
        return cls(
            iid=mr.ref.iid,
            title=mr.title,
            description=mr.description,
            author=MRAuthorOut(username=change.requested_by),
            state=str(mr.state),
            created_at=mr.created_at.isoformat(),
            updated_at=mr.updated_at.isoformat(),
            web_url=mr.web_url,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            labels=list(mr.labels),
            has_conflicts=mr.has_conflicts,
            team=team,
            project_id=mr.ref.project_id,
            sha=mr.sha,
            gitlab_author=mr.author_username,
        )


class FileChangeOut(BaseModel):
    """One file a change writes."""

    action: str
    path: str

    @classmethod
    def of(cls, change: FileChange) -> FileChangeOut:
        """From the core change."""
        return cls(action=str(change.kind), path=str(change.path))


class ChangeOut(MRDetailOut):
    """An opened MR (an ``MRDetail``) plus what it writes and what to expect."""

    cluster: str
    files: list[FileChangeOut]
    app_names: list[str]
    warnings: list[FindingOut]
    notes: list[str]

    @classmethod
    def of_result(cls, result: ChangeResult) -> ChangeOut:
        """From the change result (its MR's footer names the requester)."""
        base = MRDetailOut.of(result.team, result.merge_request)
        return cls(
            **base.model_dump(),
            cluster=result.cluster.ref.id,
            files=[FileChangeOut.of(c) for c in result.changes],
            app_names=list(result.app_names),
            warnings=findings(result.findings),
            notes=list(result.notes),
        )


class BulkFailureOut(BaseModel):
    """A team whose MR could not be opened after validation passed."""

    team: str
    error: str
    detail: str


class BulkOut(BaseModel):
    """One MR per team."""

    merge_requests: list[ChangeOut]
    failed: list[BulkFailureOut]


class ApprovalDetailOut(BaseModel):
    """An MR and its diff (the legacy ``{mr, diffs}`` shape)."""

    mr: MRDetailOut
    diffs: list[FileDiffOut]


class CommitRecordOut(BaseModel):
    """A commit (legacy audit shape plus ``team``)."""

    id: str
    short_id: str
    title: str
    author_name: str
    author_email: str
    authored_date: str
    message: str
    web_url: str
    team: str
    repo: str = "day2"

    @classmethod
    def of(cls, team: str, commit: Commit) -> CommitRecordOut:
        """From the core commit."""
        return cls(
            id=commit.id,
            short_id=commit.short_id,
            title=commit.title,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_date=commit.authored_at.isoformat(),
            message=commit.message,
            web_url=commit.web_url,
            team=team,
        )


class HistoryEntryOut(BaseModel):
    """A commit in a cluster's history (the legacy ``format_commit`` shape)."""

    sha: str
    short_sha: str
    message: str
    author: str
    date: str
    web_url: str
    team: str

    @classmethod
    def of(cls, team: str, commit: Commit) -> HistoryEntryOut:
        """From the core commit."""
        return cls(
            sha=commit.id,
            short_sha=commit.short_id,
            message=commit.title,
            author=commit.author_name,
            date=commit.authored_at.isoformat(),
            web_url=commit.web_url,
            team=team,
        )


class UpgradeCheckOut(BaseModel):
    """Charts that need an ``ocp-versions/<to>/`` before a cluster moves to ``to``."""

    cluster: str
    from_version: str | None
    to_version: str
    warnings: list[FindingOut]
