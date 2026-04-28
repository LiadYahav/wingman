"""Audit service — Git commits and MR history from Day1 + Specs repos."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import GitLabError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import CommitRecord, FileDiff, MRDetail
from wingman_shared.mr_conventions import parse_mr_to_detail

logger = logging.getLogger(__name__)


def _parse_commit(raw: dict[str, Any]) -> CommitRecord:
    return CommitRecord(
        id=raw.get("id", ""),
        short_id=raw.get("short_id", ""),
        title=raw.get("title", ""),
        author_name=raw.get("author_name", ""),
        author_email=raw.get("author_email", ""),
        authored_date=raw.get("authored_date", ""),
        message=raw.get("message", ""),
        web_url=raw.get("web_url", ""),
    )


class AuditService:
    """Aggregates commits and MRs across the day1 and specs repos."""

    def __init__(
        self,
        gitlab_day1: GitLabClient,
        gitlab_specs: GitLabClient,
        cache: CacheManager,
        cache_ttl: float = 30.0,
    ) -> None:
        self.gl_day1 = gitlab_day1
        self.gl_specs = gitlab_specs
        self.cache = cache
        self._ttl = cache_ttl

    async def list_commits(self, per_page: int = 50, page: int = 1) -> list[CommitRecord]:
        async def _fetch() -> list[CommitRecord]:
            loop = asyncio.get_event_loop()
            results: list[CommitRecord] = []
            for gl in (self.gl_day1, self.gl_specs):
                try:
                    _gl, _per_page, _page = gl, per_page, page
                    raws = await loop.run_in_executor(
                        None,
                        lambda g=_gl, p=_per_page, pg=_page: g.list_commits(per_page=p, page=pg),
                    )
                    results.extend(_parse_commit(r) for r in raws)
                except GitLabError as exc:
                    logger.warning("Failed to fetch commits: %s", exc)
            results.sort(key=lambda c: c.authored_date, reverse=True)
            return results[:per_page]

        return await self.cache.get_or_fetch(f"audit:day1:commits:{page}", _fetch, ttl=self._ttl)

    async def list_mrs(self, per_page: int = 50, page: int = 1) -> list[MRDetail]:
        async def _fetch() -> list[MRDetail]:
            loop = asyncio.get_event_loop()
            results: list[MRDetail] = []
            for gl in (self.gl_day1, self.gl_specs):
                try:
                    _gl, _per_page, _page = gl, per_page, page
                    raws = await loop.run_in_executor(
                        None,
                        lambda g=_gl, p=_per_page, pg=_page: g.list_mrs(
                            state="all", per_page=p, page=pg
                        ),
                    )
                    results.extend(
                        parse_mr_to_detail(r, extract_platform_author=False) for r in raws
                    )
                except GitLabError as exc:
                    logger.warning("Failed to fetch MRs: %s", exc)
            results.sort(key=lambda m: m.created_at, reverse=True)
            return results[:per_page]

        return await self.cache.get_or_fetch(f"audit:day1:mrs:{page}", _fetch, ttl=self._ttl)

    async def get_commit_diff(self, repo: str, sha: str) -> list[FileDiff]:
        """Get file diffs for a specific commit.

        repo hint is 'day1' or 'specs', but commits from the list endpoint
        may come from either project — we try both so the frontend doesn't
        need to track which sub-project each commit belongs to.
        """
        from wingman_shared.exceptions import NotFoundError  # noqa: PLC0415

        primary = self.gl_day1 if repo == "day1" else self.gl_specs
        fallback = self.gl_specs if repo == "day1" else self.gl_day1

        for gl in (primary, fallback):
            try:
                raws = gl.get_commit_diff(sha)
                return [
                    FileDiff(
                        old_path=d.get("old_path", ""),
                        new_path=d.get("new_path", ""),
                        diff=d.get("diff", ""),
                        new_file=d.get("new_file", False),
                        renamed_file=d.get("renamed_file", False),
                        deleted_file=d.get("deleted_file", False),
                    )
                    for d in raws
                ]
            except NotFoundError:
                continue
            except GitLabError as exc:
                logger.warning("Failed to get commit diff %s: %s", sha, exc)
                continue

        from fastapi import HTTPException  # noqa: PLC0415

        raise HTTPException(status_code=404, detail=f"Commit {sha} not found")
