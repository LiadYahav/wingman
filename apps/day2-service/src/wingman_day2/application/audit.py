"""History: commits and Wingman MRs across the team repos, and one cluster's history."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, FileDiff
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.application.topology import TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind
from wingman_day2.domain.teams import Team
from wingman_day2.ports import SigsRepository


@dataclass(frozen=True, slots=True)
class TeamCommit:
    """A commit in a team repo."""

    team: str
    commit: Commit


@dataclass(frozen=True, slots=True)
class TeamMergeRequest:
    """A Wingman MR in a team repo."""

    team: str
    merge_request: MergeRequest


def _page[T](items: list[T], per_page: int, page: int) -> list[T]:
    return items[(page - 1) * per_page : page * per_page]


class AuditService:
    """Read history across team repos."""

    def __init__(self, gitlab: GitLabPort, topology: TopologyService, sigs: SigsRepository) -> None:
        """Read through ``sigs`` (cached) and ``gitlab`` (commit diffs)."""
        self._gitlab = gitlab
        self._topology = topology
        self._sigs = sigs

    async def commits(self, *, per_page: int, page: int) -> list[TeamCommit]:
        """Commits across team repos, newest first, one page."""
        teams = await self._sigs.teams()
        per_team = await asyncio.gather(
            *(self._sigs.commits(t, path=None, limit=per_page * page) for t in teams)
        )
        found = [
            TeamCommit(team.name, c) for team, cs in zip(teams, per_team, strict=True) for c in cs
        ]
        found.sort(key=lambda c: c.commit.authored_at, reverse=True)
        return _page(found, per_page, page)

    async def merge_requests(self, *, per_page: int, page: int) -> list[TeamMergeRequest]:
        """Wingman MRs in any state across team repos, newest update first, one page."""
        teams = await self._sigs.teams()
        per_team = await asyncio.gather(
            *(self._sigs.merge_requests(t, limit=per_page * page) for t in teams)
        )
        found = [
            TeamMergeRequest(team.name, mr)
            for team, mrs in zip(teams, per_team, strict=True)
            for mr in mrs
        ]
        found.sort(key=lambda m: m.merge_request.updated_at, reverse=True)
        return _page(found, per_page, page)

    async def commit_diff(self, sha: str, *, team: str | None = None) -> tuple[str, list[FileDiff]]:
        """What a commit changed, in the team repo that has it."""
        teams = await self._sigs.teams()
        if team is not None:
            teams = [t for t in teams if t.name == team]

        async def diff(candidate: Team) -> list[FileDiff] | None:
            try:
                return await self._gitlab.commit_diff(candidate.project.id, sha)
            except NotFoundError:
                return None

        for candidate, found in zip(
            teams, await asyncio.gather(*(diff(t) for t in teams)), strict=True
        ):
            if found is not None:
                return candidate.name, found
        raise NotFoundError(f"commit {sha} is in no team repo")

    async def cluster_history(
        self, key: str, *, mce: str | None = None, limit: int = 50
    ) -> list[TeamCommit]:
        """Commits that touched the cluster's folder in any team repo, newest first."""
        topology = await self._topology.load()
        ref = topology.resolve(key, mce=mce).ref
        if ref.kind is not ClusterKind.HUB and not ref.env:
            return []
        folder = layout.cluster_dir(ref)
        teams = [s.team for s in topology.teams]
        per_team = await asyncio.gather(
            *(self._sigs.commits(t, path=folder, limit=limit) for t in teams)
        )
        found = [
            TeamCommit(team.name, c) for team, cs in zip(teams, per_team, strict=True) for c in cs
        ]
        found.sort(key=lambda c: c.commit.authored_at, reverse=True)
        return found[:limit]
