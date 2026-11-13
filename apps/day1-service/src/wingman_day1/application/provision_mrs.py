"""The open day1 merge requests the provision-cluster workflow opened (ADR-0042's amendment).

The workflow opens its own merge request, with no label and its own title,
on ``provision-cluster/<file stem>`` (``wingman_day1.domain.workflows``).
Wingman counts it as an open create whoever started the run, from Wingman
or not: one cached read of the day1 project's open merge requests, kept to
those on the workflow's branch. Approving it stays in GitLab: the workflow
records no requester, so Wingman's "nobody approves their own change" rule
could not hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_day1.domain.workflows import provision_branch_stem
from wingman_day1.ports import RepoReads

OPEN_MRS_LIMIT: Final = 1000
"""Open day1 merge requests read at most, of every author; GitLab pages them by 100."""


@dataclass(frozen=True, slots=True)
class ProvisionMergeRequest:
    """An open merge request of the provision-cluster workflow, and the file stem it creates."""

    stem: str
    merge_request: MergeRequest


async def provision_merge_requests(day1: RepoReads) -> list[ProvisionMergeRequest]:
    """The provision-cluster workflow's open merge requests in the day1 project, newest first."""
    opened = await day1.merge_requests(state=MRState.OPENED, limit=OPEN_MRS_LIMIT)
    return [
        ProvisionMergeRequest(stem, mr)
        for mr in opened
        if (stem := provision_branch_stem(mr.source_branch)) is not None
    ]
