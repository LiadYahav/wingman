"""History across the day1 and specs projects: commits and merge requests.

Each item carries the repository it came from, so a client can address it
without guessing (the legacy list tagged every MR ``day1``, and expanding a
specs MR asked the wrong project). A viewer's day1 commits are those that
changed a file in a tenant's folder (``commits(day1_folders=...)``, ADR-0068).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from wingman_core.application.approvals import PendingChange, describe
from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, FileDiff, RepoPath
from wingman_core.domain.mr_conventions import WINGMAN_LABEL
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

    async def commits(
        self, *, per_page: int, page: int, day1_folders: Sequence[RepoPath] | None = None
    ) -> list[AuditCommit]:
        """One page of commits merged across both repositories.

        ``day1_folders``: the day1 commits are only those that changed a file
        under one of them, each once; ``None``, every day1 commit.
        """
        wanted = per_page * page
        lists = await asyncio.gather(
            *(self._commits(key, wanted, day1_folders) for key in self._repos)
        )
        merged = sorted(
            (AuditCommit(repo, c) for repo, cs in zip(self._repos, lists, strict=True) for c in cs),
            key=lambda item: item.commit.authored_at,
            reverse=True,
        )
        return merged[per_page * (page - 1) : wanted]

    async def _commits(
        self, key: RepoKey, wanted: int, folders: Sequence[RepoPath] | None
    ) -> list[Commit]:
        reads = self._repos[key]
        if key is not RepoKey.DAY1 or folders is None:
            return await reads.commits(limit=wanted)
        histories = await asyncio.gather(*(reads.history(f, limit=wanted) for f in folders))
        unique = {c.id: c for history in histories for c in history}
        return sorted(unique.values(), key=lambda c: c.authored_at, reverse=True)[:wanted]

    async def merge_requests(self, *, per_page: int, page: int) -> list[AuditMergeRequest]:
        """One page of Wingman's merge requests (any state) merged across both repositories.

        Only MRs labelled ``wingman``: those are the ones Wingman opened, and the
        only ones an approval detail can open (``Approvals.get`` refuses the rest).
        """
        wanted = per_page * page
        lists = await asyncio.gather(
            *(
                r.merge_requests(state=None, labels=(WINGMAN_LABEL,), limit=wanted)
                for r in self._repos.values()
            )
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

    async def commit_diff(self, repo: RepoKey, sha: str) -> tuple[RepoKey, list[FileDiff]]:
        """A commit's diff, and the project it is in.

        A SHA names one commit everywhere, so the other repo is tried too: the
        web app tags every day1-service commit ``day1``; trying the second
        project keeps its specs commits expandable.
        """
        order = [repo, *(r for r in self._repos if r is not repo)]
        for key in order:
            try:
                return key, await self._repos[key].commit_diff(sha)
            except NotFoundError:
                continue
        raise ResourceNotFoundError(f"commit {sha} is in neither the day1 nor the specs project")
