"""The scale routes' bodies (docs/notes/2026-11-16-scale-nodepools-api.md, ADR-0062).

Request bodies forbid unknown fields; who asks is never one of them.
Responses pass the workflow's strings through, its phases included.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from wingman_day1.application.scale import ScaleOptions, ScaleTarget
from wingman_day1.domain.scale import (
    ChosenServer,
    FileNodePool,
    HeldReplicas,
    LiveReplicas,
    NodePoolChange,
    ScaleChild,
    ScaleResult,
    ScaleRun,
)

_NAME = r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$"
"""A Kubernetes name, as the workflow takes a NodePool."""


class ScaleIn(BaseModel):
    """``POST .../scale``: one NodePool of the cluster, by name, and its replicas."""

    model_config = ConfigDict(extra="forbid")

    replicas: StrictInt = Field(ge=0, le=10_000)
    """That NodePool's own, set exactly; the cluster's other NodePools are left as they are."""
    nodepool: str = Field(max_length=253, pattern=_NAME)

    @model_validator(mode="before")
    @classmethod
    def _no_kind(cls, data: Any) -> Any:
        """A total over an InfraEnv kind is gone (2026-11-18): refused in words, not as extra."""
        if isinstance(data, dict) and "infra_env_kind" in data:
            raise ValueError(
                "infra_env_kind is no longer taken: send the NodePool's name as nodepool, "
                "with that NodePool's own replicas"
            )
        return data

    def target(self) -> ScaleTarget:
        """For the use case."""
        return ScaleTarget(self.replicas, self.nodepool)


# ── What can be scaled ───────────────────────────────────────────────────────


class ScaleNodePoolOut(BaseModel):
    """One NodePool of the cluster file on main."""

    index: int
    name: str | None
    """What update-nodepool takes by name; ``null`` when the file cannot name it."""
    infra_env: str | None
    replicas: int | None
    """The file's (1 when absent, the chart's default); ``null`` when not a whole number."""
    locked_by: str | None
    """The flavor that locks its replicas; such a NodePool moves only back to its locked value."""
    locked_replicas: int | None
    unnamed: str | None
    """Why it cannot be scaled by name."""
    scale_down_policy: str | None
    """The entry's ``redbull.io/scale-down-policy`` annotation as written; ``null`` without one."""

    @classmethod
    def of(cls, pool: FileNodePool) -> ScaleNodePoolOut:
        """From a file NodePool."""
        return cls(
            index=pool.index,
            name=pool.name,
            infra_env=pool.infra_env,
            replicas=pool.replicas,
            locked_by=pool.locked_by,
            locked_replicas=pool.locked_replicas,
            unnamed=pool.unnamed,
            scale_down_policy=pool.scale_down_policy,
        )


class ScaleOptionsOut(BaseModel):
    """``GET .../scale``: what Scale offers for the cluster, one NodePool at a time."""

    cluster: str
    mce: str
    flavor: str | None
    nodepools: list[ScaleNodePoolOut]

    @classmethod
    def of(cls, options: ScaleOptions) -> ScaleOptionsOut:
        """From the options."""
        return cls(
            cluster=options.ref.name,
            mce=options.ref.mce,
            flavor=options.flavor,
            nodepools=[ScaleNodePoolOut.of(p) for p in options.nodepools],
        )


# ── A run ────────────────────────────────────────────────────────────────────


class ScaleChildOut(BaseModel):
    """The scale-up-nodepool or scale-down-nodepool run the parent waits for."""

    workflow_id: str
    status: str | None
    phase: str | None
    error: str | None

    @classmethod
    def of(cls, child: ScaleChild) -> ScaleChildOut:
        """From the child."""
        return cls(
            workflow_id=child.workflow_id,
            status=child.status,
            phase=child.phase,
            error=child.error,
        )


class NodePoolChangeOut(BaseModel):
    """One NodePool the run selected, before and after."""

    name: str
    infra_env: str | None
    before: int | None
    after: int | None
    scale_down_policy: str | None


