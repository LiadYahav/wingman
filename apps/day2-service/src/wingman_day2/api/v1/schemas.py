"""Request and response bodies of ``/api/day2``.

Request bodies refuse unknown fields (``extra="forbid"``): a typo is a 422,
not a silently ignored setting. Response shapes keep the legacy field names
where the meaning is unchanged, and add fields; every change visible to the
web app is listed in ``docs/notes/2026-11-07-day2-api-changes.md`` (add-on
authoring and per-team access: ``docs/notes/2026-11-12-day2-addon-authoring-api.md``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wingman_core.application.approvals import PendingChange, describe
from wingman_core.domain.git import Commit, FileChange
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.web.schemas import FileDiffOut
from wingman_day2.application.apps import LoadedLayer
from wingman_day2.application.authoring import (
    SCOPE_LABELS,
    SCOPE_NOUNS,
    AddonTemplate,
    Adoption,
    AuthoringPlan,
    AuthoringResult,
    DestinationImpact,
    FleetDefault,
    KeyChange,
    NewAddon,
    TeamDefaultEdit,
)
from wingman_day2.application.catalog import CatalogEntry, ChartValues
from wingman_day2.application.changes import ChangeResult
from wingman_day2.application.installed import ClusterCharts, InstalledChart
from wingman_day2.application.operators import (
    DestinationView,
    ExclusionsView,
    OcpVersionPin,
    OperatorSummary,
    OperatorView,
    ScopeView,
)
from wingman_day2.application.preview import ValuesPreview
from wingman_day2.application.topology import ClusterSummary
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.deploy_config import (
    IGNORE_DIFFERENCES,
    PATH,
    PROJECT_NAMESPACE,
    REPOURL,
    SYNC_POLICY,
    TARGET_REVISION,
    LeafApplication,
)
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.platform import ExcludedDefault
from wingman_day2.domain.stacks import LayerRole
from wingman_day2.domain.sync_policy import KNOWN_SYNC_OPTIONS, SyncSettings, sync_settings
from wingman_day2.domain.teams import Team, TeamAccess


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


class SyncIn(_Input):
    """A leaf app's sync options (ADR-0043)."""

    auto_sync: bool = False
    prune: bool = Field(default=False, description="Only with auto_sync.")
    self_heal: bool = Field(default=False, description="Only with auto_sync.")
    sync_options: list[str] = Field(default_factory=list, description="Name=value, in order.")

    def settings(self) -> SyncSettings:
        """The domain settings (checked where they are used)."""
        return SyncSettings(self.auto_sync, self.prune, self.self_heal, tuple(self.sync_options))


class CreateAddonBody(_Input):
    """A new add-on in a team's catalog (``operators/<name>/``), optionally a fleet default."""

    name: str
    repourl: str
    target_revision: str | None = Field(default=None, description="A chart repo branch; HEAD.")
    path: str | None = None
    project_namespace: str | None = None
    sync: SyncIn
    ignore_differences: list[dict[str, Any]] | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    default_scope: DefaultsScope | None = None
    default_values: dict[str, Any] = Field(default_factory=dict)
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None

    def spec(self, team: str) -> NewAddon:
        """The application's request."""
        return NewAddon(
            team=team,
            chart=self.name,
            repourl=self.repourl,
            sync=self.sync.settings(),
            target_revision=self.target_revision,
            path=self.path,
            project_namespace=self.project_namespace,
            ignore_differences=list(self.ignore_differences) if self.ignore_differences else None,
            values=self.values,
            default_scope=self.default_scope,
            default_values=self.default_values,
            confirm_changes=tuple(self.confirm_changes),
        )


_DEPLOY_KEYS = {
    "repourl": REPOURL,
    "target_revision": TARGET_REVISION,
    "path": PATH,
    "project_namespace": PROJECT_NAMESPACE,
    "ignore_differences": IGNORE_DIFFERENCES,
}


class UpdateTeamDefaultBody(_Input):
    """An edit of ``operators/<addon>/``: absent fields are unchanged, ``null`` removes a key."""

    repourl: str | None = None
    target_revision: str | None = None
    path: str | None = None
    project_namespace: str | None = None
    sync: SyncIn | None = Field(default=None, description="Absent or null: unchanged.")
    ignore_differences: list[dict[str, Any]] | None = None
    values: dict[str, Any] | None = Field(default=None, description="Absent or null: unchanged.")
    last_commit_id: str | None = None
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None

    def edit(self) -> TeamDefaultEdit:
        """The application's request: only the fields the body sent."""
        sent = self.model_fields_set
        return TeamDefaultEdit(
            keys={
                key: getattr(self, field) for field, key in _DEPLOY_KEYS.items() if field in sent
            },
            sync=self.sync.settings() if self.sync is not None else None,
            values=self.values,
            last_commit_id=self.last_commit_id,
        )


