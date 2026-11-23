"""The whole cluster lifecycle over HTTP: list, create, the workflow's merge, edit, delete.

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
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

NEW = "ocp4-prod-falcon-site1"
NEW_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{NEW}.yaml"

Auth = Callable[[User], dict[str, str]]


async def hook(client: httpx.AsyncClient, project_id: int, event: str) -> None:
    """GitLab's webhook for ``event`` in the day1 project: it clears what went stale."""
    response = await client.post(
        "/api/webhooks/gitlab",
        json={"object_kind": "push", "project": {"id": project_id}, "ref": "refs/heads/main"},
        headers={"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": event},
    )
    assert response.json() == {"status": "ok"}


async def test_read_views_list_the_fixture_repo(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    headers, admin = auth(support.VIEWER), auth(support.ALICE)
    assert (await client.get("/api/day1/sites", headers=admin)).json() == ["site1", "site2"]
    mces = (await client.get("/api/day1/sites/site1/mces", headers=admin)).json()
    assert mces == [
        "ocp4-mce-workflow-test",
        "ocp4-prep-mce-site1-a",
        "ocp4-prod-mce-site1-a",
        "ocp4-prod-mce-site1-b",
        "ocp4-prod-mce-site1-c",
        "ocp4-prod-seed-site1-az1-a",
    ]

    clusters = (await client.get("/api/day1/clusters", headers=headers)).json()
    by_name = {c["name"]: c for c in clusters}
    assert len(clusters) == 14  # a viewer's: the two KV clusters are left out (ADR-0067)
    assert {c["kind"] for c in clusters} == {"tenant"}
    lark = by_name["ocp4-prod-lark-site1"]
    assert lark["owner"] == {"merkaz": "1234", "anaf": "56", "mador": "7"}
    demo = by_name["ocp4-upgrade-demo"]
    assert demo["naming"]["follows_convention"] is False
    assert demo["mastertag"] == "4.21.40-x86_64"
    herzi = by_name["ocp4-prod-herzi-site1"]
    assert herzi["naming"] == {
        "follows_convention": True,
        "env": "prod",
        "short_name": "herzi",
        "sequence": None,
        "zone": None,
        "problems": [],
    }
    assert herzi["hosted_cluster"] == {
        "cluster_name": "prod-herzi-site1",
        "name": "ocp4-prod-herzi-site1",
        "namespace": "hcp-prod-herzi-site1",
    }
    assert by_name["ocp4-prep-amit-site2-a"]["naming"]["sequence"] == "a"

    details = (await client.get("/api/day1/mces", headers=admin)).json()
    prod = next(m for m in details if m["name"] == "ocp4-prod-mce-site1-a")
    assert prod["default_mastertag"] == "4.16.27-x86_64"
    assert prod["hub_version"] == "4.16.27-x86_64"
    assert prod["env"] == "prod"
    lab = next(m for m in details if m["name"] == "ocp4-mce-workflow-test")
    assert lab["follows_convention"] is False
    assert {m["kind"] for m in details if m["name"] != "ocp4-prod-seed-site1-az1-a"} == {"mce"}


async def test_create_merge_edit_delete(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    provision: FakeProvisionWorkflow,
) -> None:
    alice = auth(support.ALICE)
    day1 = await support.project_id(gitlab, support.DAY1)
    before = gitlab.snapshot(day1, "main")

    preview = await client.post(
        "/api/day1/clusters/preview", json=support.create_body(), headers=alice
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["path"] == NEW_PATH

    # A create starts provision-cluster with exactly the previewed file (ADR-0042).
    created = await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    assert created.status_code == 202, created.text
    assert created.json()["workflow_id"] == f"provision-cluster-{NEW}"
    (started,) = provision.starts
    assert started["content"] == preview.json()["yaml"]
    values = yaml.safe_load(started["content"])
    assert values["mastertag"] == "4.18.56-x86_64"
    assert [np["infraEnvName"] for np in values["nodepool"]] == [
        "dell-r660-site1-128c-1024gb-5tb",
        "hp-gen11-site1-64c",
    ]
    assert not {"vlanId", "dhcp_values", "mcFiles", "mcConfigMap"} & set(values)
    # Wingman wrote nothing: the workflow pushes the file and opens the merge request.
    assert gitlab.snapshot(day1, "main") == before
    assert await gitlab.list_merge_requests(day1, state=None) == []

    # While the workflow's merge request is open, a second create of the name is refused.
    await support.open_provision_mr(gitlab, NEW)
    await hook(client, day1, "Merge Request Hook")
    again = await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_EXISTS")
    assert "an open merge request already creates" in again.json()["detail"]

    # A person merges it: the file Wingman sent, with the segment the workflow reserved.
    await support.provisioned(gitlab, started)
    await hook(client, day1, "Push Hook")
    names = [c["name"] for c in (await client.get("/api/day1/clusters", headers=alice)).json()]
    assert NEW in names
    cluster = (await client.get(f"/api/day1/clusters/{NEW}", headers=alice)).json()
    assert cluster["metadata"]["spec_name"] == "agent-standard"
    assert cluster["metadata"]["requested_addons"] == [
        {"team": "redbull", "name": "cluster-roles", "version": "main", "override_values": {}}
    ]
    assert cluster["values"]["mastertag"] == "4.18.56-x86_64"
    assert cluster["values"]["network"] == {
        "vlan_id": 1234,
        "dhcp_network": "10.20.50.0",
        "segment": "10.20.50.0/24",
    }

    # CI commits its keys to main.
    content = cluster["yaml"] + "\nmcFiles:\n- worker-kubeletconfig-reserved\n"
    await support.push(gitlab, support.DAY1, branch="main", file=NEW_PATH, content=content)

    # An edit made from the stale read is refused (ADR-0006): GitLab itself refuses it,
    # because Wingman's cached read has not seen the push yet.
    stale = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={
            "updated_yaml": cluster["yaml"].replace("4.18.56", "4.18.57"),
            "last_commit_id": cluster["last_commit_id"],
        },
        headers=alice,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"

    # GitLab's push webhook clears the cached files; the next read sees CI's keys.
    await hook(client, day1, "Push Hook")
    fresh = (await client.get(f"/api/day1/clusters/{NEW}", headers=alice)).json()
    assert "mcFiles" in fresh["yaml"]
    # Dropping automation's keys is refused.
    dropped = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={"updated_yaml": cluster["yaml"], "last_commit_id": fresh["last_commit_id"]},
        headers=alice,
    )
    assert dropped.status_code == 422
    assert any("mcFiles" in p for p in dropped.json()["details"]["problems"])

    edited = await client.patch(
        f"/api/day1/clusters/{NEW}",
        json={
            "updated_yaml": fresh["yaml"].replace("4.18.56", "4.18.57"),
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
