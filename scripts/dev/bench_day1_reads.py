"""Time day1's read pages on a production-sized day1 repo, and count their GitLab calls.

The whole day1 service runs in-process on the in-memory GitLab, seeded from
``dev/gitlab-fixtures`` plus ``--clusters`` more cluster files. Every GitLab
call waits ``--latency`` seconds first (the local GitLab CE answers a REST
read in about 0.035 s; a production GitLab with years of history is slower,
most of all for a file's history), so the times follow the call counts. The
cases are the ones a person meets:

- ``cold``: the first load on a new pod (a deploy, a restart, a scale-up),
  without a warm-up; since ADR-0041 the warm-up pays this at start-up;
- ``warm``: again, within the TTL;
- ``expired``: after the TTL, nothing changed in GitLab;
- ``merged-1``, ``merged-2``: the first and the next load after someone
  merged a change to one cluster, outside Wingman;
- ``burst-1``, ``burst-2``: the same, with 20 people loading at once;
- ``status``: 20 people's pages ask for every cluster's live status at once
  (the MCE hub waits ``--latency`` too; every HostedCluster is healthy).

Nothing here talks to a network.

    uv run python scripts/dev/bench_day1_reads.py --clusters 300 --latency 0.035
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter
from typing import Any

import httpx
from pydantic import SecretStr

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.settings import AuthSettings, Environment, GitBackend, RuntimeSettings
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects, seed_fake
from wingman_day1.domain.status import Condition, HostedClusterObservation
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.main import Adapters, create_app
from wingman_day1.settings import Day1Settings

DAY1 = "gitops-day1/platform-config"
MCE_DIR = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
TEMPLATE = f"{MCE_DIR}/ocp4-prod-herzi-site1.yaml"
TTL = 1.0
PAGES = (
    "/api/day1/clusters",
    "/api/day1/clusters/drift-summary",
    "/api/day1/specs",
    "/api/day1/approvals",
)


class SlowGitLab:
    """A fake (GitLab or an MCE hub), waiting ``latency`` before each call and counting them."""

    def __init__(self, inner: object, latency: float) -> None:
        """Wrap ``inner``; each call waits ``latency`` seconds."""
        self._inner = inner
        self._latency = latency
        self.calls: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        """``inner``'s attribute; a public method waits and is counted."""
        target = getattr(self._inner, name)
        if not callable(target) or name.startswith("_"):
            return target

        async def call(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] += 1
            await asyncio.sleep(self._latency)
            return await target(*args, **kwargs)

        return call


async def seed(clusters: int) -> InMemoryGitLab:
    """The fixture repos plus ``clusters`` copies of one cluster file, in one commit."""
    gitlab = InMemoryGitLab()
    seed_fake(gitlab, load_fixture_projects(default_fixture_root()))
    pid = (await gitlab.get_project(DAY1)).id
    template = (await gitlab.read_file(pid, RepoPath(TEMPLATE), "main")).content
    changes = [
        FileChange.create(RepoPath(f"{MCE_DIR}/ocp4-prod-scale{i:04d}-site1.yaml"), template)
        for i in range(clusters)
    ]
    await gitlab.commit(pid, branch="main", message="scale", changes=changes)
    return gitlab


async def move(gitlab: InMemoryGitLab) -> None:
    """Someone merges a change to one cluster file, outside Wingman."""
    pid = (await gitlab.get_project(DAY1)).id
    path = RepoPath(f"{MCE_DIR}/ocp4-prod-scale0000-site1.yaml")
    current = await gitlab.read_file(pid, path, "main")
    change = FileChange.update(
        path, current.content + f"# {time.time()}\n", last_commit_id=current.last_commit_id
    )
    await gitlab.commit(pid, branch="main", message="outside merge", changes=[change])


async def main() -> None:
    """Run every case and print one line each."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clusters", type=int, default=300)
    parser.add_argument("--latency", type=float, default=0.035)
    args = parser.parse_args()

    inner = await seed(args.clusters)
    gitlab = SlowGitLab(inner, args.latency)
    names = [f"ocp4-prod-scale{i:04d}-site1" for i in range(args.clusters)]
    healthy = (Condition("Available", "True"), Condition("Degraded", "False"))
    hub = SlowGitLab(
        FakeHubApi(
            hosted_clusters={
                "ocp4-prod-mce-site1-a": [
                    HostedClusterObservation(
                        name=f"ocp4-{n.removeprefix('ocp4-')}",
                        namespace=f"hcp-{n.removeprefix('ocp4-')}",
                        phase=None,
                        version="4.16.27",
                        conditions=healthy,
                    )
                    for n in names
                ]
            },
            mces=["ocp4-prod-mce-site1-a"],
        ),
        args.latency,
    )
    app = create_app(
        settings=Day1Settings(
            day1_gitlab_project_id=DAY1,
            specs_gitlab_project_id="wingman/cluster-specs",
            day1_cache_ttl_seconds=TTL,
            cluster_status_enabled=True,
            dev_auth_enabled=True,
            dev_auth_secret=SecretStr("bench-dev-secret-of-at-least-32-characters"),
        ),
        auth=AuthSettings(
            jwt_secret_key=SecretStr("bench-jwt-secret-of-at-least-32-characters"),
            wingman_admin_groups="admins",
        ),
        runtime=RuntimeSettings(environment=Environment.TEST, git_backend=GitBackend.FAKE),
        adapters=Adapters(gitlab=gitlab, day2=FakeDay2Addons({}), hub=hub),  # ty: ignore[invalid-argument-type]
    )
    bench = User(username="bench", role=Role.ADMIN, groups=("admins",))
    token = app.state.session_tokens.issue(bench)
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://day1", headers=headers)
    async with client:

        async def load(label: str, people: int = 1, pages: tuple[str, ...] = PAGES) -> None:
            for page in pages:
                gitlab.calls.clear()
                started = time.perf_counter()
                answers = await asyncio.gather(*(client.get(page) for _ in range(people)))
                took = time.perf_counter() - started
                failed = [a.status_code for a in answers if a.status_code != 200]
                if failed:
                    raise SystemExit(f"{page} answered {failed}")
                calls = dict(sorted(gitlab.calls.items()))
                size = len(answers[0].content) // 1024
                total = sum(calls.values())
                print(f"{label:<8} {page:<34} {took:6.2f}s {size:5d} KiB {total:4d} calls  {calls}")

        settle = args.latency * 4  # what a background refresh needs: a head check and an archive
        await load("cold")
        await load("warm")
        await asyncio.sleep(TTL + 0.1)
        await load("expired")
        for label, people in (("merged", 1), ("burst", 20)):
            await asyncio.sleep(TTL + 0.1)
            await move(inner)
            await load(f"{label}-1", people, PAGES[:1])
            await asyncio.sleep(settle)
            await load(f"{label}-2", people, PAGES[:1])

        body = {"clusters": [{"name": n, "mce": "ocp4-prod-mce-site1-a"} for n in names]}
        hub.calls.clear()
        started = time.perf_counter()
        answers = await asyncio.gather(
            *(client.post("/api/day1/clusters/bulk-status", json=body) for _ in range(20))
        )
        took = time.perf_counter() - started
        if any(a.status_code != 200 for a in answers):
            raise SystemExit("bulk-status failed")
        calls = dict(sorted(hub.calls.items()))
        route = "POST /api/day1/clusters/bulk-status"
        total = sum(calls.values())
        print(f"{'status':<8} {route:<34} {took:6.2f}s x20 {total:5d} hub calls  {calls}")


if __name__ == "__main__":
    asyncio.run(main())
