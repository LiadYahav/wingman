"""What a day1 sync MR moves a cluster to, read back from its title (ADR-0044).

Every MR that syncs a cluster to a flavor version, whether a person opened it
or a rollout did, is titled ``[Wingman/Day1] Sync cluster <name> to spec
<flavor> v<version>`` (``wingman_core.domain.mr_conventions``, ADR-0007). An
open one is the cluster's pending update; one to an older version of the
same flavor is superseded when a newer one opens. The title is the contract,
so a rollout finds the MRs a person opened by hand as well as its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, parse_mr_title

_TARGET: Final = re.compile(r" to spec (?P<flavor>\S+) v(?P<version>\S+)$")


class RolloutTrigger(StrEnum):
    """What started a rollout run; the ``trigger`` label of ``wingman_rollout_runs_total``."""

    MERGE = "merge"
    """Wingman merged the flavor's MR."""
    WEBHOOK = "webhook"
    """The specs project's webhook reported a push or a merge."""
    RECONCILE = "reconcile"
    """An admin pressed Reconcile."""
    READ = "read"
    """The rollout status was read while work was pending."""


class RolloutOutcome(StrEnum):
    """What a run did with one cluster's MR; ``wingman_rollout_merge_requests_total``'s label."""

    OPENED = "opened"
    RECOVERED = "recovered"
    """An MR opened for a branch an earlier run committed to and left without one."""
    SUPERSEDED = "superseded"
    """An open MR to an older version was closed for the new one."""
    FAILED = "failed"
    UNCONFIRMED = "unconfirmed"
    """GitLab did not confirm the write (ADR-0006): the next run checks before sending again."""
    NOT_SENT = "not_sent"
    """Not started: GitLab stopped answering earlier in the run."""


@dataclass(frozen=True, slots=True)
class SyncTarget:
    """A sync MR's cluster, and the flavor and version it moves the cluster to."""

    cluster: str
    flavor: str
    version: str


def sync_target(title: str) -> SyncTarget | None:
    """The target of a day1 sync MR's title; ``None`` for any other title."""
    parsed = parse_mr_title(title)
    if parsed is None or (parsed.repo, parsed.verb, parsed.resource_type) != (
        Repo.DAY1,
        Verb.SYNC,
        ResourceType.CLUSTER,
    ):
        return None
    match = _TARGET.search(title)
    if match is None:
        return None
    return SyncTarget(parsed.resource_name, match["flavor"], match["version"])
