"""History across the day1 and specs projects: commits and merge requests.

Each item carries the repository it came from, so a client can address it
without guessing (the legacy list tagged every MR ``day1``, and expanding a
specs MR asked the wrong project).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from wingman_core.application.approvals import PendingChange, describe
from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, FileDiff
from wingman_day1.application.approvals import RepoKey
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.ports import RepoReads


@dataclass(frozen=True, slots=True)
class AuditCommit:
    """A commit on a managed repository's default branch."""

    repo: RepoKey
    commit: Commit


@dataclass(frozen=True, slots=True)
class AuditMergeRequest:
    """A merge request in a managed repository, any state."""

    repo: RepoKey
    change: PendingChange


class AuditService:
    """Commits and merge requests, newest first, one page at a time."""

    def __init__(self, repos: Mapping[RepoKey, RepoReads]) -> None:
        """Read through ``repos`` (cached)."""
        self._repos = dict(repos)

    async def commits(self, *, per_page: int, page: int) -> list[AuditCommit]:
        """One page of commits merged across both repositories."""
        wanted = per_page * page
        lists = await asyncio.gather(*(r.commits(limit=wanted) for r in self._repos.values()))
        merged = sorted(
            (AuditCommit(repo, c) for repo, cs in zip(self._repos, lists, strict=True) for c in cs),
            key=lambda item: item.commit.authored_at,
            reverse=True,
        )
        return merged[per_page * (page - 1) : wanted]

    async def merge_requests(self, *, per_page: int, page: int) -> list[AuditMergeRequest]:
        """One page of merge requests (any state) merged across both repositories."""
        wanted = per_page * page
        lists = await asyncio.gather(
            *(r.merge_requests(state=None, limit=wanted) for r in self._repos.values())
        )
        merged = sorted(
            (
                AuditMergeRequest(repo, describe(mr))
                for repo, mrs in zip(self._repos, lists, strict=True)
                for mr in mrs
            ),
            key=lambda item: (item.change.merge_request.created_at, item.change.merge_request.ref),
            reverse=True,
        )
        return merged[per_page * (page - 1) : wanted]

    async def commit_diff(self, repo: RepoKey, sha: str) -> list[FileDiff]:
        """A commit's diff. A SHA names one commit everywhere, so the other repo is tried too.

        The web app tags every day1-service commit ``day1``; trying the
        second project keeps its specs commits expandable.
        """
        order = [repo, *(r for r in self._repos if r is not repo)]
        for key in order:
            try:
                return await self._repos[key].commit_diff(sha)
            except NotFoundError:
                continue
        raise ResourceNotFoundError(f"commit {sha} is in neither the day1 nor the specs project")
