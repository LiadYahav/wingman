"""``/api/day1/approvals`` and ``/api/day1/audit`` over HTTP."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.merge_request import NewMergeRequest
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]
NEW = "ocp4-prod-falcon-site1"
NEW_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{NEW}.yaml"
SPEC = {"metadata": {"name": "agent-mini", "version": "1.0.0"}}


async def open_cluster_mr(client: httpx.AsyncClient, auth: Auth, support: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/day1/clusters", json=support.create_body(), headers=auth(support.ALICE)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_list_has_the_legacy_mr_shape_plus_project_and_sha(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    [listed] = (await client.get("/api/day1/approvals", headers=auth(support.VIEWER))).json()
    assert set(listed) == {
        "iid", "project_id", "title", "description", "author", "state", "created_at",
        "updated_at", "merged_at", "web_url", "source_branch", "target_branch", "labels",
        "repo", "has_conflicts", "sha", "opened_by_workflow",
    }  # fmt: skip
    assert listed["iid"] == mr["iid"]
    assert listed["author"] == {"username": "alice", "name": "alice", "avatar_url": ""}
    assert listed["state"] == "opened"
    assert listed["opened_by_workflow"] is None


async def test_expanding_an_mr_without_repo_reaches_the_day1_project(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    # Legacy: ?repo= was required, and the audit page's expand (which sends none)
    # answered 422 for every day1 MR.
    mr = await open_cluster_mr(client, auth, support)
    response = await client.get(f"/api/day1/approvals/{mr['iid']}", headers=auth(support.VIEWER))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mr"]["repo"] == "day1"
    assert [d["new_path"] for d in body["diffs"]] == [NEW_PATH]
    assert body["diffs"][0]["new_file"] is True


async def test_the_same_iid_in_the_specs_project_is_addressed_by_repo(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    # ADR-0007: an MR is (project, iid); both projects now have a !1.
    cluster_mr = await open_cluster_mr(client, auth, support)
    spec_mr = (await client.post("/api/day1/specs", json=SPEC, headers=auth(support.ALICE))).json()
    assert cluster_mr["iid"] == spec_mr["iid"] == 1
    headers = auth(support.VIEWER)
    day1 = (await client.get("/api/day1/approvals/1", headers=headers)).json()
    specs = (await client.get("/api/day1/approvals/1?repo=specs", headers=headers)).json()
    assert day1["mr"]["title"].startswith("[Wingman/Day1]")
    assert specs["mr"]["title"].startswith("[Wingman/Specs]")
    assert day1["mr"]["project_id"] != specs["mr"]["project_id"]
    unknown = await client.get("/api/day1/approvals/1?repo=day2", headers=headers)
    assert unknown.status_code == 422


async def test_approve_needs_the_reviewed_sha(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    response = await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={}, headers=auth(support.BOB)
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["errors"][0]["loc"] == ["body", "sha"]


async def test_a_push_after_review_blocks_the_merge_until_reviewed_again(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    bob = auth(support.BOB)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[NEW_PATH]
    await support.push(
        gitlab,
        support.DAY1,
        branch=mr["source_branch"],
        file=NEW_PATH,
        content=content + "vlanId: 412\n",
    )
    stale = await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": mr["sha"]}, headers=bob
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "REVISION_CONFLICT")
    assert NEW_PATH not in gitlab.snapshot(pid, "main")

    head = (await client.get(f"/api/day1/approvals/{mr['iid']}", headers=bob)).json()["mr"]["sha"]
    merged = await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": head}, headers=bob
    )
    assert merged.json()["state"] == "merged"
    assert "vlanId: 412" in gitlab.snapshot(pid, "main")[NEW_PATH]


async def test_reject_closes_and_the_list_forgets_it(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    bob = auth(support.BOB)
    assert len((await client.get("/api/day1/approvals", headers=bob)).json()) == 1
    rejected = await client.post(f"/api/day1/approvals/{mr['iid']}/reject", headers=bob)
    assert rejected.json()["state"] == "closed"
    assert (await client.get("/api/day1/approvals", headers=bob)).json() == []
    again = await client.post(f"/api/day1/approvals/{mr['iid']}/reject", headers=bob)
    assert (again.status_code, again.json()["code"]) == (409, "NOT_MERGEABLE")


async def test_put_commits_edited_files_on_top_of_the_branch(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    bob = auth(support.BOB)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[NEW_PATH]

    outside = await client.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={"files": [{"path": "sites/configValues.yaml", "content": "x: 1\n"}]},
        headers=bob,
    )
    assert (outside.status_code, outside.json()["code"]) == (422, "VALIDATION_ERROR")

    edited = content.replace("replicas: 2", "replicas: 3", 1)
    stale = await client.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={"files": [{"path": NEW_PATH, "content": edited}], "sha": "0" * 40},
        headers=bob,
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "REVISION_CONFLICT")

    ok = await client.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={
            "files": [{"path": NEW_PATH, "content": edited}],
            "sha": mr["sha"],
            "message": "3 workers",
        },
        headers=bob,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["mr"]["sha"] != mr["sha"]
    commits = await gitlab.list_commits(pid, ref=mr["source_branch"], limit=1)
    assert (commits[0].title, commits[0].author_name) == ("3 workers", "Bob Admin")


async def test_a_viewer_cannot_decide_or_edit(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    viewer = auth(support.VIEWER)
    for response in (
        await client.post(
            f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": mr["sha"]}, headers=viewer
        ),
        await client.post(f"/api/day1/approvals/{mr['iid']}/reject", headers=viewer),
        await client.put(
            f"/api/day1/approvals/{mr['iid']}",
            json={"files": [{"path": NEW_PATH, "content": "x"}]},
            headers=viewer,
        ),
    ):
        assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")


async def test_an_mr_outside_the_managed_projects_is_not_found(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get("/api/day1/approvals/99", headers=auth(support.VIEWER))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_audit_lists_carry_the_repo_and_paginate(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await open_cluster_mr(client, auth, support)
    await client.post("/api/day1/specs", json=SPEC, headers=auth(support.ALICE))
    viewer = auth(support.VIEWER)
    mrs = (await client.get("/api/day1/audit/merge-requests", headers=viewer)).json()
    assert [m["repo"] for m in mrs] == ["specs", "day1"]
    commits = (await client.get("/api/day1/audit/commits", headers=viewer)).json()
    assert {c["repo"] for c in commits} == {"day1", "specs"}
    assert set(commits[0]) == {
        "id", "short_id", "title", "author_name", "author_email", "authored_date", "message",
        "web_url", "repo",
    }  # fmt: skip
    page_two = (
        await client.get("/api/day1/audit/commits?per_page=1&page=2", headers=viewer)
    ).json()
    assert [c["id"] for c in page_two] == [commits[1]["id"]]
    too_big = await client.get("/api/day1/audit/commits?per_page=500", headers=viewer)
    assert too_big.status_code == 422


async def test_audit_lists_only_wingman_mrs_and_each_one_expands(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    # An MR someone opened by hand in the day1 repo is not Wingman's: listing
    # it made the audit page offer an expand that could only fail.
    mr = await open_cluster_mr(client, auth, support)
    pid = await support.project_id(gitlab, support.DAY1)
    await gitlab.create_branch(pid, "by-hand", "main")
    await gitlab.create_merge_request(
        pid, NewMergeRequest(source_branch="by-hand", target_branch="main", title="Bump a value")
    )
    viewer = auth(support.VIEWER)
    mrs = (await client.get("/api/day1/audit/merge-requests", headers=viewer)).json()
    assert [m["iid"] for m in mrs] == [mr["iid"]]
    for listed in mrs:
        expanded = await client.get(
            f"/api/day1/approvals/{listed['iid']}?repo={listed['repo']}", headers=viewer
        )
        assert expanded.status_code == 200, expanded.text


async def test_audit_commit_diffs_and_unknown_commits(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = auth(support.VIEWER)
    commits = (await client.get("/api/day1/audit/commits", headers=viewer)).json()
    specs_commit = next(c for c in commits if c["repo"] == "specs")
    diff = await client.get(
        f"/api/day1/audit/commits/day1/{specs_commit['id']}/diff", headers=viewer
    )
    assert diff.status_code == 200
    assert diff.json()
    missing = await client.get("/api/day1/audit/commits/day1/deadbeefdeadbeef/diff", headers=viewer)
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


async def test_an_approved_merge_names_the_requester_in_history(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mr = await open_cluster_mr(client, auth, support)
    bob = auth(support.BOB)
    await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": mr["sha"]}, headers=bob
    )
    history = (await client.get(f"/api/day1/clusters/{NEW}/history", headers=bob)).json()
    assert "Alice Admin" in [c["author"] for c in history]
