"""One cluster's merge request that gives its NodePools the deployment's excluded Agent labels.

ADR-0065: a cluster created before ``DAY1_EXCLUDED_AGENT_LABELS`` was set, or
before its keys changed, takes them only through its own merge request,
never all at once. The plan says, per NodePool (by the name the MCE shows),
what it excludes now and whether the merge request writes the deployment's
keys on it; a Replace NodePool (every node would be replaced) and a KubeVirt
cluster's (no Agents) are left out, with why, and the merge request's text
lists each NodePool it leaves out, and why. The merge request is an edit of
the file's text, every other line byte for byte (ADR-0037), through the
cluster's own modify, guarded by the commit the plan was read at (ADR-0006).

One at a time: while an open Wingman merge request that modifies the cluster
already has the keys wherever the plan would write them (its branch's file
plans no change), the plan names it and the merge request is not opened
again (409), as a sync's (``open_syncs``) and a create's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    Repo,
    ResourceType,
    Verb,
    parse_mr_title,
)
from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.changes import ClusterAction, ProvisionResult
from wingman_day1.domain.cluster_edits import SetValue
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.cluster_text import edit_values
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    InvalidClusterFileError,
    InvalidInputError,
)
from wingman_day1.domain.excluded_agent_labels import FILE_KEY, PoolPlan, plan, summary
from wingman_day1.domain.input_paths import InputPath
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.ports import RepoReads

OPEN_MODIFIES_LIMIT: Final = 1000
"""Open Wingman modify MRs read at most, of every cluster."""


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
    open_merge_request: MergeRequest | None = None
    """An open merge request that already writes the keys where this plan would; the newest."""

    @property
    def changes(self) -> tuple[PoolPlan, ...]:
        """The nodepools the merge request writes the keys on."""
        return tuple(p for p in self.nodepools if p.change)


class AgentLabelsService:
    """The plan and the merge request of one cluster (``DAY1_EXCLUDED_AGENT_LABELS``)."""

    def __init__(self, clusters: ClusterService, day1: RepoReads, labels: tuple[str, ...]) -> None:
        """Read and write through ``clusters``, open MRs from ``day1``; ``labels``: the keys."""
        self._clusters = clusters
        self._day1 = day1
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
        name = cluster.hosted_cluster.cluster_name
        pools = plan(values, self.labels, cluster_name=name)
        opened = await self._carried_by(ref, name) if any(p.change for p in pools) else None
        return AgentLabelsPlan(
            ref, self.labels, cluster.last_commit_id, pools, cluster.content, opened
        )

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
        opened = planned.open_merge_request
        if opened is not None:
            raise AlreadyInUseError(
                f"an open merge request already excludes {', '.join(self.labels)} from the "
                f"NodePools of {ref.name}: !{opened.ref.iid} {opened.web_url}"
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

    async def _carried_by(self, ref: ClusterRef, cluster_name: str) -> MergeRequest | None:
        """The newest open Wingman MR modifying the cluster whose file plans no change, if any.

        Its branch's file is read as it is now: whoever wrote the keys there
        (this merge request, or a person's edit), it carries the change.
        """
        opened = await self._day1.merge_requests(
            state=MRState.OPENED,
            labels=(WINGMAN_LABEL, ClusterAction.MODIFY.value),
            limit=OPEN_MODIFIES_LIMIT,
        )
        for merge_request in opened:
            title = parse_mr_title(merge_request.title)
            if title is None or (title.repo, title.verb, title.resource_type) != _MODIFY_CLUSTER:
                continue
            if title.resource_name != ref.name:
                continue
            try:
                found = await self._day1.read(ref.path, ref=merge_request.source_branch)
                values = load_values(found.content)
            except (NotFoundError, InvalidClusterFileError):
                continue  # the branch is gone, or its file does not parse: it carries nothing
            if not any(p.change for p in plan(values, self.labels, cluster_name=cluster_name)):
                return merge_request
        return None


_MODIFY_CLUSTER: Final = (Repo.DAY1, Verb.MODIFY, ResourceType.CLUSTER)
