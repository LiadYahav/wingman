"""Seed a GitLab with the fixture repos in ``dev/gitlab-fixtures``.

Creates each group and project as production lays them out
(``gitops-day1/platform-config``, ``sigs/<team>``, ``helm-charts/<chart>``,
``wingman/cluster-specs``), commits the fixture files, and creates the
release branches named in ``branches.yaml``. Projects that already exist are
left alone unless ``--reset`` deletes and recreates them.

    uv run python scripts/dev/seed_gitlab.py [--url URL] [--token TOKEN] [--reset]

Defaults come from GITLAB_URL / GITLAB_TOKEN. Meant for the local GitLab
(scripts/dev/gitlab-up.sh); it refuses any other host unless --any-host.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from urllib.parse import quote, urlparse

import httpx

from wingman_core.testing.fixtures import FixtureProject, default_fixture_root, load_fixture_projects

LOCAL_HOSTS = {"localhost", "127.0.0.1", "gitlab.local"}


async def _group_id(client: httpx.AsyncClient, path: str) -> int:
    response = await client.get(f"/groups/{quote(path, safe='')}")
    if response.status_code == 404:
        response = await client.post("/groups", json={"name": path, "path": path, "visibility": "private"})
    response.raise_for_status()
    return int(response.json()["id"])


async def _delete_and_wait(client: httpx.AsyncClient, path: str) -> None:
    await client.delete(f"/projects/{quote(path, safe='')}", params={"permanently_remove": "true", "full_path": path})
    for _ in range(60):
        if (await client.get(f"/projects/{quote(path, safe='')}")).status_code == 404:
            return
        await asyncio.sleep(1)
    raise RuntimeError(f"{path} was not deleted within a minute")


async def _seed_project(client: httpx.AsyncClient, fixture: FixtureProject, *, reset: bool) -> str:
    group, name = fixture.path_with_namespace.split("/", 1)
    existing = await client.get(f"/projects/{quote(fixture.path_with_namespace, safe='')}")
    if existing.status_code == 200:
        if not reset:
            return "exists"
        await _delete_and_wait(client, fixture.path_with_namespace)
    namespace_id = await _group_id(client, group)
    created = await client.post(
        "/projects",
        json={"name": name, "path": name, "namespace_id": namespace_id, "default_branch": "main"},
    )
    created.raise_for_status()
    project_id = created.json()["id"]
    actions = [{"action": "create", "file_path": p, "content": c} for p, c in sorted(fixture.files.items())]
    commit = await client.post(
        f"/projects/{project_id}/repository/commits",
        json={"branch": "main", "commit_message": "Seed from dev/gitlab-fixtures", "actions": actions},
    )
    commit.raise_for_status()
    for branch in fixture.branches:
        files = fixture.branch_files(branch)
        changed = [
            {"action": "update", "file_path": p, "content": c}
            for p, c in sorted(files.items())
            if fixture.files.get(p) != c
        ]
        body: dict[str, object] = {"branch": branch, "start_branch": "main", "commit_message": f"Release {branch}"}
        if changed:
            response = await client.post(f"/projects/{project_id}/repository/commits", json={**body, "actions": changed})
        else:
            response = await client.post(
                f"/projects/{project_id}/repository/branches", json={"branch": branch, "ref": "main"}
            )
        response.raise_for_status()
    return "created"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("GITLAB_URL", "http://localhost:8929"))
    parser.add_argument("--token", default=os.environ.get("GITLAB_TOKEN", ""))
    parser.add_argument("--reset", action="store_true", help="delete and recreate projects that exist")
    parser.add_argument("--any-host", action="store_true", help="allow a non-local GitLab")
    args = parser.parse_args()
    if not args.token:
        parser.error("no token: pass --token or set GITLAB_TOKEN")
    if urlparse(args.url).hostname not in LOCAL_HOSTS and not args.any_host:
        parser.error(f"{args.url} is not a local GitLab; pass --any-host if you mean it")

    projects = load_fixture_projects(default_fixture_root(), substitutions={"GITLAB_URL": args.url.rstrip("/")})
    started = time.monotonic()
    async with httpx.AsyncClient(
        base_url=f"{args.url.rstrip('/')}/api/v4", headers={"PRIVATE-TOKEN": args.token}, timeout=120
    ) as client:
        for fixture in projects:
            outcome = await _seed_project(client, fixture, reset=args.reset)
            print(f"{outcome:>8}  {fixture.path_with_namespace}")
    print(f"seeded {len(projects)} projects in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
