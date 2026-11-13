"""The bodies two or more ``/api/day2`` routers share, and the request base.

Each router's own bodies are in ``<router>_schemas.py`` beside it; a model
moves here once a second router uses it. Request bodies refuse unknown fields
(``extra="forbid"``): a typo is a 422, not a silently ignored setting. Response
shapes keep the legacy field names where the meaning is unchanged, and add
fields; every change visible to the web app is listed in
``docs/notes/2026-11-07-day2-api-changes.md`` (add-on authoring and per-team
access: ``docs/notes/2026-11-12-day2-addon-authoring-api.md``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wingman_core.application.approvals import PendingChange, describe
from wingman_core.domain.git import FileChange
from wingman_core.domain.merge_request import MergeRequest
from wingman_day2.application.catalog import CatalogEntry
from wingman_day2.domain.deploy_config import IGNORE_DIFFERENCES, SYNC_POLICY
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.sync_policy import SyncSettings, sync_settings
from wingman_day2.domain.teams import TeamAccess


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