class MakeDefaultBody(_Input):
    """Make an add-on a fleet default."""

    values: dict[str, Any] = Field(default_factory=dict)
    sync: SyncIn | None = Field(default=None, description="null: the team default's.")
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class UpdateFleetDefaultBody(_Input):
    """An edit of ``defaults/<scope>/<addon>/``: absent fields are unchanged."""

    values: dict[str, Any] | None = None
    sync: SyncIn | None = Field(default=None, description="null: back to the team default's.")
    last_commit_id: str | None = None
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class _Confirmed(_Input):
    last_commit_id: str | None = Field(default=None, description="The file's, as read.")
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class ExclusionsBody(_Confirmed):
    """The destinations of a scope a fleet default skips: the full set, by cluster id."""

    excluded: list[str]


class DestinationValuesBody(_Confirmed):
    """A destination's ``values-<name>.yaml`` of a fleet default; null or {} deletes it."""

    values: dict[str, Any] | None


class DeployOverrideIn(_Input):
    """The keys a destination's own deploy config sets (null: not set)."""

    target_revision: str | None = None
    repourl: str | None = None
    path: str | None = None
    project_namespace: str | None = None

    def keys(self) -> dict[str, object | None]:
        """As deploy-config keys."""
        return {
            TARGET_REVISION: self.target_revision,
            REPOURL: self.repourl,
            PATH: self.path,
            PROJECT_NAMESPACE: self.project_namespace,
        }


class DestinationDeployBody(_Confirmed):
    """A destination's own deploy config (the carve-out); null takes it back into the default."""

    deploy: DeployOverrideIn | None


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
    """A team, its project, and whether Wingman may write there (ADR-0043)."""

    name: str
    project_id: int
    path_with_namespace: str
    web_url: str
    writable: bool
    access_level: int
    access_role: str
    read_only_reason: str | None

    @classmethod
    def of(cls, team: Team, access: TeamAccess) -> TeamOut:
        """From the domain team and its access."""
        return cls(
            name=team.name,
            project_id=team.project.id,
            path_with_namespace=team.project.path_with_namespace,
            web_url=team.project.web_url,
            writable=access.writable,
            access_level=int(access.level),
            access_role=access.level.role,
            read_only_reason=access.reason,
        )


class SyncOut(BaseModel):
    """A leaf app's sync options."""

    auto_sync: bool
    prune: bool
    self_heal: bool
    sync_options: list[str]

    @classmethod
    def of(cls, settings: SyncSettings) -> SyncOut:
        """From the domain settings."""
        return cls(
            auto_sync=settings.auto_sync,
            prune=settings.prune,
            self_heal=settings.self_heal,
            sync_options=list(settings.sync_options),
        )


class ScopeOut(BaseModel):
    """A fleet scope and the destinations a default there reaches today."""

    scope: str
    label: str
    destinations: list[str]


class AddonTemplateOut(BaseModel):
    """What a new add-on form starts from."""

    team: str
    writable: bool
    read_only_reason: str | None
    sync: SyncOut
    sync_source: str
    repourl_prefix: str | None
    known_sync_options: list[str]
    scopes: list[ScopeOut]

    @classmethod
    def of(cls, template: AddonTemplate) -> AddonTemplateOut:
        """From the application value."""
        return cls(
            team=template.team,
            writable=template.access.writable,
            read_only_reason=template.access.reason,
            sync=SyncOut.of(template.sync),
            sync_source=template.sync_source,
            repourl_prefix=template.repourl_prefix,
            known_sync_options=list(KNOWN_SYNC_OPTIONS),
            scopes=[
                ScopeOut(
                    scope=str(s.scope),
                    label=s.label,
                    destinations=[ref.id for ref in s.destinations],
                )
                for s in template.scopes
            ],
        )


