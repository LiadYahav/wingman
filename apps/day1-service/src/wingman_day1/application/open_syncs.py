"""The open MRs that sync a cluster to a flavor version, read from GitLab (ADR-0044).

A cluster's pending update is an open day1 MR titled ``Sync cluster <name>
to spec <flavor> v<version>``, whether a rollout or a person opened it
(``wingman_day1.domain.rollout``). GitLab is the only state: the list is
one cached read of the open Wingman sync MRs, so a restarted replica, or a
second one, sees the same MRs.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from wingman_core.domain.errors import GitError
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import WINGMAN_LABEL
from wingman_day1.domain.rollout import SyncTarget, sync_target
from wingman_day1.ports import RepoReads, RolloutMergeRequests

logger = logging.getLogger(__name__)

SYNC_LABEL: Final = "sync"
"""The label every sync MR carries (the action), a rollout's included."""
OPEN_SYNCS_LIMIT: Final = 5000
"""Open sync MRs read at most; more than one per cluster of a large fleet."""


@dataclass(frozen=True, slots=True)
class OpenSync:
    """An open MR and the cluster, flavor and version it syncs to."""

    target: SyncTarget
    merge_request: MergeRequest


@dataclass(frozen=True, slots=True)
class OpenSyncs:
    """Open sync MRs by cluster name."""

    by_cluster: dict[str, tuple[OpenSync, ...]] = field(default_factory=dict)

    def to(self, cluster: str, flavor: str, version: str) -> MergeRequest | None:
        """The open MR that moves ``cluster`` to ``flavor`` ``version``, if any (the newest)."""
        for found in self.by_cluster.get(cluster, ()):
            if (found.target.flavor, found.target.version) == (flavor, version):
                return found.merge_request
        return None

    def older(self, cluster: str, flavor: str, version: str) -> list[MergeRequest]:
        """Open MRs that move ``cluster`` to another version of ``flavor`` (superseded)."""
        return [
            found.merge_request
            for found in self.by_cluster.get(cluster, ())
            if found.target.flavor == flavor and found.target.version != version
        ]


def index(merge_requests: Sequence[MergeRequest]) -> OpenSyncs:
    """Open sync MRs, newest first, by the cluster their title names."""
    found: defaultdict[str, list[OpenSync]] = defaultdict(list)
    for mr in merge_requests:
        target = sync_target(mr.title)
        if target is not None and mr.state is MRState.OPENED:
            found[target.cluster].append(OpenSync(target, mr))
    return OpenSyncs({name: tuple(items) for name, items in found.items()})


async def open_syncs(day1: RepoReads) -> OpenSyncs:
    """The day1 project's open Wingman sync MRs (one cached read)."""
    return index(
        await day1.merge_requests(
            state=MRState.OPENED, labels=(WINGMAN_LABEL, SYNC_LABEL), limit=OPEN_SYNCS_LIMIT
        )
    )


async def supersede(
    rollouts: RolloutMergeRequests,
    olds: Sequence[MergeRequest],
    *,
    by: MergeRequest,
    flavor: str,
    version: str,
) -> list[tuple[MergeRequest, GitError | None]]:
    """Close each open MR in ``olds``, with a comment pointing to ``by``; one per cluster stays.

    A failure is logged and returned, never retried (ADR-0006): ``by`` is open
    either way, and the next rollout run finds the old MR again.
    """
    note = (
        f"Superseded by !{by.ref.iid} ({by.web_url}), which syncs this cluster to flavor "
        f"`{flavor}` v{version}. Wingman closed this merge request: review and merge "
        f"!{by.ref.iid} instead (ADR-0044)."
    )
    done: list[tuple[MergeRequest, GitError | None]] = []
    for old in olds:
        try:
            await rollouts.supersede(old.ref, note=note)
        except GitError as exc:
            logger.warning(
                "superseded merge request %s not closed: %s: %s",
                old.ref,
                type(exc).__name__,
                exc,
                extra={"event": "sync_mr_not_superseded", "flavor": flavor, "version": version},
            )
            done.append((old, exc))
        else:
            done.append((old, None))
    return done