class LiveReplicasOut(BaseModel):
    """One NodePool as the run read it back after the sync."""

    name: str
    replicas: int | None
    ready_replicas: int | None


class ChosenServerOut(BaseModel):
    """A server a scale-down chose to leave, by its NodePool's policy."""

    nodepool: str
    machine: str
    node: str | None
    policy: str
    reason: str


class ScaleResultOut(BaseModel):
    """What a completed run did."""

    infra_env_kind: str | None
    """Only on a run recorded by kind before 2026-11-18; every other names its ``nodepool``."""
    nodepool: str | None
    day1_path: str | None
    direction: str
    total_before: int | None
    total_after: int | None
    nodepools: list[NodePoolChangeOut]
    child_workflow_id: str | None
    revision: str | None
    committed: bool | None
    live: list[LiveReplicasOut]
    chosen: list[ChosenServerOut]
    deleting: list[str]
    ignored: list[str]
    """What the request said about a scale-down that this run had no use for; never a failure."""

    @classmethod
    def of(cls, result: ScaleResult) -> ScaleResultOut:
        """From the result."""
        return cls(
            infra_env_kind=result.infra_env_kind,
            nodepool=result.nodepool,
            day1_path=result.day1_path,
            direction=result.direction,
            total_before=result.total_before,
            total_after=result.total_after,
            nodepools=[_change(c) for c in result.nodepools],
            child_workflow_id=result.child_workflow_id,
            revision=result.revision,
            committed=result.committed,
            live=[_live(n) for n in result.live],
            chosen=[_chosen(c) for c in result.chosen],
            deleting=list(result.deleting),
            ignored=list(result.ignored),
        )


class ScaleRunOut(BaseModel):
    """``GET .../scale-run`` and ``POST .../scale``: the cluster's update-nodepool run."""

    workflow_id: str
    status: str
    phase: str | None
    """The workflow's word, humanized by the web; there is no list of them."""
    direction: str | None
    child: ScaleChildOut | None
    result: ScaleResultOut | None
    error: str | None
    """Why it failed, in the workflow's words."""
    error_type: str | None
    """The failure's type, when its words name one (a child's always does)."""

    @classmethod
    def of(cls, run: ScaleRun) -> ScaleRunOut:
        """From a run."""
        return cls(
            workflow_id=run.workflow_id,
            status=run.status,
            phase=run.phase,
            direction=run.direction,
            child=ScaleChildOut.of(run.child) if run.child else None,
            result=ScaleResultOut.of(run.result) if run.result else None,
            error=run.error,
            error_type=run.error_type,
        )


class HeldReplicasOut(BaseModel):
    """A NodePool whose drifted locked replicas a sync leaves to update-nodepool (ADR-0062)."""

    index: int
    name: str | None
    """The NodePool to restore by name; ``null`` when the file cannot name it."""
    replicas: int | None
    flavor_replicas: int | None
    """The flavor's locked value: a restore starts update-nodepool on ``name`` with it."""

    @classmethod
    def of(cls, held: HeldReplicas) -> HeldReplicasOut:
        """From a held NodePool."""
        return cls(
            index=held.index,
            name=held.name,
            replicas=_whole(held.replicas),
            flavor_replicas=_whole(held.flavor_replicas),
        )


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _change(c: NodePoolChange) -> NodePoolChangeOut:
    return NodePoolChangeOut(
        name=c.name,
        infra_env=c.infra_env,
        before=c.before,
        after=c.after,
        scale_down_policy=c.scale_down_policy,
    )


def _live(n: LiveReplicas) -> LiveReplicasOut:
    return LiveReplicasOut(name=n.name, replicas=n.replicas, ready_replicas=n.ready_replicas)


def _chosen(c: ChosenServer) -> ChosenServerOut:
    return ChosenServerOut(
        nodepool=c.nodepool, machine=c.machine, node=c.node, policy=c.policy, reason=c.reason
    )
