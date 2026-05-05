"""Approval service — MR review and approval for Day1 + Specs repos."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import HTTPException
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import AuthError, GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import FileDiff, MRDetail, UpdateMRRequest, UserInfo
from wingman_shared.mr_conventions import parse_mr_to_detail

logger = logging.getLogger(__name__)

RepoType = Literal["day1", "specs"]


class ApprovalService:
    """Handles MR listing, approval, and rejection for Day1 and Specs repos."""

    def __init__(
        self,
        gitlab_day1: GitLabClient,
        gitlab_specs: GitLabClient,
        cache: CacheManager,
        cache_ttl: float = 15.0,
    ) -> None:
        self.gl_day1 = gitlab_day1
        self.gl_specs = gitlab_specs
        self.cache = cache
        self._ttl = cache_ttl

    def _get_client(self, repo: RepoType) -> GitLabClient:
        """Get the appropriate GitLab client for a repo type."""
        return self.gl_day1 if repo == "day1" else self.gl_specs

    async def _list_mrs_for_repo(self, repo: RepoType) -> list[MRDetail]:
        """List open MRs for a single repo."""
        gl = self._get_client(repo)
        try:
            raws = gl.list_open_mrs()
            mrs = [parse_mr_to_detail(r) for r in raws]
            # Set the repo field on each MR
            for mr in mrs:
                mr.repo = repo
            return mrs
        except GitLabError as exc:
            logger.error("Failed to list MRs from %s: %s", repo, exc)
            return []

    async def list_open_mrs(self) -> list[MRDetail]:
        """Aggregate open MRs from both Day1 and Specs repos."""

        async def _fetch() -> list[MRDetail]:
            # Fetch from both repos in parallel
            day1_mrs, specs_mrs = await asyncio.gather(
                self._list_mrs_for_repo("day1"),
                self._list_mrs_for_repo("specs"),
            )
            # Combine and sort by updated_at descending
            all_mrs = day1_mrs + specs_mrs
            all_mrs.sort(key=lambda m: m.updated_at, reverse=True)
            return all_mrs

        return await self.cache.get_or_fetch(
            "approvals:combined:list", _fetch, ttl=self._ttl
        )

    async def get_mr_detail(self, mr_iid: int, repo: RepoType) -> dict[str, Any]:
        """Get MR metadata + file diffs."""
        gl = self._get_client(repo)
        try:
            raw = gl.get_mr(mr_iid)
            diffs = gl.get_mr_diff(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found in {repo}") from exc
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        mr = parse_mr_to_detail(raw)
        mr.repo = repo
        file_diffs = [
            FileDiff(
                old_path=d.get("old_path", ""),
                new_path=d.get("new_path", ""),
                diff=d.get("diff", ""),
                new_file=d.get("new_file", False),
                renamed_file=d.get("renamed_file", False),
                deleted_file=d.get("deleted_file", False),
            )
            for d in diffs
        ]

        return {
            "mr": mr.model_dump(),
            "diffs": [d.model_dump() for d in file_diffs],
        }

    async def approve_mr(self, mr_iid: int, repo: RepoType, approver: UserInfo) -> MRDetail:
        """Approve and merge an MR. Enforces: approver != author."""
        gl = self._get_client(repo)
        try:
            raw = gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found in {repo}") from exc

        mr = parse_mr_to_detail(raw)
        mr.repo = repo

        # CRITICAL: same-user approval is forbidden
        if mr.author.username == approver.username:
            raise HTTPException(
                status_code=403,
                detail="You cannot approve your own merge request",
            )

        if mr.state != "opened":
            raise HTTPException(
                status_code=409,
                detail=f"MR !{mr_iid} is already {mr.state}",
            )

        try:
            # Try to approve first (may fail if approval not required or already approved)
            try:
                gl.approve_mr(mr_iid)
            except (AuthError, GitLabError) as approve_exc:
                # Log but continue - some projects don't require explicit approval
                logger.warning(
                    "MR !%d approval failed (may not be required): %s", mr_iid, approve_exc
                )

            # Always try to merge
            gl.merge_mr(mr_iid)
        except AuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to merge MR: {exc}") from exc

        self.cache.invalidate("approvals:combined:list")

        # Re-fetch after merge
        try:
            updated_raw = gl.get_mr(mr_iid)
            result = parse_mr_to_detail(updated_raw)
            result.repo = repo
            return result
        except Exception:
            return mr

    async def update_mr(
        self, mr_iid: int, repo: RepoType, req: UpdateMRRequest, updater: UserInfo
    ) -> dict:
        """Push new file content to an existing MR's source branch."""
        gl = self._get_client(repo)
        try:
            raw = gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found in {repo}") from exc

        mr = parse_mr_to_detail(raw)
        if mr.state != "opened":
            raise HTTPException(status_code=409, detail=f"MR !{mr_iid} is already {mr.state}")

        actions = [
            {"action": "update", "file_path": f.path, "content": f.content} for f in req.files
        ]
        commit_message = req.message or f"chore: update MR !{mr_iid} via Wingman"
        try:
            gl.commit_to_branch(
                branch=mr.source_branch,
                message=commit_message,
                actions=actions,
                author_name=updater.full_name or updater.username,
                author_email=f"{updater.username}@openshift.local",
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to update MR: {exc}") from exc

        self.cache.invalidate("approvals:combined:list")
        return await self.get_mr_detail(mr_iid, repo)

    async def reject_mr(self, mr_iid: int, repo: RepoType, rejector: UserInfo) -> MRDetail:
        """Close an MR without merging."""
        gl = self._get_client(repo)
        try:
            raw = gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found in {repo}") from exc

        mr = parse_mr_to_detail(raw)
        mr.repo = repo
        if mr.state != "opened":
            raise HTTPException(
                status_code=409,
                detail=f"MR !{mr_iid} is already {mr.state}",
            )

        try:
            gl.close_mr(mr_iid)
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to reject MR: {exc}") from exc

        self.cache.invalidate("approvals:combined:list")

        try:
            updated_raw = gl.get_mr(mr_iid)
            result = parse_mr_to_detail(updated_raw)
            result.repo = repo
            return result
        except Exception:
            return mr
