"""A flavor's rollout over HTTP (ADR-0044): its triggers and the JSON the web reads.

The contract is ``docs/notes/2026-11-12-flavor-rollout-api.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.git import RepoPath
from wingman_core.domain.merge_request import MRState
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context

Auth = Callable[[User], dict[str, str]]
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
LARK, HERON, HERZI = "ocp4-prod-lark-site1", "ocp4-prod-heron-site1", "ocp4-prod-herzi-site1"
FLAVOR = "agent-baseline"
WEBHOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"}


async def link(
    client: httpx.AsyncClient, support: Any, gitlab: InMemoryGitLab, name: str, version: str
) -> None:
    """A fixture cluster's header names the flavor at ``version`` on main (a merged import)."""
    pid = await support.project_id(gitlab, support.DAY1)
    path = f"{HOSTED}/{name}.yaml"
    current = await gitlab.read_file(pid, RepoPath(path), "main")
    content = f'# specName: "{FLAVOR}"\n# specVersion: "{version}"\n{current.content}'
    await support.push(gitlab, support.DAY1, branch="main", file=path, content=content)
    await client.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)


async def flavor_mr(client: httpx.AsyncClient, alice: dict[str, str], version: str) -> int:
    """Alice's MR that gives the flavor ``version``; its iid in the specs project."""
    spec = (await client.get(f"/api/day1/specs/{FLAVOR}", headers=alice)).json()
    for key in ("load_error", "load_problems", "warnings", "enforced_locks", "last_commit_id"):
        spec.pop(key, None)
    spec["metadata"]["version"] = version
    response = await client.put(f"/api/day1/specs/{FLAVOR}", json=spec, headers=alice)
    assert response.status_code == 200, response.text
    return response.json()["iid"]


async def open_rollouts(gitlab: InMemoryGitLab, support: Any) -> dict[str, Any]:
    pid = await support.project_id(gitlab, support.DAY1)
    found = await gitlab.list_merge_requests(pid, state=MRState.OPENED, labels=("rollout",))
    return {mr.source_branch.rsplit("/", 1)[1]: mr for mr in found}


