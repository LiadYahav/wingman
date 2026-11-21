"""One cluster's merge request that gives its NodePools the deployment's excluded Agent labels.

ADR-0065: a cluster created before ``DAY1_EXCLUDED_AGENT_LABELS`` was set, or
before its keys changed, takes them only through its own merge request,
never all at once. The plan says, per NodePool (by the name the MCE shows),
what it excludes now and whether the merge request writes the deployment's
keys on it; a Replace NodePool (every node would be replaced) and a KubeVirt
cluster's (no Agents) are left out, with why, and the merge request's text
lists each NodePool it leaves out, and why. The merge request is an edit of the file's text,
every other line byte for byte (ADR-0037), through the cluster's own modify,
guarded by the commit the plan was read at (ADR-0006).
"""

from __future__ import annotations

from dataclasses import dataclass

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.changes import ProvisionResult
from wingman_day1.domain.cluster_edits import SetValue
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.cluster_text import edit_values
from wingman_day1.domain.errors import InvalidClusterFileError, InvalidInputError
from wingman_day1.domain.excluded_agent_labels import FILE_KEY, PoolPlan, plan, summary
from wingman_day1.domain.input_paths import InputPath
from wingman_day1.domain.paths import ClusterRef


@dataclass(frozen=True, slots=True)
class AgentLabelsPlan:
    """What the cluster's merge request would do, read from its file on ``main``."""

    ref: ClusterRef
    labels: tuple[str, ...]
    """The deployment's keys."""
    last_commit_id: str
    """The commit the file was read at: the merge request's guard."""
    nodepools: tuple[PoolPlan, ...]
    content: str

    @property
    def changes(self) -> tuple[PoolPlan, ...]:
        """The nodepools the merge request writes the keys on."""
        return tuple(p for p in self.nodepools if p.change)


class AgentLabelsService:
    """The plan and the merge request of one cluster (``DAY1_EXCLUDED_AGENT_LABELS``)."""

    def __init__(self, clusters: ClusterService, labels: tuple[str, ...]) -> None:
        """Read and write through ``clusters``; ``labels`` are the deployment's keys."""
        self._clusters = clusters
        self.labels = labels

    async def plan(self, ref: ClusterRef) -> AgentLabelsPlan:
        """Each nodepool of the file on ``main``, and whether the merge request changes it."""
        cluster = await self._clusters.get(ref)
        try:
            values = load_values(cluster.content)
        except InvalidClusterFileError as exc:
            raise InvalidInputError(
                f"cluster {ref.name!r} cannot be planned: its file does not parse", exc.problems
            ) from exc
        pools = plan(values, self.labels, cluster_name=cluster.hosted_cluster.cluster_name)
        return AgentLabelsPlan(ref, self.labels, cluster.last_commit_id, pools, cluster.content)

    async def apply(
        self, ref: ClusterRef, *, user: User, last_commit_id: str | None = None
    ) -> ProvisionResult:
        """Open the cluster's merge request; nothing to change is a 422. Never retried."""
        planned = await self.plan(ref)
        if not planned.changes:
            raise InvalidInputError(
                f"cluster {ref.name!r} has nothing to change",
                [f"nodepool[{p.index}] {p.name}: {p.reason}" for p in planned.nodepools]
                or ["the cluster file has no nodepool"],
            )
        edits = [
            SetValue(InputPath(("nodepool", p.index, FILE_KEY)), list(self.labels))
            for p in planned.changes
        ]
        return await self._clusters.modify(
            ref,
            edit_values(planned.content, edits),
            user=user,
            summary=summary(ref.name, self.labels, planned.nodepools),
            last_commit_id=last_commit_id or planned.last_commit_id,
        )
