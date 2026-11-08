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
            "reboots": False,
        }
    ]
