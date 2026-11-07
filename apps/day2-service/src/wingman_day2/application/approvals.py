"""Day2 approvals: core ``Approvals`` over the team projects, every MR addressed as (team, iid).

The team name maps to exactly one project, so ``redbull !5`` and ``lynx !5``
can never be confused (the legacy service looked MRs up by number alone and
acted on the first team that had one, ADR-0007).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from wingman_core.application.approvals import Approvals, PendingChange, describe
from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.domain.git import FileChange, FileDiff, RepoPath
from wingman_core.domain.merge_request import MergeRequest, MergeRequestRef, MRState
from wingman_core.domain.users import User
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.domain.errors import ChangeRefusedError, UnknownTeamError
from wingman_day2.domain.teams import Team
from wingman_day2.ports import SigsRepository


@dataclass(frozen=True, slots=True)
class TeamChange:
    """A Wingman MR and the team whose repo it is in."""

    team: Team
    change: PendingChange


@dataclass(frozen=True, slots=True)
class FileEdit:
    """New content for a file an MR changes, guarded by the commit the editor read it at."""

    path: str
    content: str
    last_commit_id: str | None = None


class ApprovalService:
    """List, inspect, edit, approve and reject day2 MRs."""

    def __init__(self, gitlab: GitLabPort, sigs: SigsRepository) -> None:
        """Act through ``gitlab`` (Wingman's account); find teams through ``sigs``."""
        self._gitlab = gitlab
        self._sigs = sigs
        self._approvals = Approvals(gitlab)

    async def _team(self, name: str) -> tuple[Team, frozenset[int]]:
        teams = await self._sigs.teams()
        managed = frozenset(t.project.id for t in teams)
        for team in teams:
            if team.name == name:
                return team, managed
        raise UnknownTeamError(f"no team {name!r} in the sigs group", details={"team": name})

    async def pending(self) -> list[TeamChange]:
        """Open Wingman MRs across every team, newest first."""
        teams = await self._sigs.teams()
        per_team = await asyncio.gather(*(self._sigs.open_merge_requests(t) for t in teams))
        changes = [
            TeamChange(team, describe(mr))
            for team, mrs in zip(teams, per_team, strict=True)
            for mr in mrs
        ]
        return sorted(
            changes,
            key=lambda c: (c.change.merge_request.created_at, c.change.merge_request.ref),
            reverse=True,
        )

    async def detail(self, team: str, iid: int) -> tuple[TeamChange, list[FileDiff]]:
        """One MR and what it changes."""
        owner, managed = await self._team(team)
        ref = MergeRequestRef(owner.project.id, iid)
        change = await self._approvals.get(ref, managed=managed)
        return TeamChange(owner, change), await self._gitlab.merge_request_diff(ref)

    async def edit(
        self, team: str, iid: int, files: Sequence[FileEdit], message: str, user: User
    ) -> tuple[TeamChange, list[FileDiff]]:
        """Commit new content for files the MR already changes, onto its branch."""
        current, diffs = await self.detail(team, iid)
        merge_request = current.change.merge_request
        if merge_request.state is not MRState.OPENED:
            raise ChangeRefusedError(
                f"!{iid} is {merge_request.state}; only an open MR can be edited",
                details={"rule": "mr-not-open"},
            )
        editable = {str(d.new_path) for d in diffs if not d.deleted_file}
        changes = []
        for edit in files:
            try:
                path = RepoPath(edit.path)
            except InvalidRepoPathError as exc:
                raise ChangeRefusedError(
                    f"invalid path {edit.path!r}", details={"rule": "path"}
                ) from exc
            if str(path) not in editable:
                raise ChangeRefusedError(
                    f"{path} is not a file this MR changes; only those can be edited here",
                    details={"rule": "path-not-in-mr", "editable": sorted(editable)},
                )
            guard = (
                edit.last_commit_id
                or (
                    await self._gitlab.read_file(
                        current.team.project.id, path, merge_request.source_branch
                    )
                ).last_commit_id
            )
            changes.append(FileChange.update(path, edit.content, last_commit_id=guard))
        if not changes:
            raise ChangeRefusedError("no files to edit", details={"rule": "no-change"})
        try:
            await self._gitlab.commit(
                current.team.project.id,
                branch=merge_request.source_branch,
                message=f"{message or f'Edit !{iid}'}\n\nEdited by {user.username} via Wingman",
                changes=changes,
            )
        finally:
            self._sigs.invalidate(current.team)
        return await self.detail(team, iid)

    async def approve(self, team: str, iid: int, *, sha: str, approver: User) -> MergeRequest:
        """Approve and merge the commit the approver reviewed, unless they requested the change."""
        owner, managed = await self._team(team)
        try:
            return await self._approvals.approve(
                MergeRequestRef(owner.project.id, iid),
                approver=approver,
                reviewed_sha=sha,
                managed=managed,
            )
        finally:
            self._sigs.invalidate(owner)

    async def reject(self, team: str, iid: int) -> MergeRequest:
        """Close without merging."""
        owner, managed = await self._team(team)
        try:
            return await self._approvals.reject(
                MergeRequestRef(owner.project.id, iid), managed=managed
            )
        finally:
            self._sigs.invalidate(owner)
