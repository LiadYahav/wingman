"""The bodies of ``/clusters/{name}/nodes``: nodes by NodePool, node uninstall (ADR-0038).

The shape is docs/notes/2026-11-11-cluster-nodes-api.md's.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import WorkflowRunOut, _In, _iso
from wingman_day1.application.nodes import ClusterNodes
from wingman_day1.domain.node_pools import NodePoolView, NodeView
from wingman_day1.domain.servers import ServerRow


class ServerOut(BaseModel):
    """A server, as server-scan reports it."""

    id: str
    name: str
    url: str
    """The server's page in server-scan's UI."""
    serial: str | None
    vendor: str | None
    model: str | None
    site: str | None
    mce: str | None
    state: str
    health: str
    maintenance: bool
    reachable: bool
    stale: bool
    contested: bool
    last_seen_at: str | None

    @classmethod
    def fields_of(cls, row: ServerRow, url: str) -> dict[str, Any]:
        """The server's fields, for this model and its subclasses."""
        return {
            "id": row.id,
            "name": row.name,
            "url": url,
            "serial": row.serial,
            "vendor": row.vendor,
            "model": row.model,
            "site": row.site,
            "mce": row.mce,
            "state": row.state,
            "health": row.health,
            "maintenance": row.maintenance,
            "reachable": row.reachable,
            "stale": row.stale,
            "contested": row.contested,
            "last_seen_at": _iso(row.last_seen_at),
        }


class UnassignedServerOut(ServerOut):
    """A server server-scan places in the cluster that no Machine leads to."""

    uninstall: WorkflowRunOut | None


class AgentOut(BaseModel):
    """The Agent reserved for a Machine."""

    name: str
    state: str | None
    stage: str | None


class NodeOut(BaseModel):
    """One node of a NodePool: a Machine, or one the pool wants and has not got."""

    machine: str | None
    node_name: str | None
    state: str
    current: bool
    activity: str | None
    waiting_for: str | None
    outdated: bool | None
    agent: AgentOut | None
    server_name: str | None
    server: ServerOut | None
    uninstall: WorkflowRunOut | None
    """The server's newest uninstall run; ``null`` when none, or when runs are unknown."""


class AutoscalingOut(BaseModel):
    """A NodePool's autoscaling bounds."""

    min: int
    max: int


class UpdateProgressOut(BaseModel):
    """An in-place update's ``Total Nodes`` and ``Upgraded``."""

    total: int
    updated: int


class PoolUpdateOut(BaseModel):
    """A NodePool update in progress."""

    kind: str
    message: str
    progress: UpdateProgressOut | None
    failed: bool


class FreeAgentsOut(BaseModel):
    """The Agents a NodePool's selector matches, and how many are free."""

    matching: int
    free: int


class NodePoolNodesOut(BaseModel):
    """A NodePool, its update and problems, and its nodes."""

    name: str
    wanted: int | None
    autoscaling: AutoscalingOut | None
    ready: int
    version: str | None
    upgrade_type: str | None
    agent_selector: str | None
    update: PoolUpdateOut | None
    problems: list[str]
    free_agents: FreeAgentsOut | None
    nodes: list[NodeOut]


class UninstallAvailabilityOut(BaseModel):
    """Whether the Uninstall button can be offered, and why not."""

    available: bool
    detail: str | None


class ClusterNodesOut(BaseModel):
    """``GET /clusters/{name}/nodes``: the docs/notes/2026-11-11-cluster-nodes-api.md shape."""

    hosted_cluster: str
    node_pools: list[NodePoolNodesOut]
    unassigned: list[UnassignedServerOut]
    uninstall: UninstallAvailabilityOut
    server_scan_error: str | None
    runs_error: str | None

    @classmethod
    def of(cls, found: ClusterNodes) -> ClusterNodesOut:
        """From a cluster's nodes."""

        def run_of(row: ServerRow | None) -> WorkflowRunOut | None:
            run = found.runs.get(row.id) if row is not None else None
            return WorkflowRunOut.of(run) if run is not None else None

        def server_of(row: ServerRow | None) -> ServerOut | None:
            if row is None:
                return None
            return ServerOut(**ServerOut.fields_of(row, found.server_urls[row.id]))

        def node_of(node: NodeView) -> NodeOut:
            agent = node.agent
            return NodeOut(
                machine=node.machine,
                node_name=node.node_name,
                state=node.state.value,
                current=node.current,
                activity=node.activity,
                waiting_for=node.waiting_for,
                outdated=node.outdated,
                agent=AgentOut(name=agent.name, state=agent.state, stage=agent.stage)
                if agent
                else None,
                server_name=node.server_name,
                server=server_of(node.server),
                uninstall=run_of(node.server),
            )

        def pool_of(pool: NodePoolView) -> NodePoolNodesOut:
            update = pool.update
            progress = update.progress if update else None
            return NodePoolNodesOut(
                name=pool.name,
                wanted=pool.wanted,
                autoscaling=AutoscalingOut(min=pool.autoscaling.min, max=pool.autoscaling.max)
                if pool.autoscaling
                else None,
                ready=pool.ready,
                version=pool.version,
                upgrade_type=pool.upgrade_type,
                agent_selector=pool.agent_selector,
                update=PoolUpdateOut(
                    kind=update.kind,
                    message=update.message,
                    progress=UpdateProgressOut(total=progress.total, updated=progress.updated)
                    if progress
                    else None,
                    failed=update.failed,
                )
                if update
                else None,
                problems=list(pool.problems),
                free_agents=FreeAgentsOut(
                    matching=pool.free_agents.matching, free=pool.free_agents.free
                )
                if pool.free_agents
                else None,
                nodes=[node_of(node) for node in pool.nodes],
            )

        return cls(
            hosted_cluster=found.hosted_cluster,
            node_pools=[pool_of(pool) for pool in found.node_pools],
            unassigned=[
                UnassignedServerOut(
                    **ServerOut.fields_of(row, found.server_urls[row.id]), uninstall=run_of(row)
                )
                for row in found.unassigned
            ],
            uninstall=UninstallAvailabilityOut(
                available=found.uninstall_available, detail=found.uninstall_detail
            ),
            server_scan_error=found.server_scan_error,
            runs_error=found.runs_error,
        )


class UninstallNodeIn(_In):
    """``POST /clusters/{name}/nodes/{server_id}/uninstall``: the node's name, typed again."""

    server_name: str = Field(min_length=1, max_length=253)
