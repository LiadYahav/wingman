"""The body of ``GET /api/day1/placement``: every candidate MCE for a new cluster (ADR-0050)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from wingman_day1.domain.placement import Candidate, Placement


class PlacementCheckOut(BaseModel):
    """One required check of a candidate MCE."""

    check: Literal["version", "free_pods", "servers", "readable"]
    status: Literal["pass", "fail", "unknown", "not_checked"]
    """``not_checked``: live MCE reads are off; it does not block the pick."""
    detail: str


class SpareServersOut(BaseModel):
    """An MCE's spare servers in server-scan."""

    total: int
    usable: int


class ExcludedNodesOut(BaseModel):
    """Nodes left out of the free pods (only workers count), by the first reason that applies."""

    control_plane: int
    infra: int
    not_ready: int
    unschedulable: int
    tainted: int
    """With a ``NoSchedule`` or ``NoExecute`` taint."""


class NodeTypeOut(BaseModel):
    """One node type the new cluster needs, on one candidate MCE."""

    infra_env: str
    needed: int
    free_agents: int | None
    """Free Agents in the InfraEnv; ``None`` when the MCE's Agents could not be read."""
    healthy: int | None
    """Of those, the ones whose server-scan server is usable; ``None`` without server-scan."""
    not_in_server_scan: int
    health_checked: bool
    """``False`` when this deployment has no server-scan: free Agents counted as they are."""
    status: Literal["pass", "fail", "unknown"]
    detail: str


class NeedOut(BaseModel):
    """Replicas the new cluster needs of one node type, summed over its nodepools."""

    infra_env: str
    replicas: int


class FreePodsOut(BaseModel):
    """How an MCE's free pods were counted."""

    free: int
    allocatable: int
    used: int
    nodes_counted: int
    nodes_excluded: ExcludedNodesOut


class PlacementCandidateOut(BaseModel):
    """One candidate MCE: its checks, its numbers, its place in the ranking."""

    mce: str
    eligible: bool
    picked: bool
    rank: int | None
    behind_on: Literal["owner_clusters", "clusters", "spare_servers", "name"] | None
    checks: list[PlacementCheckOut]
    node_types: list[NodeTypeOut]
    versions: list[str]
    clusters: int
    open_creates: int
    owner_clusters: int | None
    spare: SpareServersOut | None
    spare_detail: str | None
    pods: FreePodsOut | None

    @classmethod
    def of(cls, candidate: Candidate) -> PlacementCandidateOut:
        """From a domain candidate."""
        picture = candidate.picture
        pods = picture.pods
        return cls(
            mce=candidate.mce,
            eligible=candidate.eligible,
            picked=candidate.picked,
            rank=candidate.rank,
            behind_on=candidate.behind_on.value if candidate.behind_on else None,
            checks=[
                PlacementCheckOut(check=c.check.value, status=c.status.value, detail=c.detail)
                for c in candidate.checks
            ],
            node_types=[
                NodeTypeOut(
                    infra_env=t.infra_env,
                    needed=t.needed,
                    free_agents=t.free_agents,
                    healthy=t.healthy,
                    not_in_server_scan=t.not_in_server_scan,
                    health_checked=t.health_checked,
                    status=t.status.value,
                    detail=t.detail,
                )
                for t in picture.node_types
            ],
            versions=list(picture.versions.versions),
            clusters=picture.clusters,
            open_creates=picture.open_creates,
            owner_clusters=picture.owner_clusters,
            spare=(
                SpareServersOut(total=picture.spare.total, usable=picture.spare.usable)
                if picture.spare
                else None
            ),
            spare_detail=picture.spare_detail,
            pods=(
                FreePodsOut(
                    free=pods.free,
                    allocatable=pods.allocatable,
                    used=pods.used,
                    nodes_counted=pods.nodes_counted,
                    nodes_excluded=ExcludedNodesOut(
                        control_plane=pods.excluded.control_plane,
                        infra=pods.excluded.infra,
                        not_ready=pods.excluded.not_ready,
                        unschedulable=pods.excluded.unschedulable,
                        tainted=pods.excluded.tainted,
                    ),
                )
                if pods
                else None
            ),
        )


class PlacementOut(BaseModel):
    """``GET /placement``: every candidate MCE for a new cluster, and Wingman's pick (ADR-0050)."""

    site: str
    env: str
    version: str | None
    owner: str | None
    flavor: str | None
    min_free_pods: int
    live_reads: bool
    """``False`` when live MCE reads are off: free pods and servers were not checked."""
    needs: list[NeedOut]
    """The servers the new cluster needs, per node type, summed; empty when none is named."""
    versions: list[str]
    """Every version some candidate hosts, newest first."""
    pick: str | None
    why: str | None
    problems: list[str]
    server_scan_error: str | None
    candidates: list[PlacementCandidateOut]

    @classmethod
    def of(cls, placement: Placement) -> PlacementOut:
        """From the domain result."""
        inputs = placement.inputs
        return cls(
            site=inputs.site,
            env=inputs.env.value,
            version=inputs.version,
            owner=inputs.owner,
            flavor=inputs.flavor,
            min_free_pods=inputs.min_free_pods,
            live_reads=placement.live_reads,
            needs=[NeedOut(infra_env=t, replicas=n) for t, n in inputs.needs],
            versions=list(placement.versions),
            pick=placement.pick,
            why=placement.why,
            problems=list(placement.problems),
            server_scan_error=placement.server_scan_error,
            candidates=[PlacementCandidateOut.of(c) for c in placement.candidates],
        )