async def test_merging_a_flavor_version_opens_one_mr_per_cluster(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    context: Day1Context,
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    for name in (LARK, HERON, HERZI):
        await link(client, support, gitlab, name, "1.0.0")
    iid = await flavor_mr(client, alice, "1.1.0")

    # Before the merge: what it will open, on the review page
    preview = await client.get(f"/api/day1/approvals/{iid}/rollout?repo=specs", headers=bob)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert {
        k: body[k] for k in ("applies", "reason", "spec_name", "version", "current_version")
    } == {
        "applies": True,
        "reason": None,
        "spec_name": FLAVOR,
        "version": "1.1.0",
        "current_version": "1.0.0",
    }
    assert (body["following"], body["opens"], body["already_on_version"]) == (3, 2, 0)
    assert [(d["name"], d["reasons"][0].split(":")[0]) for d in body["needs_decision"]] == [
        (HERON, "nodepool[0].configs")
    ]
    assert body["rolls_nodes"] == [
        {
            "name": LARK,
            "site": "site1",
            "mce": "ocp4-prod-mce-site1-a",
            "nodepools": [
                {
                    "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
                    "replicas": 3,
                    "replaces_nodes": False,
                    "max_unavailable": None,
                },
                {
                    "name": "prod-lark-site1-dell-r760-site1-64c-512gb-20tb",
                    "replicas": 2,
                    "replaces_nodes": False,
                    "max_unavailable": None,
                },
            ],
        }
    ]
    assert [r["name"] for r in body["removes_configs"]] == [LARK]
    assert body["adds_addons"] == []

    # The merge: Wingman's approve starts the rollout
    detail = (await client.get(f"/api/day1/approvals/{iid}?repo=specs", headers=bob)).json()
    merged = await client.post(
        f"/api/day1/approvals/{iid}/approve?repo=specs",
        json={"sha": detail["mr"]["sha"]},
        headers=bob,
    )
    assert merged.status_code == 200, merged.text
    await context.rollouts.wait()
    assert sorted(await open_rollouts(gitlab, support)) == sorted([LARK, HERZI])

    status = await client.get(f"/api/day1/specs/{FLAVOR}/rollout", headers=auth(support.VIEWER))
    assert status.status_code == 200, status.text
    rollout = status.json()
    assert (rollout["spec_name"], rollout["version"], rollout["running"]) == (
        FLAVOR,
        "1.1.0",
        False,
    )
    assert rollout["counts"] == {
        "on_version": 0,
        "merge_request_open": 2,
        "pending": 0,
        "needs_decision": 1,
        "declined": 0,
        "failed": 0,
        "unknown": 0,
    }
    assert rollout["last_run"]["trigger"] == "merge"
    assert (rollout["last_run"]["opened"], rollout["last_run"]["failed"]) == (2, 0)
    # Clusters by state: what is open, then what needs a person
    assert [(c["name"], c["state"]) for c in rollout["clusters"]] == [
        (HERZI, "merge_request_open"),
        (LARK, "merge_request_open"),
        (HERON, "needs_decision"),
    ]
    herzi = rollout["clusters"][0]
    assert herzi["from_version"] == "1.0.0"
    assert herzi["path"] == f"{HOSTED}/{HERZI}.yaml"
    assert herzi["merge_request"]["repo"] == "day1"
    assert herzi["merge_request"]["title"] == (
        f"[Wingman/Day1] Sync cluster {HERZI} to spec agent-baseline v1.1.0"
    )

    # Every drift answer carries the update and its MR
    drift = (await client.get(f"/api/day1/clusters/{HERZI}/drift", headers=bob)).json()
    assert drift["update"] == {"version": "1.1.0", "merge_request": herzi["merge_request"]}
    summary = (await client.get("/api/day1/clusters/drift-summary", headers=bob)).json()
    row = next(r for r in summary if r["name"] == HERZI)
    assert (row["spec_name"], row["spec_version"], row["update"]) == (
        FLAVOR,
        "1.0.0",
        drift["update"],
    )
    rows = (await client.get(f"/api/day1/specs/{FLAVOR}/clusters", headers=bob)).json()
    assert next(r for r in rows if r["name"] == HERZI)["update"] == drift["update"]
    rows = (await client.get(f"/api/day1/specs/{FLAVOR}/drift", headers=bob)).json()
    assert next(r for r in rows if r["cluster"] == HERZI)["update"] == drift["update"]

    # A sync by hand to v1.1.0 is refused: an MR already takes HERZI there
    plan = (
        await client.post(f"/api/day1/clusters/{HERZI}/sync/preview", json={}, headers=bob)
    ).json()
    refused = await client.post(
        f"/api/day1/clusters/{HERZI}/sync",
        json={
            "last_commit_id": plan["last_commit_id"],
            "spec_version": "1.1.0",
            "confirm_removals": [],
        },
        headers=bob,
    )
    assert (refused.status_code, refused.json()["code"]) == (409, "ALREADY_EXISTS")
    assert "an open merge request already syncs" in refused.json()["detail"]


async def test_the_specs_webhook_starts_the_rollout_of_each_flavor_with_work(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    context: Day1Context,
) -> None:
    await link(client, support, gitlab, HERZI, "1.0.0")
    pid = await support.project_id(gitlab, support.SPECS)
    path = f"specs/{FLAVOR}.yaml"
    current = (await gitlab.read_file(pid, RepoPath(path), "main")).content
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file=path,
        content=current.replace('version: "1.0.0"', 'version: "1.1.0"'),
    )
    hooked = await client.post(
        "/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK
    )
    assert hooked.json() == {"status": "ok"}
    await context.rollouts.wait()
    assert list(await open_rollouts(gitlab, support)) == [HERZI]


async def test_reconcile_is_for_admins_and_answers_at_once(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    context: Day1Context,
) -> None:
    await link(client, support, gitlab, HERZI, "1.0.0")
    viewer = await client.post(f"/api/day1/specs/{FLAVOR}/rollout", headers=auth(support.VIEWER))
    assert viewer.status_code == 403
    response = await client.post(f"/api/day1/specs/{FLAVOR}/rollout", headers=auth(support.ALICE))
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["version"], body["running"], body["counts"]["on_version"]) == ("1.0.0", True, 1)
    await context.rollouts.wait()
    missing = await client.post("/api/day1/specs/nope/rollout", headers=auth(support.ALICE))
    assert missing.status_code == 404


async def test_the_review_page_preview_applies_only_to_a_flavor_update(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    created = await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    day1 = await client.get(f"/api/day1/approvals/{created.json()['iid']}/rollout", headers=bob)
    assert day1.json()["applies"] is False
    assert day1.json()["reason"] == "this merge request does not change a flavor"
    deleting = await client.delete("/api/day1/specs/agent-single", headers=alice)
    preview = await client.get(
        f"/api/day1/approvals/{deleting.json()['iid']}/rollout?repo=specs", headers=bob
    )
    assert preview.json()["applies"] is False
    assert preview.json()["reason"].startswith("deleting a flavor opens no merge requests")


async def test_a_flavor_edit_that_keeps_or_reuses_a_version_is_refused(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    spec = (await client.get(f"/api/day1/specs/{FLAVOR}", headers=alice)).json()
    for key in ("load_error", "load_problems", "warnings", "enforced_locks", "last_commit_id"):
        spec.pop(key, None)
    same = await client.put(f"/api/day1/specs/{FLAVOR}", json=spec, headers=alice)
    assert (same.status_code, same.json()["code"]) == (422, "VALIDATION_ERROR")
    assert same.json()["details"]["problems"] == [
        "metadata.version: 1.0.0 is the current version; an edit needs a new one, which "
        "reaches each cluster through its own merge request"
    ]
