"""Approval service — MR review and approval for Day1 + Specs repos."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import AuthError, GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import FileDiff, MRDetail, UpdateMRRequest, UserInfo
from wingman_shared.mr_conventions import parse_mr_to_detail

logger = logging.getLogger(__name__)


class ApprovalService:
    """Handles MR listing, approval, and rejection for a single GitLab client."""

    def __init__(
        self,
        gitlab_client: GitLabClient,
        cache: CacheManager,
        cache_key_prefix: str,
        cache_ttl: float = 15.0,
    ) -> None:
        self.gl = gitlab_client
        self.cache = cache
        self._prefix = cache_key_prefix
        self._ttl = cache_ttl

    async def list_open_mrs(self) -> list[MRDetail]:
        async def _fetch() -> list[MRDetail]:
            try:
                raws = self.gl.list_open_mrs()
                return [parse_mr_to_detail(r) for r in raws]
            except GitLabError as exc:
                logger.error("Failed to list MRs: %s", exc)
                return []

        return await self.cache.get_or_fetch(
            f"approvals:{self._prefix}:list", _fetch, ttl=self._ttl
        )

    async def get_mr_detail(self, mr_iid: int) -> dict[str, Any]:
        """Get MR metadata + file diffs."""
        try:
            raw = self.gl.get_mr(mr_iid)
            diffs = self.gl.get_mr_diff(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        mr = parse_mr_to_detail(raw)
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

    async def approve_mr(self, mr_iid: int, approver: UserInfo) -> MRDetail:
        """Approve and merge an MR. Enforces: approver != author."""
        try:
            raw = self.gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc

        mr = parse_mr_to_detail(raw)

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
                self.gl.approve_mr(mr_iid)
            except (AuthError, GitLabError) as approve_exc:
                # Log but continue - some projects don't require explicit approval
                logger.warning(
                    "MR !%d approval failed (may not be required): %s", mr_iid, approve_exc
                )

            # Always try to merge
            self.gl.merge_mr(mr_iid)
        except AuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to merge MR: {exc}") from exc

        self.cache.invalidate(f"approvals:{self._prefix}:list")

        # Re-fetch after merge
        try:
            updated_raw = self.gl.get_mr(mr_iid)
            return parse_mr_to_detail(updated_raw)
        except Exception:
            return mr

    async def update_mr(self, mr_iid: int, req: UpdateMRRequest, updater: UserInfo) -> dict:
        """Push new file content to an existing MR's source branch."""
        try:
            raw = self.gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc

        mr = parse_mr_to_detail(raw)
        if mr.state != "opened":
            raise HTTPException(status_code=409, detail=f"MR !{mr_iid} is already {mr.state}")

        actions = [
            {"action": "update", "file_path": f.path, "content": f.content} for f in req.files
        ]
        commit_message = req.message or f"chore: update MR !{mr_iid} via Wingman"
        try:
            self.gl.commit_to_branch(
                branch=mr.source_branch,
                message=commit_message,
                actions=actions,
                author_name=updater.full_name or updater.username,
                author_email=f"{updater.username}@openshift.local",
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to update MR: {exc}") from exc

        self.cache.invalidate(f"approvals:{self._prefix}:list")
        return await self.get_mr_detail(mr_iid)

    async def reject_mr(self, mr_iid: int, rejector: UserInfo) -> MRDetail:
        """Close an MR without merging."""
        try:
            raw = self.gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc

        mr = parse_mr_to_detail(raw)
        if mr.state != "opened":
            raise HTTPException(
                status_code=409,
                detail=f"MR !{mr_iid} is already {mr.state}",
            )

        try:
            self.gl.close_mr(mr_iid)
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to reject MR: {exc}") from exc

        self.cache.invalidate(f"approvals:{self._prefix}:list")

        try:
            updated_raw = self.gl.get_mr(mr_iid)
            return parse_mr_to_detail(updated_raw)
        except Exception:
            return mr
