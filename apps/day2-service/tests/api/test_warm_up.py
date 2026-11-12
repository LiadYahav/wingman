"""A new day2 replica reads every team repo and the day1 index as it starts (ADR-0041)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab


async def test_the_warm_up_reads_each_team_repo_and_the_day1_repo_once(
    app: FastAPI, gitlab: InMemoryGitLab
) -> None:
    archives: list[int] = []
    read_archive = gitlab.read_archive

    async def counting(project_id: int, sha: str, **kwargs: Any) -> Any:
        archives.append(project_id)
        return await read_archive(project_id, sha, **kwargs)

    gitlab.read_archive = counting  # ty: ignore[invalid-assignment]
    teams = await gitlab.list_group_projects("sigs")
    async with app.router.lifespan_context(app):
        warm = next(t for t in asyncio.all_tasks() if t.get_name() == "day2-warm-up")
        await warm
    assert len(archives) == len(set(archives)) == len(teams) + 1
