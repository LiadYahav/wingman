"""Per-team opt-in: Wingman writes for a team only when the team let its account write (ADR-0043).

Wingman has one GitLab account. A team that trusts Wingman makes that account
a Developer (or higher) member of its project ``sigs/<team>``; a team that
does not is read-only in Wingman: every day2 write for it is refused before
anything is planned or sent, with the reason, and its reads still work
wherever the account can read. The access is read per team project and kept
like the other reads (ADR-0011, ADR-0041).

A team whose access GitLab does not answer reads as access unknown: read-only,
with the cause, while every other team reads as usual. A failed read is not
kept (the cache keeps answers only), so the next read asks GitLab again.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from wingman_core.domain.errors import GitError
from wingman_day2.domain.errors import TeamReadOnlyError
from wingman_day2.domain.teams import WRITE_LEVEL, Team, TeamAccess, UnknownAccess
from wingman_day2.ports import SigsRepository

logger = logging.getLogger(__name__)


class AccessService:
    """What Wingman's GitLab account may do in each team's project."""

    def __init__(self, sigs: SigsRepository) -> None:
        """Read the access through ``sigs`` (cached)."""
        self._sigs = sigs

    async def of(self, team: Team) -> TeamAccess:
        """``team``'s access; unknown (so read-only) when GitLab does not answer it."""
        project = team.project.path_with_namespace
        try:
            level = await self._sigs.access(team)
        except GitError as exc:
            logger.warning("reading Wingman's access to %s failed: %s", project, _cause(exc))
            return TeamAccess(team.name, project, UnknownAccess(_cause(exc)))
        return TeamAccess(team.name, project, level)

    async def of_all(self, teams: Sequence[Team]) -> dict[str, TeamAccess]:
        """Every team's access, by team name; one team's failed read leaves the others."""
        found = await asyncio.gather(*(self.of(team) for team in teams))
        return {access.team: access for access in found}

    async def require_write(self, team: Team) -> TeamAccess:
        """``team``'s access, or the refusal when Wingman may not write there."""
        access = await self.of(team)
        if not access.writable:
            raise TeamReadOnlyError(
                access.reason or f"{team.name} is read-only in Wingman",
                details={
                    "team": team.name,
                    "project": access.project,
                    "access_level": int(access.level),
                    "access_role": access.level.role,
                    "required_level": int(WRITE_LEVEL),
                },
            )
        return access


def _cause(exc: GitError) -> str:
    return str(exc) or type(exc).__name__
