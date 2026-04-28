"""Approval service for Day2 — multi-project: each team is a separate GitLab project."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import AuthError, GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient, GitLabGroupClient
from wingman_shared.models import FileDiff, MRDetail, UpdateMRRequest, UserInfo
from wingman_shared.mr_conventions import parse_mr_to_detail

logger = logging.getLogger(__name__)


class ApprovalService:
    """Multi-project approval service for day2.

    Aggregates MRs across all team projects inside the sigs subgroup.
    MR lookup by IID searches team projects in order and caches the result.
    """

    def __init__(
        self,
        group_client: GitLabGroupClient,
        cache: CacheManager,
        cache_key_prefix: str,
        cache_ttl: float = 15.0,
    ) -> None:
        self.group_client = group_client
        self.cache = cache
        self._prefix = cache_key_prefix
        self._ttl = cache_ttl
        # In-process cache: mr_iid -> team (avoids repeated project searches)
        self._mr_team: dict[int, str] = {}

    def _teams(self) -> list[str]:
        try:
            return self.group_client.list_project_paths()
        except GitLabError as exc:
            logger.error("Failed to list team projects: %s", exc)
            return []

    def _find_client_for_mr(self, mr_iid: int) -> GitLabClient:
        """Find which team project contains the given MR IID."""
        if mr_iid in self._mr_team:
            return self.group_client.get_project_client(self._mr_team[mr_iid])

        for team in self._teams():
            gl = self.group_client.get_project_client(team)
            try:
                gl.get_mr(mr_iid)
                self._mr_team[mr_iid] = team
                return gl
            except (NotFoundError, GitLabError):
                continue

        raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found in any team project")

    async def list_open_mrs(self) -> list[MRDetail]:
        async def _fetch() -> list[MRDetail]:
            all_mrs: list[MRDetail] = []
            for team in self._teams():
                gl = self.group_client.get_project_client(team)
                try:
                    for r in gl.list_open_mrs():
                        self._mr_team[r["iid"]] = team
                        all_mrs.append(parse_mr_to_detail(r))
                except GitLabError as exc:
                    logger.error("Failed to list MRs from team %s: %s", team, exc)
            return all_mrs

        return await self.cache.get_or_fetch(
            f"approvals:{self._prefix}:list", _fetch, ttl=self._ttl
        )

    async def get_mr_detail(self, mr_iid: int) -> dict[str, Any]:
        gl = self._find_client_for_mr(mr_iid)
        try:
            raw = gl.get_mr(mr_iid)
            diffs = gl.get_mr_diff(mr_iid)
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
        return {"mr": mr.model_dump(), "diffs": [d.model_dump() for d in file_diffs]}

    async def approve_mr(self, mr_iid: int, approver: UserInfo) -> MRDetail:
        gl = self._find_client_for_mr(mr_iid)
        try:
            raw = gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc

        mr = parse_mr_to_detail(raw)
        if mr.author.username == approver.username:
            raise HTTPException(status_code=403, detail="You cannot approve your own merge request")
        if mr.state != "opened":
            raise HTTPException(status_code=409, detail=f"MR !{mr_iid} is already {mr.state}")

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

        self.cache.invalidate(f"approvals:{self._prefix}:list")
        try:
            return parse_mr_to_detail(gl.get_mr(mr_iid))
        except Exception:
            return mr

    async def update_mr(self, mr_iid: int, req: UpdateMRRequest, updater: UserInfo) -> dict:
        """Push new file content to an existing MR's source branch."""
        gl = self._find_client_for_mr(mr_iid)
        try:
            raw = gl.get_mr(mr_iid)
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
            gl.commit_to_branch(
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
        gl = self._find_client_for_mr(mr_iid)
        try:
            raw = gl.get_mr(mr_iid)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"MR !{mr_iid} not found") from exc

        mr = parse_mr_to_detail(raw)
        if mr.state != "opened":
            raise HTTPException(status_code=409, detail=f"MR !{mr_iid} is already {mr.state}")

        try:
            gl.close_mr(mr_iid)
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to reject MR: {exc}") from exc

        self.cache.invalidate(f"approvals:{self._prefix}:list")
        try:
            return parse_mr_to_detail(gl.get_mr(mr_iid))
        except Exception:
            return mr
