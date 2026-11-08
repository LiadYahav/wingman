"""The approval flow for Wingman's merge requests, written once for every service.

A change is a merge request labelled ``wingman``. Approving it approves and
merges it as Wingman's service account; rejecting it closes it. Two rules:

- Nobody approves their own change. The requester is read from the MR
  description footer (``Author:``), because GitLab shows the service account
  as every MR's author (ADR-0007).
- Only MRs in projects the calling service manages can be acted on, and they
  are addressed by ``(project, iid)``: never by number alone.

The merge carries the commit the approver reviewed, so commits pushed after
the review (by a person, by CI or by the allocate-segment workflow) are not
merged unseen (ADR-0006).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Collection
from dataclasses import dataclass

from wingman_core.domain.errors import NotFoundError, PermissionDeniedError
from wingman_core.domain.merge_request import MergeRequest, MergeRequestRef, MRState
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    MRMetadata,
    ParsedTitle,
    parse_mr_description,
    parse_mr_title,
)
from wingman_core.domain.users import User
from wingman_core.ports.gitlab import GitLabPort

logger = logging.getLogger(__name__)


class SelfApprovalError(Exception):
    """The approver requested this change."""


class UnmanagedProjectError(Exception):
    """The MR is not in a project this service manages, or is not a Wingman MR."""


@dataclass(frozen=True, slots=True)
class PendingChange:
    """An open Wingman MR and what its title and footer say about it."""

    merge_request: MergeRequest
    requested_by: str
    title: ParsedTitle | None
    metadata: MRMetadata | None


def describe(merge_request: MergeRequest) -> PendingChange:
    """Read the requester, title and footer of ``merge_request``."""
    metadata = parse_mr_description(merge_request.description)
    return PendingChange(
        merge_request=merge_request,
        requested_by=metadata.author if metadata else merge_request.author_username,
        title=parse_mr_title(merge_request.title),
        metadata=metadata,
    )


class Approvals:
    """Read, approve and reject Wingman MRs in a set of projects."""

    def __init__(self, gitlab: GitLabPort) -> None:
        """Act through ``gitlab`` (Wingman's service account)."""
        self._gitlab = gitlab

    async def get(self, ref: MergeRequestRef, *, managed: Collection[int]) -> PendingChange:
        """One Wingman MR in a managed project; while it is open, ``sha`` is its branch head.

        GitLab updates an MR's ``sha`` in a background job after a push, so it
        can still name the commit before the last one. A reviewer must approve
        what the branch holds (the merge compares the branch head), so the
        head is read instead; read the diff after this, and approving that
        ``sha`` merges what the reviewer saw, or less, never more.
        """
        if ref.project_id not in managed:
            raise UnmanagedProjectError(f"project {ref.project_id} is not managed here")
        merge_request = await self._gitlab.get_merge_request(ref)
        if WINGMAN_LABEL not in merge_request.labels:
            raise UnmanagedProjectError(f"{ref} is not a Wingman merge request")
        return describe(await self._at_branch_head(merge_request))

    async def _at_branch_head(self, merge_request: MergeRequest) -> MergeRequest:
        if merge_request.state is not MRState.OPENED:
            return merge_request
        try:
            head = await self._gitlab.list_commits(
                merge_request.ref.project_id, ref=merge_request.source_branch, limit=1
            )
        except NotFoundError:
            return merge_request
        if not head or head[0].id == merge_request.sha:
            return merge_request
        return dataclasses.replace(merge_request, sha=head[0].id)

    async def approve(
        self,
        ref: MergeRequestRef,
        *,
        approver: User,
        reviewed_sha: str,
        managed: Collection[int],
    ) -> MergeRequest:
        """Approve and merge, if ``approver`` did not request it and nothing moved since review."""
        change = await self.get(ref, managed=managed)
        if change.requested_by == approver.username:
            raise SelfApprovalError(f"{approver.username} requested {ref} and cannot approve it")
        try:
            await self._gitlab.approve_merge_request(ref)
        except PermissionDeniedError:
            # GitLab refuses an approval the service account already gave, or one
            # by an MR's own author when the project forbids it. The merge below
            # still fails if the project actually requires approvals.
            logger.info("GitLab did not record an approval for %s; merging anyway", ref)
        return await self._gitlab.merge_merge_request(ref, sha=reviewed_sha)

    async def reject(self, ref: MergeRequestRef, *, managed: Collection[int]) -> MergeRequest:
        """Close without merging."""
        await self.get(ref, managed=managed)
        return await self._gitlab.close_merge_request(ref)
