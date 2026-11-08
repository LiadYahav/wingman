"""Flavors and the clusters that follow them, over HTTP: drift, import, sync, use.

The web stage is built from ``docs/notes/2026-11-08-flavors-v2-api-changes.md``;
these tests hold the JSON to it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
LARK = "ocp4-prod-lark-site1"
HERON = "ocp4-prod-heron-site1"


async def link(
    client: httpx.AsyncClient, support: Any, gitlab: InMemoryGitLab, name: str, flavor: str
) -> None:
    """Write a flavor header onto a fixture file on main, as a merged import would."""
    pid = await support.project_id(gitlab, support.DAY1)
    path = f"{HOSTED}/{name}.yaml"
    current = await gitlab.read_file(pid, RepoPath(path), "main")
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=path,
        content=f'# specName: "{flavor}"\n# specVersion: "1.0.0"\n{current.content}',
    )
    await client.post(
        "/api/webhooks/gitlab",
        json={"project": {"id": pid}},
        headers={"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"},
    )


async def test_drift_lists_each_locked_value_the_file_does_not_hold(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(client, support, gitlab, LARK, "agent-baseline")
    response = await client.get(f"/api/day1/clusters/{LARK}/drift", headers=auth(support.VIEWER))
    assert response.status_code == 200, response.text
    drift = response.json()
    assert (drift["state"], drift["is_drifted"], drift["error"]) == ("drifted", True, None)
    first, second = drift["value_drift"]
    assert first == {
        "path": "nodepools[*].configs",
        "file_key": "nodepool[0].configs",
        "nodepool": {"index": 0, "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"},
        "flavor_value": [
            {"name": "nm-conf-prod-lark-site1-dell"},
            {"name": "workers-chrony-configuration"},
            {"name": "nic-ring-buffer"},
        ],
        "cluster_value": [
            {"name": "nm-conf-prod-lark-site1-dell"},
            {"name": "worker-kubeletconfig-reserved"},
            {"name": "nic-ring-buffer"},
            {"name": "workers-chrony-configuration"},
        ],
        "in_file": True,
        "added": [],
        "removed": ["worker-kubeletconfig-reserved"],
        "needs_decision": None,
        "needs_hardware": False,
        "reboots": True,
    }
    assert (second["added"], second["removed"]) == (
        ["nic-ring-buffer"],
        ["restored-example-config"],
    )
    assert [a["addon_name"] for a in drift["addon_drift"]] == ["cluster-roles"]


async def test_a_value_the_file_lacks_is_null_and_not_in_file(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    flavor = {
        "metadata": {"name": "agent-owned", "version": "1.0.0"},
        "spec": {"day1": {"locked_paths": ["platform"], "values": {"platform": "kubevirt"}}},
    }
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file="specs/agent-owned.yaml",
        content=yaml.safe_dump(flavor),
    )
    await link(client, support, gitlab, LARK, "agent-owned")
    drift = (
        await client.get(f"/api/day1/clusters/{LARK}/drift", headers=auth(support.VIEWER))
    ).json()
    assert drift["value_drift"] == [
        {
            "path": "platform",
            "file_key": "platform",
            "nodepool": None,
            "flavor_value": "kubevirt",
            "cluster_value": None,
            "in_file": False,
            "added": [],
            "removed": [],
            "needs_decision": None,
            "needs_hardware": False,
            "reboots": False,
        }
    ]


# ── Import ───────────────────────────────────────────────────────────────────


async def test_the_import_preview_lists_each_cluster_with_its_drift_against_the_flavor(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.post(
        "/api/day1/specs/agent-baseline/import/preview",
        json={"clusters": [{"name": LARK}, {"name": HERON, "site": "site1"}]},
        headers=auth(support.ALICE),
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert (preview["spec_name"], preview["spec_version"], preview["warnings"]) == (
        "agent-baseline",
        "1.0.0",
        [],
    )
    lark, heron = preview["clusters"]
    assert {k: v for k, v in lark.items() if k != "drift"} == {
        "name": LARK,
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "path": f"{HOSTED}/{LARK}.yaml",
        "last_commit_id": lark["last_commit_id"],
        "status": "ready",
        "linked_spec": None,
        "problems": [],
    }
    assert len(lark["last_commit_id"]) == 40
    assert lark["drift"]["state"] == "drifted"
    assert lark["drift"]["spec_name"] == "agent-baseline"
    assert lark["drift"]["spec_version"] is None
    assert [d["file_key"] for d in lark["drift"]["value_drift"]] == [
        "nodepool[0].configs",
        "nodepool[1].configs",
    ]
    assert heron["drift"]["value_drift"][0]["needs_decision"].startswith(
        "nodepool[0] has no network config"
    )


async def test_the_import_opens_one_day1_mr(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    headers = auth(support.ALICE)
    preview = (
        await client.post(
            "/api/day1/specs/agent-baseline/import/preview",
            json={"clusters": [{"name": LARK}]},
            headers=headers,
        )
    ).json()
    (lark,) = preview["clusters"]
    body = {
        "spec_version": preview["spec_version"],
        "clusters": [
            {
                "name": lark["name"],
                "site": lark["site"],
                "mce": lark["mce"],
                "last_commit_id": lark["last_commit_id"],
            }
        ],
    }
    response = await client.post(
        "/api/day1/specs/agent-baseline/import", json=body, headers=headers
    )
    assert response.status_code == 201, response.text
    mr = response.json()
    assert (mr["repo"], mr["title"]) == (
        "day1",
        "[Wingman/Day1] Import spec agent-baseline into 1 cluster",
    )
    assert mr["labels"] == ["day1", "import", "wingman"]
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[lark["path"]]
    assert content.startswith('# specName: "agent-baseline"\n# specVersion: "1.0.0"\n# Placeholder')
    again = await client.post("/api/day1/specs/agent-baseline/import", json=body, headers=headers)
    assert again.status_code == 201  # the file on main is unchanged until the MR merges


async def test_import_problems_are_422s_and_a_moved_file_is_409(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    headers = auth(support.ALICE)
    pick = {"name": LARK, "site": "site1", "mce": "ocp4-prod-mce-site1-a"}
    stale = {"spec_version": "1.0.0", "clusters": [{**pick, "last_commit_id": "0" * 40}]}
    response = await client.post(
        "/api/day1/specs/agent-baseline/import", json=stale, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_CONFLICT"
    await link(client, support, gitlab, LARK, "agent-dell")
    preview = (
        await client.post(
            "/api/day1/specs/agent-baseline/import/preview",
            json={"clusters": [{"name": LARK}]},
            headers=headers,
        )
    ).json()
    (lark,) = preview["clusters"]
    assert (lark["status"], lark["linked_spec"]) == (
        "relink",
        {"name": "agent-dell", "version": "1.0.0"},
    )
    body = {
        "spec_version": "1.0.0",
        "clusters": [{**pick, "last_commit_id": lark["last_commit_id"]}],
    }
    response = await client.post(
        "/api/day1/specs/agent-baseline/import", json=body, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["details"]["problems"] == [
        "ocp4-prod-lark-site1: follows flavor agent-dell v1.0.0; send relink: true to link it "
        "to agent-baseline instead"
    ]
    body["clusters"][0]["relink"] = True
    response = await client.post(
        "/api/day1/specs/agent-baseline/import", json=body, headers=headers
    )
    assert response.status_code == 201, response.text


async def test_import_is_for_admins(client: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    response = await client.post(
        "/api/day1/specs/agent-baseline/import/preview",
        json={"clusters": [{"name": LARK}]},
        headers=auth(support.VIEWER),
    )
    assert response.status_code == 403


# ── Sync ─────────────────────────────────────────────────────────────────────


async def test_the_sync_preview_says_what_changes_what_is_removed_and_what_rolls(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(client, support, gitlab, LARK, "agent-baseline")
    response = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    pools = [
        {"index": 0, "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"},
        {"index": 1, "name": "prod-lark-site1-dell-r760-site1-64c-512gb-20tb"},
    ]
    assert {k: preview[k] for k in ("cluster", "site", "mce", "path", "spec_name")} == {
        "cluster": LARK,
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "path": f"{HOSTED}/{LARK}.yaml",
        "spec_name": "agent-baseline",
    }
    assert (preview["spec_version"], preview["file_spec_version"]) == ("1.0.0", "1.0.0")
    assert len(preview["last_commit_id"]) == 40
    assert [c["file_key"] for c in preview["changes"]] == [
        "nodepool[0].configs",
        "nodepool[1].configs",
    ]
    assert preview["removals"] == [
        {"nodepool": pools[0], "name": "worker-kubeletconfig-reserved"},
        {"nodepool": pools[1], "name": "restored-example-config"},
    ]
    assert preview["rebooting"] == [
        {
            "nodepool": pools[0],
            "replicas": 3,
            "upgrade_type": None,
            "max_unavailable": None,
            "replaces_nodes": False,
        },
        {
            "nodepool": pools[1],
            "replicas": 2,
            "upgrade_type": None,
            "max_unavailable": None,
            "replaces_nodes": False,
        },
    ]
    assert (preview["problems"], preview["warnings"], preview["can_sync"]) == ([], [], True)
    assert "-  - name: worker-kubeletconfig-reserved\n" in preview["diff"]
    assert [a["addon_name"] for a in preview["addons_to_install"]] == ["cluster-roles"]
    assert (preview["version_differences"], preview["addons_error"]) == ([], None)


async def test_the_sync_opens_one_day1_mr_once_the_removals_are_confirmed(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(client, support, gitlab, LARK, "agent-baseline")
    headers = auth(support.ALICE)
    preview = (
        await client.post(f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=headers)
    ).json()
    body: dict[str, Any] = {
        "last_commit_id": preview["last_commit_id"],
        "spec_version": preview["spec_version"],
    }
    refused = await client.post(f"/api/day1/clusters/{LARK}/sync", json=body, headers=headers)
    assert refused.status_code == 422
    assert len(refused.json()["details"]["problems"]) == 2
    body["confirm_removals"] = [
        {"nodepool": r["nodepool"]["index"], "name": r["name"]} for r in preview["removals"]
    ]
    response = await client.post(f"/api/day1/clusters/{LARK}/sync", json=body, headers=headers)
    assert response.status_code == 201, response.text
    mr = response.json()
    assert (mr["repo"], mr["title"]) == (
        "day1",
        f"[Wingman/Day1] Sync cluster {LARK} to spec agent-baseline v1.0.0",
    )
    assert mr["labels"] == ["day1", "sync", "wingman"]
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr["source_branch"])[preview["path"]]
    assert "worker-kubeletconfig-reserved\n  - name: nic" not in content


async def test_sync_needs_an_admin_and_a_cluster_on_a_flavor(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=auth(support.VIEWER)
    )
    assert viewer.status_code == 403
    unlinked = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=auth(support.ALICE)
    )
    assert unlinked.status_code == 422
    assert unlinked.json()["details"]["problems"] == [
        f"{LARK}: import it into a flavor first (POST /specs/<flavor>/import)"
    ]
    missing = await client.post(
        "/api/day1/clusters/ocp4-prod-nope-site1/sync/preview", json={}, headers=auth(support.ALICE)
    )
    assert missing.status_code == 404
    bad = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview",
        json={"hardware": [{"nodepool": -1, "hardware": "dell"}]},
        headers=auth(support.ALICE),
    )
    assert bad.status_code == 422


async def test_a_hardware_choice_is_sent_per_nodepool(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(client, support, gitlab, HERON, "agent-baseline")
    headers = auth(support.ALICE)
    waiting = (
        await client.post(f"/api/day1/clusters/{HERON}/sync/preview", json={}, headers=headers)
    ).json()
    assert waiting["can_sync"] is False
    assert [c["needs_hardware"] for c in waiting["changes"]] == [True, True]
    chosen = (
        await client.post(
            f"/api/day1/clusters/{HERON}/sync/preview",
            json={
                "hardware": [
                    {"nodepool": 0, "hardware": "dell"},
                    {"nodepool": 1, "hardware": "dell"},
                ]
            },
            headers=headers,
        )
    ).json()
    assert (chosen["can_sync"], chosen["problems"]) == (True, [])
    assert [c["needs_decision"] for c in chosen["changes"]] == [None, None]
