"""A KV cluster's workers and its zone check on the cluster list and page (ADR-0067).

The fixtures' seed ``ocp4-prod-seed-site1-az1-a`` holds ``-a`` (2 workers)
and ``-b`` (3), both naming zone ``az1``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]
SEED = "ocp4-prod-seed-site1-az1-a"
CLUSTERS = "/api/day1/clusters"
STRAY = "ocp4-prod-kv-site1-az1-c"
STRAY_FILE = f"sites/site1/mces/{SEED}/hostedClusters/{STRAY}.yaml"
OTHER_ZONE = (
    'owner:\n  merkaz: "1000"\n  anaf: "10"\n  mador: "1"\nmastertag: 4.18.22-x86_64\n'
    "nodepool:\n- infraEnvName: r760-mtl-az2\n  replicas: 4\n"
    "  nodeLabels:\n    topology.kubernetes.io/zone: az2\n"
    "- infraEnvName: r760-mtl-az1\n  replicas: 1\n"
)


async def test_a_kv_cluster_carries_its_workers_and_no_zone_problem(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    clusters = (await client.get(CLUSTERS, headers=auth(support.ALICE))).json()
    kv = {c["name"]: c["kv"] for c in clusters if c["kind"] == "kv"}
    assert kv["ocp4-prod-kv-site1-az1-a"] == {"workers": 2, "max_workers": 40, "zone_problems": []}
    assert kv["ocp4-prod-kv-site1-az1-b"]["workers"] == 3
    assert all(c["kv"] is None for c in clusters if c["kind"] == "tenant")


async def test_a_kv_cluster_whose_nodepools_name_another_zone_or_none_is_flagged(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(gitlab, support.DAY1, branch="main", file=STRAY_FILE, content=OTHER_ZONE)
    clusters = (await client.get(CLUSTERS, headers=auth(support.ALICE))).json()
    stray = next(c for c in clusters if c["name"] == STRAY)
    assert stray["kv"]["workers"] == 5
    assert stray["kv"]["zone_problems"] == [
        "nodepool[0] (r760-mtl-az2) names zone 'az2', not 'az1' as the cluster's name does",
        "nodepool[1] (r760-mtl-az1) names no zone: its nodeLabels have no "
        "topology.kubernetes.io/zone",
    ]
    detail = (await client.get(f"{CLUSTERS}/{STRAY}", headers=auth(support.ALICE))).json()
    assert detail["kv"] == stray["kv"]
    lark = await client.get(f"{CLUSTERS}/ocp4-prod-lark-site1", headers=auth(support.ALICE))
    assert lark.json()["kv"] is None
