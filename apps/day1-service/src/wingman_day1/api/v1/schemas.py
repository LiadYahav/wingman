"""The bodies two or more day1 routers share, and the request base.

Each router's own bodies are in ``<router>_schemas.py`` beside it; the
clusters router's are split by sub-resource (``cluster_<part>_schemas.py``).
A model moves here once a second module uses it, and a ``*_schemas.py``
module imports only from here, never from another. Request bodies forbid
unknown fields, so a misspelt field is an error, not a silently ignored
value. Response shapes keep the legacy JSON wherever the meaning is
unchanged; every deliberate change is listed in
``docs/notes/2026-11-07-day1-api-changes.md``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from wingman_core.application.approvals import describe
from wingman_core.domain.git import Commit
from wingman_core.domain.merge_request import MergeRequest
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.drift import ClusterDrift, FlavorUpdate
from wingman_day1.domain.addons import AddonDrift, VersionDifference
from wingman_day1.domain.locks import MISSING
from wingman_day1.domain.value_drift import ValueDrift
from wingman_day1.domain.workflows import WorkflowName, WorkflowRun

MAX_FILE_BYTES = 256 * 1024


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
    opened_by_workflow: WorkflowName | None = None
    """The platform workflow that opened it (review it in GitLab); ``None`` for Wingman's."""

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
            opened_by_workflow=change.opened_by_workflow,
        )


def change_out(repo: RepoKey, merge_request: MergeRequest) -> MRDetailOut:
    """The response for an MR a change just opened."""
    return MRDetailOut.of(Change(repo, describe(merge_request)))


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
    update: FlavorUpdateOut | None
    """The flavor's newest version when the cluster is on an older one: never drift (ADR-0044)."""

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
            update=FlavorUpdateOut.of(drift.update),
        )


class MergeRequestLinkOut(BaseModel):
    """Enough of a day1 MR to link it: its review page is ``/approvals/day1-<iid>``."""

    repo: Literal["day1"] = "day1"
    iid: int
    title: str
    web_url: str

    @classmethod
    def of(cls, merge_request: MergeRequest) -> MergeRequestLinkOut:
        """From an MR."""
        return cls(
            iid=merge_request.ref.iid, title=merge_request.title, web_url=merge_request.web_url
        )


class FlavorUpdateOut(BaseModel):
    """A newer version of the cluster's flavor, and the open MR that moves it there."""

    version: str
    merge_request: MergeRequestLinkOut | None

    @classmethod
    def of(cls, update: FlavorUpdate | None) -> FlavorUpdateOut | None:
        """From a drift verdict's update; ``None`` stays ``None``."""
        if update is None:
            return None
        mr = update.merge_request
        return cls(
            version=update.version,
            merge_request=MergeRequestLinkOut.of(mr) if mr is not None else None,
        )


# ── Workflow runs ────────────────────────────────────────────────────────────


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
