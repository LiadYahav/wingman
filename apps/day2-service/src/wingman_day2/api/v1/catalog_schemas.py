"""The bodies of ``/api/day2`` catalog: where the team repos live, and each team."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day2.domain.teams import Team, TeamAccess


class GitLabInfoOut(BaseModel):
    """Where the team repos live."""

    gitlab_url: str
    sigs_group_path: str
    sigs_group_url: str


class TeamOut(BaseModel):
    """A team, its project, and whether Wingman may write there (ADR-0043)."""

    name: str
    project_id: int
    path_with_namespace: str
    web_url: str
    writable: bool
    access_level: int
    access_role: str
    read_only_reason: str | None

    @classmethod
    def of(cls, team: Team, access: TeamAccess) -> TeamOut:
        """From the domain team and its access."""
        return cls(
            name=team.name,
            project_id=team.project.id,
            path_with_namespace=team.project.path_with_namespace,
            web_url=team.project.web_url,
            writable=access.writable,
            access_level=int(access.level),
            access_role=access.level.role,
            read_only_reason=access.reason,
        )
