"""A new day1 replica reads its first page's GitLab data as it starts (ADR-0041)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab


async def test_the_cluster_list_is_warm_when_the_first_person_asks(
    app: FastAPI,
    gitlab: InMemoryGitLab,
    client: httpx.AsyncClient,
    auth: Callable[[User], dict[str, str]],
    support: Any,
) -> None:
    calls: list[str] = []
    list_commits = gitlab.list_commits

    async def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("list_commits")
        return await list_commits(*args, **kwargs)

    gitlab.list_commits = counting  # ty: ignore[invalid-assignment]
    async with app.router.lifespan_context(app):
        warm = next(t for t in asyncio.all_tasks() if t.get_name() == "day1-warm-up")
        await warm
        warmed = len(calls)
        assert warmed > 0, "the warm-up looked up each cluster's last change"
        answer = await client.get("/api/day1/clusters", headers=auth(support.VIEWER))
        assert answer.status_code == 200 and answer.json()
        assert len(calls) == warmed, "the first person's list made no history lookup"
