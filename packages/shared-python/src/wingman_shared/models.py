"""Shared Pydantic models used by both Day1 and Day2 services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Auth models ───────────────────────────────────────────────────────────────


class UserInfo(BaseModel):
    username: str
    groups: list[str] = Field(default_factory=list)
    uid: str = ""
    full_name: str = ""
    role: Literal["admin", "viewer"] = "viewer"  # resolved after login based on group membership


# ── Cluster spec models ───────────────────────────────────────────────────────


class SpecVariable(BaseModel):
    name: str
    type: Literal["string", "integer", "boolean", "list", "object"]
    required: bool = True
    default: Any = None
    description: str = ""
    pattern: str | None = None
    enum: list[str] | None = None
    minimum: int | None = None
    maximum: int | None = None


class OverrideableField(BaseModel):
    """A field that cluster creators can override when using a spec."""

    path: str  # dot-notation path, e.g. "replicas" or "config.timeout"
    type: Literal["string", "integer", "boolean", "object", "array"] = "string"
    default: Any = None
    description: str = ""


class SpecAddon(BaseModel):
    team: str
    name: str
    version: str
    overrideable: list[OverrideableField] = Field(default_factory=list)


class Day1Config(BaseModel):
    variables: list[SpecVariable]
    template: str  # Jinja2 template string for the multi-document cluster YAML


class Day2Config(BaseModel):
    addons: list[SpecAddon] = Field(default_factory=list)


class SpecMetadata(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    labels: dict[str, str] = Field(default_factory=dict)


class SpecBody(BaseModel):
    day1: Day1Config
    day2: Day2Config


class ClusterSpec(BaseModel):
    apiVersion: str = "wingman.io/v1"
    kind: str = "ClusterSpec"
    metadata: SpecMetadata
    spec: SpecBody


# ── Cluster metadata (.wingman.yaml) ─────────────────────────────────────────


class ClusterMetadata(BaseModel):
    """Stored alongside cluster.yaml in day1 repo."""

    spec_name: str = Field(alias="specName", default="")
    spec_version: str = Field(alias="specVersion", default="")
    created_by: str = Field(alias="createdBy", default="")
    created_at: datetime = Field(
        alias="createdAt", default_factory=lambda: datetime.min.replace(tzinfo=UTC)
    )
    site: str
    mce: str
    variables: dict[str, Any] = Field(default_factory=dict)
    addon_overrides: dict[str, dict[str, Any]] = Field(
        alias="addonOverrides", default_factory=dict
    )

    model_config = {"populate_by_name": True}


# ── Cluster list/detail ───────────────────────────────────────────────────────


class ClusterStatus(BaseModel):
    name: str
    site: str
    mce: str
    phase: Literal["Provisioning", "Ready", "Error", "Deleting", "Unknown"] = "Unknown"
    spec_name: str | None = None
    spec_version: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    is_drifted: bool = False


# ── Live cluster status (HyperShift CRD conditions) ──────────────────────────


class NodePoolStatus(BaseModel):
    name: str
    ready_replicas: int = 0
    desired_replicas: int = 0
    problems: list[str] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return len(self.problems) == 0 and self.ready_replicas == self.desired_replicas


class ClusterLiveStatus(BaseModel):
    cluster_name: str
    hc_problems: list[str] = Field(default_factory=list)
    node_pools: list[NodePoolStatus] = Field(default_factory=list)
    error: str | None = None  # set when the MCE API call failed entirely

    @property
    def is_healthy(self) -> bool:
        return (
            self.error is None
            and len(self.hc_problems) == 0
            and all(np.is_healthy for np in self.node_pools)
        )


# ── MR / Approval models ──────────────────────────────────────────────────────


class MRAuthor(BaseModel):
    username: str
    name: str = ""
    avatar_url: str = ""


class MRDetail(BaseModel):
    iid: int
    title: str
    description: str = ""
    author: MRAuthor
    state: str  # "opened" | "merged" | "closed"
    created_at: str
    updated_at: str
    web_url: str
    source_branch: str
    target_branch: str
    labels: list[str] = Field(default_factory=list)
    repo: Literal["day1", "day2", "specs"] = "day1"  # which GitLab repo this MR belongs to


class FileDiff(BaseModel):
    old_path: str
    new_path: str
    diff: str
    new_file: bool = False
    renamed_file: bool = False
    deleted_file: bool = False


class UpdateMRFile(BaseModel):
    path: str
    content: str


class UpdateMRRequest(BaseModel):
    files: list[UpdateMRFile]
    message: str = ""


# ── Audit models ──────────────────────────────────────────────────────────────


class CommitRecord(BaseModel):
    id: str
    short_id: str
    title: str
    author_name: str
    author_email: str
    authored_date: str
    message: str
    web_url: str


# ── Addon models (shared) ─────────────────────────────────────────────────────


class AddonArgoMetadata(BaseModel):
    """Contents of {addon}.yaml in the day2 repo."""

    project_namespace: str = Field(alias="projectNamespace", default="")
    repourl: str = ""
    target_revision: str = Field(alias="targetRevision", default="main")
    sync_policy: dict[str, Any] = Field(alias="syncPolicy", default_factory=dict)

    model_config = {"populate_by_name": True}


class AddonCatalogEntry(BaseModel):
    team: str
    name: str
    available_versions: list[str] = Field(default_factory=list)
    current_version: str = ""  # targetRevision from default metadata
    default_values: dict[str, Any] = Field(default_factory=dict)
    argocd_metadata: AddonArgoMetadata | None = None


class InstalledAddon(BaseModel):
    team: str
    name: str
    version: str
    override_values: dict[str, Any] = Field(default_factory=dict)


class MergedAddonValues(BaseModel):
    """Result of 3-tier merge with provenance tracking."""

    merged: dict[str, Any]
    provenance: dict[str, Any]  # same structure, values are "chart"|"team"|"cluster"
    chart_values: dict[str, Any]
    team_values: dict[str, Any]
    cluster_values: dict[str, Any]
    addon_name: str
    team: str
    version: str
