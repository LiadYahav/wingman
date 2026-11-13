"""The bodies of a cluster's live status: ``/{name}/status`` and ``/bulk-status``.

What the MCE reports for the HostedCluster the chart renders, and its NodePools.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import _In
from wingman_day1.domain.status import LiveStatus


class BulkStatusItemIn(_In):
    """One cluster to read live status for."""

    name: str = Field(min_length=1, max_length=63)
    mce: str = Field(min_length=1, max_length=63)


class BulkStatusIn(_In):
    """Many clusters at once."""

    clusters: list[BulkStatusItemIn] = Field(max_length=500)


class NodePoolStatusOut(BaseModel):
    """A NodePool's replicas, problems, and the update rolling through it."""

    name: str
    ready_replicas: int
    desired_replicas: int
    problems: list[str]
    updating: str | None = None
    """``version``, ``config`` or ``machine_template`` while an update rolls through it."""


class ClusterLiveStatusOut(BaseModel):
    """The legacy ``ClusterLiveStatus`` plus the HostedCluster that was read."""

    cluster_name: str
    hosted_cluster: str
    namespace: str
    hc_phase: str | None
    ocp_version: str | None
    hc_problems: list[str]
    node_pools: list[NodePoolStatusOut]
    error: str | None

    @classmethod
    def of(cls, status: LiveStatus) -> ClusterLiveStatusOut:
        """From a live status."""
        return cls(
            cluster_name=status.cluster_name,
            hosted_cluster=status.hosted_cluster,
            namespace=status.namespace,
            hc_phase=status.hc_phase,
            ocp_version=status.ocp_version,
            hc_problems=list(status.hc_problems),
            node_pools=[
                NodePoolStatusOut(
                    name=p.name,
                    ready_replicas=p.ready_replicas,
                    desired_replicas=p.desired_replicas,
                    problems=list(p.problems),
                    updating=p.updating,
                )
                for p in status.node_pools
            ],
            error=status.error,
        )