class FleetDefaultOut(BaseModel):
    """One ``defaults/<scope>/<chart>/`` of a team."""

    team: str
    chart: str
    scope: str
    scope_label: str
    path: str
    in_catalog: bool
    values: dict[str, Any]
    values_exists: bool
    sync: SyncOut
    sync_overridden: bool
    reach: list[str]
    excluded: list[str]
    tweaks: list[str]
    last_commit_id: str | None
    writable: bool
    read_only_reason: str | None
    warnings: list[FindingOut]

    @classmethod
    def of(cls, default: FleetDefault) -> FleetDefaultOut:
        """From the application value."""
        return cls(
            team=default.team,
            chart=default.chart,
            scope=str(default.scope),
            scope_label=SCOPE_LABELS[default.scope],
            path=str(default.folder),
            in_catalog=default.in_catalog,
            values=default.values.values,
            values_exists=default.values.exists,
            sync=SyncOut.of(default.sync),
            sync_overridden=default.sync_overridden,
            reach=[ref.id for ref in default.reach],
            excluded=[ref.id for ref in default.excluded],
            tweaks=[str(p) for p in default.tweaks],
            last_commit_id=default.last_commit_id,
            writable=default.access.writable,
            read_only_reason=default.access.reason,
            warnings=findings(default.findings),
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
    writable: bool
    read_only_reason: str | None
    sync: SyncOut
    ignore_differences: Any
    deploy_config_exists: bool
    last_commit_id: str | None

    @classmethod
    def of(cls, entry: CatalogEntry, access: TeamAccess) -> CatalogEntryOut:
        """From the catalog entry and its team's access."""
        file = entry.deploy.file or entry.values.file
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
            writable=access.writable,
            read_only_reason=access.reason,
            sync=SyncOut.of(sync_settings(entry.deploy.values.get(SYNC_POLICY))),
            ignore_differences=entry.deploy.values.get(IGNORE_DIFFERENCES),
            deploy_config_exists=entry.deploy.exists,
            last_commit_id=file.last_commit_id if file else None,
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


# ── Add-on authoring (ADR-0043) ─────────────────────────────────────────────


class PlannedFileOut(BaseModel):
    """One file a plan writes: its new text and its text before."""

    action: str
    path: str
    content: str | None
    previous: str | None


class KeyChangeOut(BaseModel):
    """One leaf of a destination's effective deploy config or values that changes.

    ``after_null``: a Helm ``null``, which deletes the key and the chart's own default.
    """

    stack: str
    key: str
    before: Any
    after: Any
    after_null: bool = False

    @classmethod
    def of(cls, change: KeyChange) -> KeyChangeOut:
        """From the application value."""
        return cls(
            stack=change.stack,
            key=change.key,
            before=change.before,
            after=change.after,
            after_null=change.after_null,
        )


class ImpactOut(BaseModel):
    """What an authoring MR does to one destination's app of the chart (ADR-0053)."""

    cluster: str
    name: str
    kind: str
    effect: str
    app_name: str
    changes: list[KeyChangeOut]
    orphaned: bool

    @classmethod
    def of(cls, impact: DestinationImpact) -> ImpactOut:
        """From the application value."""
        return cls(
            cluster=impact.ref.id,
            name=impact.ref.name,
            kind=str(impact.ref.kind),
            effect=str(impact.effect),
            app_name=impact.app_name,
            changes=[KeyChangeOut.of(c) for c in impact.changes],
            orphaned=impact.orphaned,
        )


class MovedOut(BaseModel):
    """A file moved into the fleet default."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(serialization_alias="from")
    to: str


class AdoptionOut(BaseModel):
    """A cluster whose own chart folder moves into the new fleet default."""

    cluster: str
    name: str
    moved: list[MovedOut]
    deleted: list[str]
    gitkeep: str | None
    changes: list[KeyChangeOut]
    exclusion_removed: bool

    @classmethod
    def of(cls, adoption: Adoption) -> AdoptionOut:
        """From the application value."""
        return cls(
            cluster=adoption.ref.id,
            name=adoption.ref.name,
            moved=[MovedOut(from_=str(a), to=str(b)) for a, b in adoption.moved],
            deleted=[str(p) for p in adoption.deleted],
            gitkeep=str(adoption.gitkeep) if adoption.gitkeep else None,
            changes=[KeyChangeOut.of(c) for c in adoption.changes],
            exclusion_removed=adoption.exclusion_removed,
        )


class _AuthoringFields(BaseModel):
    action: str
    chart: str
    scope: str | None
    reach: list[str]
    adopted: list[AdoptionOut]
    impact: list[ImpactOut]
    excluded: list[str]
    needs_confirmation: list[str]
    digest: str
    warnings: list[FindingOut]
    notes: list[str]

    @staticmethod
    def fields_of(plan: AuthoringPlan) -> dict[str, Any]:
        return {
            "action": str(plan.action),
            "chart": plan.chart,
            "scope": str(plan.scope) if plan.scope else None,
            "reach": [ref.id for ref in plan.reach],
            "adopted": [AdoptionOut.of(a) for a in plan.adopted],
            "impact": [ImpactOut.of(i) for i in plan.impact],
            "excluded": [ref.id for ref in plan.excluded],
            "needs_confirmation": plan.needs_confirmation,
            "digest": plan.digest,
            "warnings": findings(plan.findings),
            "notes": list(plan.notes),
        }


class AuthoringPlanOut(_AuthoringFields):
    """A dry run: what the MR would write and do; nothing was opened."""

    team: str
    title: str
    files: list[PlannedFileOut]

    @classmethod
    def of(cls, plan: AuthoringPlan) -> AuthoringPlanOut:
        """From the plan."""
        return cls(
            team=plan.team,
            title=plan.title,
            files=[
                PlannedFileOut(
                    action=str(c.kind),
                    path=str(c.path),
                    content=c.content,
                    previous=plan.previous.get(str(c.path)),
                )
                for c in plan.changes
            ],
            **cls.fields_of(plan),
        )


class AuthoringChangeOut(MRDetailOut, _AuthoringFields):
    """An opened authoring MR (an ``MRDetail``) plus what it writes and does."""

    files: list[FileChangeOut]

    @classmethod
    def of_result(cls, result: AuthoringResult) -> AuthoringChangeOut:
        """From the result of a real (not dry) run."""
        plan, merge_request = result.plan, result.merge_request
        if merge_request is None:
            raise ValueError("a dry run opened no merge request")
        base = MRDetailOut.of(plan.team, merge_request)
        return cls(
            **base.model_dump(),
            files=[FileChangeOut.of(c) for c in plan.changes],
            **_AuthoringFields.fields_of(plan),
        )


# ── Add-ons with their defaults (ADR-0053) ────────────────────────────────────────────────────


class FileOut(BaseModel):
    """A file of the team repo; ``last_commit_id`` is the commit it was read at (null: absent)."""

    path: str
    exists: bool
    text: str | None
    values: dict[str, Any]
    last_commit_id: str | None
    problem: str | None

    @classmethod
    def of(cls, loaded: LoadedLayer) -> FileOut:
        """From a loaded file."""
        return cls(
            path=str(loaded.layer.path),
            exists=loaded.exists,
            text=loaded.file.content if loaded.file else None,
            values=loaded.values,
            last_commit_id=loaded.file.last_commit_id if loaded.file else None,
            problem=loaded.problem.message if loaded.problem else None,
        )


class OcpVersionOut(BaseModel):
    """An ``ocp-versions/<v>/`` pin of an add-on."""

    version: str
    target_revision: str | None
    deploy_config: FileOut
    values_file: FileOut

    @classmethod
    def of(cls, pin: OcpVersionPin) -> OcpVersionOut:
        """From the application value."""
        return cls(
            version=pin.version,
            target_revision=pin.target_revision,
            deploy_config=FileOut.of(pin.deploy),
            values_file=FileOut.of(pin.values),
        )


class ExclusionsOut(BaseModel):
    """A scope's ``exclusions.yaml``, as it concerns one add-on."""

    path: str
    exists: bool
    names: list[str]
    unknown_names: list[str]
    editable: bool
    problem: str | None
    last_commit_id: str | None

    @classmethod
    def of(cls, view: ExclusionsView) -> ExclusionsOut:
        """From the application value."""
        file = view.file.file
        return cls(
            path=str(view.file.layer.path),
            exists=view.file.exists,
            names=list(view.names),
            unknown_names=list(view.unknown_names),
            editable=view.editable,
            problem=view.problem,
            last_commit_id=file.last_commit_id if file else None,
        )


class ScopeDestinationOut(BaseModel):
    """One destination of a scope and how the add-on's default stands there."""

    id: str
    name: str
    kind: str
    site: str
    env: str
    mce: str
    ocp_version: str | None
    renders: bool
    state: str
    deployed: bool
    app_name: str | None
    override: FileOut | None
    override_shared_with: list[str]
    own_folder: str | None
    own_deploy: FileOut | None

    @classmethod
    def of(cls, view: DestinationView) -> ScopeDestinationOut:
        """From the application value."""
        ref = view.ref
        return cls(
            id=ref.id,
            name=ref.name,
            kind=str(ref.kind),
            site=ref.site,
            env=ref.env,
            mce=ref.mce,
            ocp_version=view.ocp_version,
            renders=view.renders,
            state=str(view.state),
            deployed=view.deployed,
            app_name=view.app_name,
            override=FileOut.of(view.override) if view.override else None,
            override_shared_with=[r.id for r in view.shared_with],
            own_folder=str(view.own_folder) if view.own_folder else None,
            own_deploy=FileOut.of(view.own_deploy) if view.own_deploy else None,
        )


class UnregisteredOut(BaseModel):
    """A destination of the scope that day1 or another team knows, and this team does not."""

    id: str
    name: str
    site: str
    env: str
    mce: str


class EnvFileOut(BaseModel):
    """A fleet default's ``values-<env>.yaml``."""

    env: str
    file: FileOut


class ScopePanelOut(BaseModel):
    """One scope of an add-on: its default there, if any, and every destination."""

    scope: str
    label: str
    noun: str
    is_default: bool
    folder: str
    values_file: FileOut
    deploy_config: FileOut
    sync: SyncOut
    sync_overridden: bool
    env_files: list[EnvFileOut]
    exclusions: ExclusionsOut | None
    destinations: list[ScopeDestinationOut]
    unregistered: list[UnregisteredOut]
    last_commit_id: str | None

    @classmethod
    def of(cls, view: ScopeView) -> ScopePanelOut:
        """From the application value."""
        return cls(
            scope=str(view.scope),
            label=SCOPE_LABELS[view.scope],
            noun=SCOPE_NOUNS[view.scope],
            is_default=view.is_default,
            folder=str(view.folder),
            values_file=FileOut.of(view.values),
            deploy_config=FileOut.of(view.deploy),
            sync=SyncOut.of(view.sync),
            sync_overridden=view.sync_overridden,
            env_files=[EnvFileOut(env=env, file=FileOut.of(f)) for env, f in view.env_files],
            exclusions=ExclusionsOut.of(view.exclusions) if view.exclusions else None,
            destinations=[ScopeDestinationOut.of(d) for d in view.destinations],
            unregistered=[
                UnregisteredOut(id=r.id, name=r.name, site=r.site, env=r.env, mce=r.mce)
                for r in view.unregistered
            ],
            last_commit_id=view.last_commit_id,
        )


class OperatorOut(BaseModel):
    """One add-on of a team: its files, its OCP-version pins, one panel per scope."""

    team: str
    name: str
    in_catalog: bool
    writable: bool
    read_only_reason: str | None
    catalog: CatalogEntryOut | None
    deploy_config: FileOut
    values_file: FileOut
    ocp_versions: list[OcpVersionOut]
    scopes: list[ScopePanelOut]
    warnings: list[FindingOut]

    @classmethod
    def of(cls, view: OperatorView) -> OperatorOut:
        """From the application value."""
        return cls(
            team=view.team,
            name=view.chart,
            in_catalog=view.in_catalog,
            writable=view.access.writable,
            read_only_reason=view.access.reason,
            catalog=CatalogEntryOut.of(view.catalog, view.access) if view.catalog else None,
            deploy_config=FileOut.of(view.deploy),
            values_file=FileOut.of(view.values),
            ocp_versions=[OcpVersionOut.of(p) for p in view.ocp_versions],
            scopes=[ScopePanelOut.of(s) for s in view.scopes],
            warnings=findings(view.findings),
        )


class OperatorDefaultOut(BaseModel):
    """A scope an add-on is a default on, and its reach there."""

    scope: str
    label: str
    reach: int
    excluded: int


class OperatorSummaryOut(BaseModel):
    """One line of a team's add-ons list."""

    team: str
    name: str
    in_catalog: bool
    repourl: str
    target_revision: str
    sync: SyncOut
    ocp_versions: list[str]
    defaults: list[OperatorDefaultOut]
    installed_on: int
    warnings: int
    writable: bool
    read_only_reason: str | None

    @classmethod
    def of(cls, summary: OperatorSummary) -> OperatorSummaryOut:
        """From the application value."""
        entry = summary.catalog
        sync = sync_settings(entry.deploy.values.get(SYNC_POLICY)) if entry else SyncSettings()
        return cls(
            team=summary.team,
            name=summary.chart,
            in_catalog=entry is not None,
            repourl=entry.repo_url if entry else "",
            target_revision=entry.team_revision if entry else "",
            sync=SyncOut.of(sync),
            ocp_versions=list(summary.ocp_versions),
            defaults=[
                OperatorDefaultOut(
                    scope=str(d.scope),
                    label=SCOPE_LABELS[d.scope],
                    reach=d.reach,
                    excluded=d.excluded,
                )
                for d in summary.defaults
            ],
            installed_on=summary.installed_on,
            warnings=summary.warnings,
            writable=summary.access.writable,
            read_only_reason=summary.access.reason,
        )
