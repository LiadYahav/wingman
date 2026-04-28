"""Audit service for Day2 — aggregates commits and MR history across all team projects."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabGroupClient
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
    def __init__(
        self,
        group_client: GitLabGroupClient,
        cache: CacheManager,
        cache_ttl: float = 30.0,
    ) -> None:
        self.group_client = group_client
        self.cache = cache
        self._ttl = cache_ttl

    def _teams(self) -> list[str]:
        try:
            return self.group_client.list_project_paths()
        except GitLabError as exc:
            logger.error("Failed to list team projects for audit: %s", exc)
            return []

    async def list_commits(self, per_page: int = 50, page: int = 1) -> list[CommitRecord]:
        async def _fetch() -> list[CommitRecord]:
            loop = asyncio.get_event_loop()
            all_commits: list[CommitRecord] = []
            for team in self._teams():
                gl = self.group_client.get_project_client(team)
                try:
                    _gl, _per_page, _page = gl, per_page, page
                    raws = await loop.run_in_executor(
                        None,
                        lambda g=_gl, p=_per_page, pg=_page: g.list_commits(per_page=p, page=pg),
                    )
                    all_commits.extend(_parse_commit(r) for r in raws)
                except GitLabError as exc:
                    logger.warning("Failed to fetch commits from team %s: %s", team, exc)
            all_commits.sort(key=lambda c: c.authored_date, reverse=True)
            return all_commits[:per_page]

        return await self.cache.get_or_fetch(f"audit:day2:commits:{page}", _fetch, ttl=self._ttl)

    async def list_mrs(self, per_page: int = 50, page: int = 1) -> list[MRDetail]:
        async def _fetch() -> list[MRDetail]:
            loop = asyncio.get_event_loop()
            all_mrs: list[MRDetail] = []
            for team in self._teams():
                gl = self.group_client.get_project_client(team)
                try:
                    _gl, _per_page, _page = gl, per_page, page
                    raws = await loop.run_in_executor(
                        None,
                        lambda g=_gl, p=_per_page, pg=_page: g.list_mrs(
                            state="all", per_page=p, page=pg
                        ),
                    )
                    all_mrs.extend(
                        parse_mr_to_detail(r, extract_platform_author=False) for r in raws
                    )
                except GitLabError as exc:
                    logger.warning("Failed to fetch MRs from team %s: %s", team, exc)
            all_mrs.sort(key=lambda m: m.updated_at, reverse=True)
            return all_mrs[:per_page]

        return await self.cache.get_or_fetch(f"audit:day2:mrs:{page}", _fetch, ttl=self._ttl)

    async def get_commit_diff(self, sha: str) -> list[FileDiff]:
        """Get file diffs for a commit — searches all team projects for the SHA."""
        for team in self._teams():
            gl = self.group_client.get_project_client(team)
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
                logger.warning("Error fetching diff from team %s: %s", team, exc)
                continue

        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Commit {sha} not found in any team project")
