"""With scaling on, NodePool replicas change only through update-nodepool (ADR-0062).

Every write of an existing cluster file keeps each NodePool's replicas as
main has them: a person's YAML (the raw editor, a review edit) is refused,
pointing to Scale; a change Wingman writes (a flavor's sync, a rollout's MR)
leaves them out and lists the NodePools to restore. A new cluster, a new
nodepool and a removed one are left alone. Off, nothing changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.domain.replicas_ownership import REPLICAS_BY_SCALE
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_scale import FakeScaleWorkflow

Auth = Callable[[User], dict[str, str]]

LARK = "ocp4-prod-lark-site1"
BASE = f"/api/day1/clusters/{LARK}"
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
PATH = f"{HOSTED}/{LARK}.yaml"
SMALL = "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"
WEBHOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"}
REFUSED = f"nodepool dell-r660-site1-128c-1024gb-5tb replicas: 3 → 4. {REPLICAS_BY_SCALE}"
SIZED = """\
apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-sized
  description: "Five workers in the first nodepool, locked"
  version: "1.1.0"
spec:
  day1:
    locked_paths:
      - nodepools[0].replicas
    values:
      nodepools:
        - replicas: 5
        - replicas: 2
"""


@pytest.fixture
def scaling(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        scale=FakeScaleWorkflow(clock=clock),
        day1_scale_nodepools=True,
        workflows_api_url="http://workflows-orchestrator-api.test:8080",
        server_scan_url="http://server-scan.test:8000",
    )


@pytest.fixture
async def on(scaling: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=scaling, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


async def modify(
    client: httpx.AsyncClient, headers: dict[str, str], edit: Callable[[str], str]
) -> httpx.Response:
    cluster = (await client.get(BASE, headers=headers)).json()
    return await client.patch(
        BASE,
        json={"updated_yaml": edit(cluster["yaml"]), "last_commit_id": cluster["last_commit_id"]},
        headers=headers,
    )


async def follow_sized(client: httpx.AsyncClient, support: Any, gitlab: InMemoryGitLab) -> None:
    """Lark follows agent-sized at 1.0.0; the flavor is at 1.1.0 and locks five replicas."""
    specs = await support.project_id(gitlab, support.SPECS)
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-sized.yaml", content=SIZED
    )
    day1 = await support.project_id(gitlab, support.DAY1)
    current = await gitlab.read_file(day1, RepoPath(PATH), "main")
    header = '# specName: "agent-sized"\n# specVersion: "1.0.0"\n'
    await support.push(
        gitlab, support.DAY1, branch="main", file=PATH, content=header + current.content
    )
    for pid in (specs, day1):
        await client.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)


# ── A person's YAML ──────────────────────────────────────────────────────────


async def test_off_an_edit_may_change_replicas(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    edited = await modify(
        client, auth(support.ALICE), lambda y: y.replace("replicas: 3", "replicas: 4", 1)
    )
    assert edited.status_code == 200, edited.text


async def test_on_an_edit_that_changes_an_existing_nodepools_replicas_points_to_scale(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    edited = await modify(
        on, auth(support.ALICE), lambda y: y.replace("replicas: 3", "replicas: 4", 1)
    )
    assert (edited.status_code, edited.json()["code"]) == (422, "VALIDATION_ERROR")
    assert edited.json()["details"]["problems"] == [REFUSED]


async def test_on_an_edit_may_add_a_nodepool_with_replicas_or_remove_one(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    added = await modify(
        on,
        alice,
        lambda y: y.replace(
            "vlanId: 1412", "- infraEnvName: hp-gen11-site1-64c\n  replicas: 6\n\nvlanId: 1412"
        ),
    )
    assert added.status_code == 200, added.text
    removed = await modify(
        on, alice, lambda y: y[: y.index("# Storage nodes")] + y[y.index("vlanId: 1412") :]
    )
    assert removed.status_code == 200, removed.text


async def test_a_review_edit_is_held_to_main_and_a_create_is_not(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    opened = await modify(on, alice, lambda y: y.replace('anaf: "56"', 'anaf: "57"'))
    assert opened.status_code == 200, opened.text
    mr = opened.json()
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[PATH]
    edit = await on.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={
            "files": [{"path": PATH, "content": content.replace("replicas: 3", "replicas: 4", 1)}]
        },
        headers=bob,
    )
    assert (edit.status_code, edit.json()["code"]) == (422, "VALIDATION_ERROR")
    assert edit.json()["details"]["problems"] == [REFUSED]

    created = await on.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    assert created.status_code == 201, created.text
    new = created.json()
    new_path = f"{HOSTED}/ocp4-prod-falcon-site1.yaml"
    text = gitlab.snapshot(pid, new["source_branch"])[new_path]
    assert "replicas: 2" in text  # a create sets the first replicas
    review = await on.put(
        f"/api/day1/approvals/{new['iid']}",
        json={"files": [{"path": new_path, "content": text.replace("replicas: 2", "replicas: 7")}]},
        headers=bob,
    )
    assert review.status_code == 200, review.text


# ── A change Wingman writes ──────────────────────────────────────────────────


async def test_off_a_sync_writes_the_flavors_replicas(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await follow_sized(client, support, gitlab)
    preview = (
        await client.post(f"{BASE}/sync/preview", json={}, headers=auth(support.ALICE))
    ).json()
    assert [c["file_key"] for c in preview["changes"]] == ["nodepool[0].replicas"]
    assert preview["held_replicas"] == []


async def test_on_a_sync_leaves_replicas_out_of_its_mr_and_lists_them_to_restore(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await follow_sized(on, support, gitlab)
    alice = auth(support.ALICE)
    response = await on.post(f"{BASE}/sync/preview", json={}, headers=alice)
    assert response.status_code == 200, response.text
    preview = response.json()
    held = [{"index": 0, "name": SMALL, "replicas": 3, "flavor_replicas": 5}]
    assert (preview["changes"], preview["held_replicas"]) == ([], held)
    assert (preview["problems"], preview["can_sync"]) == ([], True)  # the header still moves
    assert "replicas" not in preview["diff"]
    synced = await on.post(
        f"{BASE}/sync",
        json={"last_commit_id": preview["last_commit_id"], "spec_version": "1.1.0"},
        headers=alice,
    )
    assert synced.status_code == 201, synced.text
    mr = synced.json()
    assert mr["held_replicas"] == held
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[PATH]
    assert "replicas: 3" in content and "replicas: 5" not in content
    assert '# specVersion: "1.1.0"' in content
    assert "Not in this MR: NodePool replicas" in mr["description"]
    assert f"`{SMALL}` replicas 3 → 5" in mr["description"]


async def test_on_a_rollout_mr_leaves_replicas_out_and_its_item_lists_them(
    on: httpx.AsyncClient, scaling: FastAPI, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await follow_sized(on, support, gitlab)
    started = await on.post("/api/day1/specs/agent-sized/rollout", headers=auth(support.ALICE))
    assert started.status_code == 202, started.text
    (item,) = [c for c in started.json()["clusters"] if c["name"] == LARK]
    assert item["state"] == "pending"
    assert item["held_replicas"] == [
        {"index": 0, "name": SMALL, "replicas": 3, "flavor_replicas": 5}
    ]
    context: Day1Context = scaling.state.day1
    await context.rollouts.wait()
    pid = await support.project_id(gitlab, support.DAY1)
    opened = await gitlab.list_merge_requests(pid, labels=("rollout",))
    (mr,) = [m for m in opened if m.source_branch.endswith(LARK)]
    content = gitlab.snapshot(pid, mr.source_branch)[PATH]
    assert "replicas: 3" in content and "replicas: 5" not in content
    assert "Not in this MR: NodePool replicas" in mr.description
