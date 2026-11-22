"""``/api/day1/clusters/{name}/excluded-agent-labels``: one cluster's merge request (ADR-0065).

``DAY1_EXCLUDED_AGENT_LABELS`` names the Agent labels every NodePool
excludes; a new cluster gets them at create, an existing one through this
merge request, one cluster at a time. Empty, both routes answer 501. Reading
the plan needs a session; opening the merge request needs an admin. While an
open merge request already carries the change, the plan names it and the
``POST`` answers 409 (``ALREADY_EXISTS``) naming it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import AgentLabels, Context
from wingman_day1.api.v1.schemas import MRDetailOut, change_out
from wingman_day1.application.agent_labels import AgentLabelsPlan
from wingman_day1.application.approvals import RepoKey
from wingman_day1.domain.excluded_agent_labels import PoolPlan

router = APIRouter(prefix="/api/day1/clusters", tags=["excluded-agent-labels"])

Site = Annotated[str | None, Query(max_length=63, description="Site folder")]
Mce = Annotated[str | None, Query(max_length=63, description="MCE folder")]


class AgentLabelsPoolOut(BaseModel):
    """One nodepool of the file: what it excludes now, and what the merge request does to it."""

    index: int
    name: str
    """Its NodePool's, as the MCE shows it: ``name``, else ``<clusterName>-<infraEnvName>``."""
    excludes: list[str]
    """Its ``excludeAgentLabels`` as written; ``[]`` without."""
    change: bool
    """Whether the merge request writes the deployment's keys on it."""
    reason: str

    @classmethod
    def of(cls, pool: PoolPlan) -> AgentLabelsPoolOut:
        """From a nodepool's plan."""
        return cls(
            index=pool.index,
            name=pool.name,
            excludes=list(pool.have),
            change=pool.change,
            reason=pool.reason,
        )


class AgentLabelsPlanOut(BaseModel):
    """``GET .../excluded-agent-labels``: what the cluster's merge request would do."""

    cluster: str
    labels: list[str]
    """The deployment's keys (``DAY1_EXCLUDED_AGENT_LABELS``)."""
    last_commit_id: str
    """The commit the file was read at; send it back with the ``POST``."""
    nodepools: list[AgentLabelsPoolOut]
    """Each nodepool against ``main``: ``change`` is what ``main`` lacks."""
    open_merge_request: MRDetailOut | None
    """An open merge request that already writes the keys where ``change`` says; the ``POST``
    then answers 409 naming it. ``None`` when none does."""

    @classmethod
    def of(cls, plan: AgentLabelsPlan) -> AgentLabelsPlanOut:
        """From the plan."""
        opened = plan.open_merge_request
        return cls(
            cluster=plan.ref.name,
            labels=list(plan.labels),
            last_commit_id=plan.last_commit_id,
            nodepools=[AgentLabelsPoolOut.of(p) for p in plan.nodepools],
            open_merge_request=change_out(RepoKey.DAY1, opened) if opened else None,
        )


class AgentLabelsIn(BaseModel):
    """``POST .../excluded-agent-labels``: open the merge request, guarded by the plan's read."""

    model_config = ConfigDict(extra="forbid")

    last_commit_id: str | None = Field(default=None, max_length=64)
    """The plan's ``last_commit_id``; without it, the file as read now."""


@router.get("/{name}/excluded-agent-labels")
async def agent_labels_plan(
    name: str,
    context: Context,
    labels: AgentLabels,
    user: CurrentUser,
    site: Site = None,
    mce: Mce = None,
) -> AgentLabelsPlanOut:
    """Each nodepool, what it excludes now, and whether the merge request changes it."""
    ref = await context.clusters.locate(name, site=site, mce=mce)
    return AgentLabelsPlanOut.of(await labels.plan(ref))


@router.post("/{name}/excluded-agent-labels", status_code=201)
async def open_agent_labels(
    name: str,
    body: AgentLabelsIn,
    context: Context,
    labels: AgentLabels,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> MRDetailOut:
    """Open the cluster's one merge request that writes the deployment's keys on its NodePools.

    409 while an open merge request already does (the plan's ``open_merge_request``).
    """
    ref = await context.clusters.locate(name, site=site, mce=mce)
    result = await labels.apply(ref, user=user, last_commit_id=body.last_commit_id)
    return change_out(RepoKey.DAY1, result.merge_request)
