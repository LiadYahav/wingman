"""The bodies of ``/api/day2`` clusters: their charts, installs, edits and values previews."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from wingman_core.domain.git import Commit
from wingman_day2.api.v1.schemas import FileChangeOut, FindingOut, MRDetailOut, _Input, findings
from wingman_day2.application.catalog import ChartValues
from wingman_day2.application.changes import ChangeResult
from wingman_day2.application.installed import ClusterCharts, InstalledChart
from wingman_day2.application.preview import ValuesPreview
from wingman_day2.application.topology import ClusterSummary
from wingman_day2.domain.deploy_config import LeafApplication
from wingman_day2.domain.platform import ExcludedDefault
from wingman_day2.domain.stacks import LayerRole

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
    override_path: str | None = Field(
        default=None,
        description="The stack layer override_values replaces; the cluster's own file when absent.",
    )


# ── Responses ───────────────────────────────────────────────────────────────


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
