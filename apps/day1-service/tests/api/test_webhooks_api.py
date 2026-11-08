"""``POST /api/webhooks/gitlab``: fail closed without a secret, clear caches with one."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

from wingman_core.domain.merge_request import NewMergeRequest
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

Auth = Callable[[User], dict[str, str]]
TOKEN = {"X-Gitlab-Token": "test-webhook-secret"}


async def test_without_a_secret_the_webhook_does_not_exist(
    support: Any, gitlab: InMemoryGitLab, hub: Any, identity: Any, clock: Any
) -> None:
    # Legacy: an empty GITLAB_WEBHOOK_SECRET accepted every caller.
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=FakeDay2Addons(),
        clock=clock,
        gitlab_webhook_secret=SecretStr(""),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://day1.test"
    ) as client:
        response = await client.post(
            "/api/webhooks/gitlab",
            json={"project": {"id": 1}},
            headers={"X-Gitlab-Event": "Push Hook"},
        )
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_a_wrong_or_missing_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    for headers in ({}, {"X-Gitlab-Token": "guess"}):
        response = await client.post(
            "/api/webhooks/gitlab",
            json={"project": {"id": 1}},
            headers={**headers, "X-Gitlab-Event": "Push Hook"},
        )
        assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")


async def test_an_event_from_another_project_is_ignored(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/webhooks/gitlab",
        json={"project": {"id": 999}},
        headers={**TOKEN, "X-Gitlab-Event": "Push Hook"},
    )
    assert response.json() == {"status": "ignored"}
    no_project = await client.post(
        "/api/webhooks/gitlab", json={}, headers={**TOKEN, "X-Gitlab-Event": "Push Hook"}
    )
    assert no_project.json() == {"status": "ignored"}


async def test_a_merge_request_event_clears_the_cached_mr_lists(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    viewer = auth(support.VIEWER)
    assert (await client.get("/api/day1/approvals", headers=viewer)).json() == []
    pid = await support.project_id(gitlab, support.DAY1)
    # Someone opens a Wingman-labelled MR without going through Wingman.
    await gitlab.create_branch(pid, "outside", "main")
    await gitlab.create_merge_request(
        pid,
        NewMergeRequest(
            source_branch="outside",
            target_branch="main",
            title="[Wingman/Day1] Modify cluster ocp4-prod-herzi-site1",
            labels=("wingman", "day1", "modify"),
        ),
    )
    assert (await client.get("/api/day1/approvals", headers=viewer)).json() == []  # cached
    hook = await client.post(
        "/api/webhooks/gitlab",
        json={"object_kind": "merge_request", "project": {"id": pid}},
        headers={**TOKEN, "X-Gitlab-Event": "Merge Request Hook"},
    )
    assert hook.json() == {"status": "ok"}
    listed = (await client.get("/api/day1/approvals", headers=viewer)).json()
    assert [m["title"] for m in listed] == ["[Wingman/Day1] Modify cluster ocp4-prod-herzi-site1"]


async def test_a_push_to_the_specs_project_clears_the_cached_specs(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    viewer = auth(support.VIEWER)
    assert len((await client.get("/api/day1/specs", headers=viewer)).json()) == 4
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file="specs/agent-mini.yaml",
        content="metadata: {name: agent-mini, version: '1'}\n",
    )
    assert len((await client.get("/api/day1/specs", headers=viewer)).json()) == 4  # cached
    pid = await support.project_id(gitlab, support.SPECS)
    await client.post(
        "/api/webhooks/gitlab",
        json={"project": {"id": pid}},
        headers={**TOKEN, "X-Gitlab-Event": "Push Hook"},
    )
    assert len((await client.get("/api/day1/specs", headers=viewer)).json()) == 5
