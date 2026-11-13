"""The bodies of ``/api/day1/specs``: a flavor, the clusters that follow it, its rollout.

Importing existing clusters into a flavor has its own module,
``spec_import_schemas.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import DriftStateOut, FlavorUpdateOut, MergeRequestLinkOut, _iso
from wingman_day1.application.rollouts import (
    ClusterRollout,
    RolloutRun,
    RolloutState,
    RolloutStatus,
)
from wingman_day1.application.specs import SpecEntry
from wingman_day1.domain.specs import ClusterSpec, SpecBody, SpecMetadata, rule_problems


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


class SpecClusterOut(BaseModel):
    """A cluster created from a spec (``GET /specs/{name}/clusters``)."""

    name: str
    site: str
    mce: str
    phase: str = "Unknown"
    state: DriftStateOut
    is_drifted: bool | None
    error: str | None
    spec_version: str | None
    update: FlavorUpdateOut | None


class SpecDriftOut(BaseModel):
    """A spec's cluster drift (``GET /specs/{name}/drift``)."""

    cluster: str
    site: str
    mce: str
    state: DriftStateOut
    is_drifted: bool | None
    spec_version: str | None
    error: str | None
    update: FlavorUpdateOut | None


# ── A flavor's rollout (ADR-0044) ────────────────────────────────────────────


RolloutStateOut = Literal[
    "on_version",
    "merge_request_open",
    "pending",
    "needs_decision",
    "declined",
    "failed",
    "unknown",
]


class RolloutClusterOut(BaseModel):
    """One cluster that follows the flavor, and where its update stands."""

    name: str
    site: str
    mce: str
    path: str
    from_version: str | None
    """The version its header names."""
    state: RolloutStateOut
    merge_request: MergeRequestLinkOut | None
    """The open MR (``merge_request_open``) or the closed one (``declined``)."""
    reasons: list[str]
    """Why it needs a decision, failed or is unknown."""

    @classmethod
    def of(cls, item: ClusterRollout) -> RolloutClusterOut:
        """From one cluster's rollout."""
        ref = item.cluster.ref
        mr = item.merge_request
        return cls(
            name=ref.name,
            site=ref.site,
            mce=ref.mce,
            path=str(ref.path),
            from_version=item.cluster.provenance.spec_version,
            state=item.state.value,
            merge_request=MergeRequestLinkOut.of(mr) if mr is not None else None,
            reasons=list(item.reasons),
        )


class RolloutRunOut(BaseModel):
    """This replica's last run for the flavor."""

    trigger: Literal["merge", "webhook", "reconcile", "read"]
    started_at: str
    finished_at: str | None
    opened: int
    failed: int

    @classmethod
    def of(cls, run: RolloutRun | None) -> RolloutRunOut | None:
        """From a run; ``None`` stays ``None``."""
        if run is None:
            return None
        return cls(
            trigger=run.trigger.value,
            started_at=run.started_at.isoformat(),
            finished_at=_iso(run.finished_at),
            opened=run.opened,
            failed=run.failed,
        )


class RolloutStatusOut(BaseModel):
    """``GET /specs/{name}/rollout``: the newest version's rollout, from GitLab's state."""

    spec_name: str
    version: str | None
    running: bool
    last_run: RolloutRunOut | None
    counts: dict[RolloutStateOut, int]
    clusters: list[RolloutClusterOut]

    @classmethod
    def of(cls, status: RolloutStatus) -> RolloutStatusOut:
        """From a rollout status."""
        order = list(RolloutState)
        return cls(
            spec_name=status.spec_name,
            version=status.version,
            running=status.running,
            last_run=RolloutRunOut.of(status.last_run),
            counts={state.value: n for state, n in status.counts().items()},
            clusters=[
                RolloutClusterOut.of(c)
                for c in sorted(
                    status.clusters, key=lambda c: (order.index(c.state), c.cluster.ref.name)
                )
            ],
        )
