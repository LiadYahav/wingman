"""The GitLabPort contract, run against a real GitLab.

Skipped unless WINGMAN_TEST_GITLAB_URL and WINGMAN_TEST_GITLAB_TOKEN are set.
The token needs the ``api`` scope and the right to create projects in the
group WINGMAN_TEST_GITLAB_GROUP (default ``wingman-contract``), which is
created if missing. Every test gets a fresh project, deleted afterwards. The
access tests also create throwaway users (with an impersonation token each)
and hard-delete them afterwards, so the token must be an administrator's,
with ``admin_mode`` where Admin Mode is on (scripts/dev/gitlab-up.sh's and
CI's are).

Run against local GitLab:  WINGMAN_TEST_GITLAB_URL=http://localhost:8929
WINGMAN_TEST_GITLAB_TOKEN=... uv run pytest -m live_gitlab
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import AnyHttpUrl, SecretStr

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import AccessLevel, Project
from wingman_core.infrastructure.gitlab import GitLabHttpAdapter
from wingman_core.infrastructure.gitlab.http import build_client
from wingman_core.ports.gitlab import GitLabPort
from wingman_core.settings import GitLabSettings
from wingman_core.testing.gitlab_contract import (
    GitLabContract,
    NewMember,
    NewProject,
    RenameProject,
)

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


async def _until_visible(member: GitLabHttpAdapter, project: Project) -> None:
    """Wait until a new member can see the project.

    GitLab records a membership at once (``permissions`` reads it), but the
    authorization that lets the account see a private project is refreshed by
    a background job, seconds later; until then the project answers 404.
    """
    for _ in range(60):
        try:
            await member.get_project(project.id)
        except NotFoundError:
            await asyncio.sleep(1)
        else:
            return
    raise AssertionError(f"the new member could not see {project.path_with_namespace} in 60s")


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

    @pytest.fixture
    def rename_project(self, admin: httpx.AsyncClient) -> RenameProject:
        async def rename(project: Project, name: str) -> None:
            response = await admin.put(f"/projects/{project.id}", json={"name": name, "path": name})
            response.raise_for_status()

        return rename

    @pytest.fixture
    async def new_member(self, admin: httpx.AsyncClient) -> AsyncIterator[NewMember]:
        users: list[int] = []
        adapters: list[GitLabHttpAdapter] = []

        async def make(
            project: Project,
            *,
            project_level: AccessLevel | None = None,
            group_level: AccessLevel | None = None,
        ) -> GitLabPort:
            name = f"contract-member-{uuid.uuid4().hex[:10]}"
            created = await admin.post(
                "/users",
                json={
                    "email": f"{name}@example.com",
                    "username": name,
                    "name": name,
                    "password": f"{secrets.token_urlsafe(24)}aA1!",
                    "skip_confirmation": True,
                },
            )
            created.raise_for_status()
            user_id = int(created.json()["id"])
            users.append(user_id)
            # Group first: GitLab refuses a project role below one the user inherits.
            if group_level is not None:
                group = await admin.post(
                    f"/groups/{await _group_id(admin)}/members",
                    json={"user_id": user_id, "access_level": int(group_level)},
                )
                group.raise_for_status()
            if project_level is not None:
                member = await admin.post(
                    f"/projects/{project.id}/members",
                    json={"user_id": user_id, "access_level": int(project_level)},
                )
                member.raise_for_status()
            token = await admin.post(
                f"/users/{user_id}/impersonation_tokens",
                json={
                    "name": "wingman-contract",
                    "scopes": ["api"],
                    "expires_at": (datetime.now(UTC) + timedelta(days=2)).date().isoformat(),
                },
            )
            token.raise_for_status()
            settings = GitLabSettings(url=AnyHttpUrl(URL), token=SecretStr(token.json()["token"]))
            adapter = GitLabHttpAdapter(build_client(settings))
            adapters.append(adapter)
            if project_level is not None or group_level is not None:
                await _until_visible(adapter, project)
            return adapter

        yield make
        for adapter in adapters:
            await adapter.aclose()
        for user_id in users:
            await admin.delete(f"/users/{user_id}", params={"hard_delete": "true"})
