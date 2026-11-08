"""Approvals for the day1 and specs projects, on ``wingman_core``'s ``Approvals``.

A merge request is addressed by ``(repo, iid)`` where ``repo`` maps to exactly
one project (ADR-0007). Approving merges the commit the approver reviewed
(``sha``); if CI, the allocate-segment workflow or a person pushed since,
the merge is refused rather than merging what nobody saw (ADR-0006).

Editing an MR's files adds a commit on top of its branch, never a force-push,
guarded per file by the revision the reviewer saw. A cluster file edited this
way must keep every automation-owned key as the branch has it.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from wingman_core.application.approvals import Approvals, PendingChange, describe
from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import FileChange, FileDiff, RepoPath
from wingman_core.domain.merge_request import MergeRequestRef, MRState
from wingman_core.domain.mr_conventions import WINGMAN_LABEL
from wingman_core.domain.users import User
from wingman_core.ports.gitlab import GitLabPort
from wingman_day1.domain import paths
from wingman_day1.domain.changes import commit_author
from wingman_day1.domain.cluster_file import edit_problems
from wingman_day1.domain.errors import InvalidInputError, InvalidSpecError, StaleError
from wingman_day1.domain.specs import parse_spec
from wingman_day1.ports import RepoReads


class RepoKey(StrEnum):
    """The repositories day1 manages; each is one project."""

    DAY1 = "day1"
    SPECS = "specs"


@dataclass(frozen=True, slots=True)
class Change:
    """A merge request in a managed repository."""

    repo: RepoKey
    pending: PendingChange


class ApprovalService:
    """List, show, edit, approve and reject Wingman MRs in the day1 and specs projects."""

    def __init__(self, gitlab: GitLabPort, repos: Mapping[RepoKey, RepoReads]) -> None:
        """Act through ``gitlab``; ``repos`` give each project and its cached MR lists."""
        self._gitlab = gitlab
        self._approvals = Approvals(gitlab)
        self._repos = dict(repos)

    async def pending(self) -> list[Change]:
        """Open Wingman MRs in both projects, newest first, whatever branch they target."""
        lists = await asyncio.gather(
            *(
                reads.merge_requests(state=MRState.OPENED, labels=(WINGMAN_LABEL,))
                for reads in self._repos.values()
            )
        )
        changes = [
            Change(repo, describe(mr))
            for repo, mrs in zip(self._repos, lists, strict=True)
            for mr in mrs
        ]
        return sorted(
            changes,
            key=lambda c: (c.pending.merge_request.created_at, c.pending.merge_request.ref),
            reverse=True,
        )

    async def get(self, repo: RepoKey, iid: int) -> tuple[Change, list[FileDiff]]:
        """One MR and what it changes; ``sha`` is the head the diff was taken at.

        GitLab updates an MR's own ``sha`` in a background job after a push,
        so for an open MR the branch head is read instead, *before* the diff:
        approving that ``sha`` can then only merge what the reviewer saw, or
        less, never more.
        """
        ref = await self._ref(repo, iid)
        change = await self._current(ref)
        diffs = await self._gitlab.merge_request_diff(ref)
        return Change(repo, change), diffs

    async def approve(self, repo: RepoKey, iid: int, *, sha: str, approver: User) -> Change:
        """Approve and merge the reviewed commit; the approver may not be the requester."""
        ref = await self._ref(repo, iid)
        merged = await self._approvals.approve(
            ref, approver=approver, reviewed_sha=sha, managed=await self._managed()
        )
        reads = self._repos[repo]
        reads.forget_files()
        reads.forget_merge_requests()
        return Change(repo, describe(merged))

    async def reject(self, repo: RepoKey, iid: int) -> Change:
        """Close without merging."""
        ref = await self._ref(repo, iid)
        closed = await self._approvals.reject(ref, managed=await self._managed())
        self._repos[repo].forget_merge_requests()
        return Change(repo, describe(closed))

    async def update(
        self,
        repo: RepoKey,
        iid: int,
        files: Mapping[str, str],
        *,
        user: User,
        sha: str | None = None,
        message: str = "",
    ) -> tuple[Change, list[FileDiff]]:
        """Commit edited files onto the MR's branch, on top of whatever is there."""
        ref = await self._ref(repo, iid)
        change = await self._current(ref)
        merge_request = change.merge_request
        if merge_request.state is not MRState.OPENED:
            raise StaleError(f"{ref} is {merge_request.state}; only an open MR can be edited")
        if sha is not None and sha != merge_request.sha:
            raise StaleError(
                f"{ref} moved since it was reviewed ({sha[:8]} → {merge_request.sha[:8]}); "
                "reload it before editing"
            )
        reviewed = sha or merge_request.sha
        diffs = await self._gitlab.merge_request_diff(ref)
        editable = {str(d.new_path) for d in diffs if not d.deleted_file}
        outside = sorted(set(files) - editable)
        if outside:
            raise InvalidInputError(
                "only files this merge request changes can be edited here", outside
            )
        if not files:
            raise InvalidInputError("nothing to commit", ["no files were sent"])
        changes = [
            await self._guarded_update(repo, ref, RepoPath(path), content, at=reviewed)
            for path, content in sorted(files.items())
        ]
        await self._gitlab.commit(
            ref.project_id,
            branch=merge_request.source_branch,
            message=(message or f"Edit {len(changes)} file(s) of !{iid} in Wingman review")
            + f"\n\nRequested-by: {user.username}",
            changes=changes,
            author=commit_author(user),
        )
        self._repos[repo].forget_merge_requests()
        return await self.get(repo, iid)

    # ── Internals ───────────────────────────────────────────────────────────

    async def _ref(self, repo: RepoKey, iid: int) -> MergeRequestRef:
        return MergeRequestRef((await self._repos[repo].project()).id, iid)

    async def _managed(self) -> set[int]:
        projects = await asyncio.gather(*(reads.project() for reads in self._repos.values()))
        return {p.id for p in projects}

    async def _current(self, ref: MergeRequestRef) -> PendingChange:
        """The MR, with ``sha`` set to its source branch's real head while it is open."""
        change = await self._approvals.get(ref, managed=await self._managed())
        merge_request = change.merge_request
        if merge_request.state is not MRState.OPENED:
            return change
        try:
            head = await self._gitlab.list_commits(
                ref.project_id, ref=merge_request.source_branch, limit=1
            )
        except NotFoundError:
            return change
        if not head or head[0].id == merge_request.sha:
            return change
        return describe(dataclasses.replace(merge_request, sha=head[0].id))

    async def _guarded_update(
        self, repo: RepoKey, ref: MergeRequestRef, path: RepoPath, content: str, *, at: str
    ) -> FileChange:
        try:
            current = await self._gitlab.read_file(ref.project_id, path, at)
        except NotFoundError:
            return FileChange.create(path, content)
        if repo is RepoKey.DAY1 and paths.parse_hosted_clusters_path(path) is not None:
            problems = edit_problems(current.content, content)
            if problems:
                raise InvalidInputError(f"the edit of {path} is not valid", problems)
        if repo is RepoKey.SPECS and str(path).endswith(paths.SPEC_SUFFIX):
            try:
                parse_spec(content, expected_name=path.name.removesuffix(paths.SPEC_SUFFIX))
            except InvalidSpecError as exc:
                raise InvalidInputError(f"the edit of {path} is not valid", exc.problems) from exc
        return FileChange.update(path, content, last_commit_id=current.last_commit_id)
