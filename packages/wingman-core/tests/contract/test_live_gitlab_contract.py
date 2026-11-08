"""The GitLabPort contract, run against a real GitLab.

Skipped unless WINGMAN_TEST_GITLAB_URL and WINGMAN_TEST_GITLAB_TOKEN are set.
The token needs the ``api`` scope and the right to create projects in the
group WINGMAN_TEST_GITLAB_GROUP (default ``wingman-contract``), which is
created if missing. Every test gets a fresh project, deleted afterwards.

Run against local GitLab:  WINGMAN_TEST_GITLAB_URL=http://localhost:8929
WINGMAN_TEST_GITLAB_TOKEN=... uv run pytest -m live_gitlab
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Mapping

import httpx
import pytest
from pydantic import AnyHttpUrl, SecretStr

from wingman_core.domain.git import Project
from wingman_core.infrastructure.gitlab import GitLabHttpAdapter
from wingman_core.infrastructure.gitlab.http import build_client
from wingman_core.settings import GitLabSettings
from wingman_core.testing.gitlab_contract import GitLabContract, NewProject

URL = os.environ.get("WINGMAN_TEST_GITLAB_URL", "")
TOKEN = os.environ.get("WINGMAN_TEST_GITLAB_TOKEN", "")
GROUP = os.environ.get("WINGMAN_TEST_GITLAB_GROUP", "wingman-contract")

pytestmark = [
    pytest.mark.live_gitlab,
    pytest.mark.skipif(
        not (URL and TOKEN), reason="no real GitLab configured (WINGMAN_TEST_GITLAB_URL/_TOKEN)"
    ),
]


async def _group_id(admin: httpx.AsyncClient) -> int:
    response = await admin.get(f"/groups/{GROUP}")
    if response.status_code == 404:
        response = await admin.post(
            "/groups", json={"name": GROUP, "path": GROUP, "visibility": "private"}
        )
    response.raise_for_status()
    return int(response.json()["id"])


class TestLiveGitLabContract(GitLabContract):
    @pytest.fixture
    async def admin(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            base_url=f"{URL.rstrip('/')}/api/v4", headers={"PRIVATE-TOKEN": TOKEN}, timeout=60
        ) as client:
            yield client

    @pytest.fixture
    async def gitlab(self) -> AsyncIterator[GitLabHttpAdapter]:
        settings = GitLabSettings(url=AnyHttpUrl(URL), token=SecretStr(TOKEN))
        adapter = GitLabHttpAdapter(build_client(settings))
        yield adapter
        await adapter.aclose()

    @pytest.fixture
    async def new_project(self, admin: httpx.AsyncClient) -> AsyncIterator[NewProject]:
        namespace_id = await _group_id(admin)
        created: list[int] = []

        async def make(files: Mapping[str, str]) -> Project:
            name = f"contract-{uuid.uuid4().hex[:10]}"
            response = await admin.post(
                "/projects",
                json={
                    "name": name,
                    "path": name,
                    "namespace_id": namespace_id,
                    "default_branch": "main",
                },
            )
            response.raise_for_status()
            raw = response.json()
            created.append(raw["id"])
            actions = [
                {"action": "create", "file_path": path, "content": content}
                for path, content in files.items()
            ]
            commit = await admin.post(
                f"/projects/{raw['id']}/repository/commits",
                json={"branch": "main", "commit_message": "Initial commit", "actions": actions},
            )
            commit.raise_for_status()
            return Project(raw["id"], raw["path_with_namespace"], "main", raw["web_url"])

        yield make
        for project_id in created:
            await admin.delete(f"/projects/{project_id}")
