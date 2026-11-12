"""Per-team opt-in: Wingman writes for a team only when the team let its account write (ADR-0043).

Wingman has one GitLab account. A team that trusts Wingman makes that account
a Developer (or higher) member of its project ``sigs/<team>``; a team that
does not is read-only in Wingman: every day2 write for it is refused before
anything is planned or sent, with the reason, and its reads still work
wherever the account can read. The access is read per team project and kept
like the other reads (ADR-0011, ADR-0041).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from wingman_day2.domain.errors import TeamReadOnlyError
from wingman_day2.domain.teams import WRITE_LEVEL, Team, TeamAccess
from wingman_day2.ports import SigsRepository


class AccessService:
    """What Wingman's GitLab account may do in each team's project."""

    def __init__(self, sigs: SigsRepository) -> None:
        """Read the access through ``sigs`` (cached)."""
        self._sigs = sigs

    async def of(self, team: Team) -> TeamAccess:
        """``team``'s access."""
        level = await self._sigs.access(team)
        return TeamAccess(team.name, team.project.path_with_namespace, level)

    async def of_all(self, teams: Sequence[Team]) -> dict[str, TeamAccess]:
        """Every team's access, by team name."""
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
