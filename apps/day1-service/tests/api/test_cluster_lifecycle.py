"""The whole cluster lifecycle over HTTP: list, create, approve, edit, delete.

Runs the real app (``create_app``) on the in-memory GitLab seeded from
dev/gitlab-fixtures; only the adapters are fakes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

NEW = "ocp4-prod-falcon-site1"
NEW_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{NEW}.yaml"

Auth = Callable[[User], dict[str, str]]


async def test_read_views_list_the_fixture_repo(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    headers = auth(support.VIEWER)
    assert (await client.get("/api/day1/sites", headers=headers)).json() == ["site1", "site2"]
    mces = (await client.get("/api/day1/sites/site1/mces", headers=headers)).json()
    assert mces == ["ocp4-mce-workflow-test", "ocp4-prep-mce-site1-a", "ocp4-prod-mce-site1-a"]

    clusters = (await client.get("/api/day1/clusters", headers=headers)).json()
    by_name = {c["name"]: c for c in clusters}
    assert len(clusters) == 14
    demo = by_name["ocp4-upgrade-demo"]
    assert demo["naming"]["follows_convention"] is False
    assert demo["mastertag"] == "4.21.40-x86_64"
    herzi = by_name["ocp4-prod-herzi-site1"]
    assert herzi["naming"] == {
        "follows_convention": True,
        "env": "prod",
        "short_name": "herzi",
        "sequence": None,
        "problems": [],
    }
    assert herzi["hosted_cluster"] == {
        "cluster_name": "prod-herzi-site1",
        "name": "openshift-prod-herzi-site1",
        "namespace": "hcp-prod-herzi-site1",
    }
    assert by_name["ocp4-prep-amit-site2-a"]["naming"]["sequence"] == "a"

    details = (await client.get("/api/day1/mces", headers=headers)).json()
    prod = next(m for m in details if m["name"] == "ocp4-prod-mce-site1-a")
    assert prod["default_mastertag"] == "4.16.27-x86_64"
    assert prod["hub_version"] == "4.16.27-x86_64"
    assert prod["env"] == "prod"
    lab = next(m for m in details if m["name"] == "ocp4-mce-workflow-test")
    assert lab["follows_convention"] is False


async def test_create_approve_edit_delete(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    day1 = await support.project_id(gitlab, support.DAY1)
    before = gitlab.snapshot(day1, "main")

    # Approvals are listed (and cached) before the create.
    assert (await client.get("/api/day1/approvals", headers=alice)).json() == []

    preview = await client.post(
        "/api/day1/clusters/preview", json=support.create_body(), headers=alice
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["path"] == NEW_PATH

    created = await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    assert created.status_code == 201, created.text
    mr = created.json()
    assert mr["title"] == f"[Wingman/Day1] Create cluster {NEW} from spec agent-standard"
    assert mr["source_branch"].startswith(f"platform/alice/create-cluster-{NEW}-")
    assert mr["labels"] == ["create", "day1", "wingman"]
    assert mr["author"]["username"] == "alice"
    assert mr["repo"] == "day1"

    # Exactly one file was added on the branch, and main is untouched.
    branch = gitlab.snapshot(day1, mr["source_branch"])
    assert set(branch) - set(before) == {NEW_PATH}
    assert {p: c for p, c in branch.items() if p in before} == before
    assert gitlab.snapshot(day1, "main") == before
    values = yaml.safe_load(branch[NEW_PATH])
    assert values["mastertag"] == "4.18.22-x86_64"
    assert [np["infraEnvName"] for np in values["nodepool"]] == [
        "dell-r660-site1-128c-1024gb-5tb",
        "hp-gen11-site1-64c",
    ]
    assert not {"vlanId", "dhcp_values", "mcFiles", "mcConfigMap"} & set(values)

    # The new MR shows up at once: the write cleared the cached list (legacy cleared the wrong key).
    pending = (await client.get("/api/day1/approvals", headers=alice)).json()
    assert [p["iid"] for p in pending] == [mr["iid"]]

    # A second create of the same name is refused while the first MR is open.
    again = await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    assert again.status_code == 409
    assert again.json()["code"] == "ALREADY_EXISTS"

    # The requester cannot approve; another admin approves the reviewed commit.
    detail = (await client.get(f"/api/day1/approvals/{mr['iid']}", headers=bob)).json()
    sha = detail["mr"]["sha"]
    own = await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": sha}, headers=alice
    )
    assert own.status_code == 403
    assert own.json()["code"] == "SELF_APPROVAL"
    merged = await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": sha}, headers=bob
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["state"] == "merged"

    # The merge cleared the cached tree: the new cluster is listed immediately.
    names = [c["name"] for c in (await client.get("/api/day1/clusters", headers=alice)).json()]
    assert NEW in names
    cluster = (await client.get(f"/api/day1/clusters/{NEW}", headers=alice)).json()
    assert cluster["metadata"]["spec_name"] == "agent-standard"
    assert cluster["metadata"]["requested_addons"] == [
        {"team": "redbull", "name": "cluster-roles", "version": "main", "override_values": {}}
    ]
    assert cluster["values"]["mastertag"] == "4.18.22-x86_64"

    # Automation commits vlanId/dhcp_values to main (as CI would after the workflow).
    content = cluster["yaml"] + "vlanId: 412\ndhcp_values:\n  network: 10.20.99.0\n"
    await support.push(gitlab, support.DAY1, branch="main", file=NEW_PATH, content=content)

    # An edit made from the stale read is refused (ADR-0006): GitLab itself refuses it,
    # because Wingman's cached read has not seen the push yet.
    stale = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={
            "updated_yaml": cluster["yaml"].replace("4.18.22", "4.18.23"),
            "last_commit_id": cluster["last_commit_id"],
        },
        headers=alice,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"

    # GitLab's push webhook clears the cached files; the next read sees the allocation.
    hook = await client.post(
        "/api/webhooks/gitlab",
        json={"object_kind": "push", "project": {"id": day1}, "ref": "refs/heads/main"},
        headers={"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"},
    )
    assert hook.json() == {"status": "ok"}
    fresh = (await client.get(f"/api/day1/clusters/{NEW}", headers=alice)).json()
    assert fresh["values"]["network"] == {"vlan_id": 412, "dhcp_network": "10.20.99.0"}
    # Dropping automation's keys is refused.
    dropped = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={"updated_yaml": cluster["yaml"], "last_commit_id": fresh["last_commit_id"]},
        headers=alice,
    )
    assert dropped.status_code == 422
    assert any("vlanId" in p for p in dropped.json()["details"]["problems"])

    edited = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={
            "updated_yaml": fresh["yaml"].replace("4.18.22", "4.18.23"),
            "last_commit_id": fresh["last_commit_id"],
        },
        headers=alice,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == f"[Wingman/Day1] Modify cluster {NEW}"

    deleted = await client.delete(
        f"/api/day1/clusters/{NEW}",
        params={"last_commit_id": fresh["last_commit_id"]},
        headers=alice,
    )
    assert deleted.status_code == 200, deleted.text
    delete_branch = gitlab.snapshot(day1, deleted.json()["source_branch"])
    assert NEW_PATH not in delete_branch
    assert RepoPath(NEW_PATH).parent.child(".gitkeep").value not in delete_branch
