"""The bodies of ``/api/day1/approvals``: an MR's diff, approving and editing it.

``GET /approvals/{iid}/rollout`` says what merging a flavor's MR opens,
cluster by cluster (ADR-0044).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from wingman_core.web.schemas import FileDiffOut
from wingman_day1.api.v1.schemas import MAX_FILE_BYTES, MRDetailOut, _In
from wingman_day1.application.rollouts import RolloutPreview


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


# ── What merging a flavor's MR opens (ADR-0044) ──────────────────────────────


class ClusterRefOut(BaseModel):
    """A cluster, by name and place."""

    name: str
    site: str
    mce: str


class DecisionOut(ClusterRefOut):
    """A cluster that gets no MR until a person syncs it."""

    reasons: list[str]


class NodepoolRollOut(BaseModel):
    """A nodepool whose nodes roll when the cluster's MR merges, and how."""

    name: str
    replicas: int | None
    replaces_nodes: bool
    max_unavailable: int | str | None


class RollsOut(ClusterRefOut):
    """A cluster whose MR rolls nodes."""

    nodepools: list[NodepoolRollOut]


class RemovalOut(BaseModel):
    """A config a cluster's MR removes from a nodepool."""

    nodepool: str
    name: str


class RemovalsOut(ClusterRefOut):
    """A cluster whose MR removes configs."""

    removals: list[RemovalOut]


class ApprovalRolloutOut(BaseModel):
    """``GET /approvals/{iid}/rollout``: what merging a flavor's MR opens, cluster by cluster."""

    applies: bool
    reason: str | None
    spec_name: str
    version: str | None
    current_version: str | None
    following: int
    opens: int
    already_on_version: int
    needs_decision: list[DecisionOut]
    rolls_nodes: list[RollsOut]
    removes_configs: list[RemovalsOut]
    adds_addons: list[str]

    @classmethod
    def of(cls, preview: RolloutPreview) -> ApprovalRolloutOut:
        """From a rollout preview."""
        return cls(
            applies=preview.applies,
            reason=preview.reason,
            spec_name=preview.spec_name,
            version=preview.version,
            current_version=preview.current_version,
            following=preview.following,
            opens=preview.opens,
            already_on_version=preview.already_on_version,
            needs_decision=[
                DecisionOut(
                    name=d.ref.name, site=d.ref.site, mce=d.ref.mce, reasons=list(d.reasons)
                )
                for d in preview.needs_decision
            ],
            rolls_nodes=[
                RollsOut(
                    name=r.ref.name,
                    site=r.ref.site,
                    mce=r.ref.mce,
                    nodepools=[
                        NodepoolRollOut(
                            name=n.nodepool.name,
                            replicas=n.replicas,
                            replaces_nodes=n.replaces_nodes,
                            max_unavailable=n.max_unavailable,
                        )
                        for n in r.rebooting
                    ],
                )
                for r in preview.rolls_nodes
            ],
            removes_configs=[
                RemovalsOut(
                    name=r.ref.name,
                    site=r.ref.site,
                    mce=r.ref.mce,
                    removals=[
                        RemovalOut(nodepool=x.nodepool.name, name=x.name) for x in r.removals
                    ],
                )
                for r in preview.removes_configs
            ],
            adds_addons=list(preview.adds_addons),
        )
