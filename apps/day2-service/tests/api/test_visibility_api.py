"""A viewer never knows of an MCE, a seed or a KV cluster in day2 either (ADR-0067).

The day1 fixtures hold a seed, ``ocp4-prod-seed-site1-az1-a``, with two KV
cluster files beside the Customer MCEs and the tenants' clusters.
"""

from __future__ import annotations

import httpx
import pytest

SEED = "ocp4-prod-seed-site1-az1-a"
KV_A = "ocp4-prod-kv-site1-az1-a"
LARK = "ocp4-prod-lark-site1"


async def test_a_viewers_destinations_have_no_mce_seed_or_kv_cluster(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    every = (await jane.get("/api/day2/clusters")).json()
    assert {"mce", "hosted"} <= {c["kind"] for c in every}
    assert {KV_A, SEED} <= {c["name"] for c in every}

    shown = (await vic.get("/api/day2/clusters")).json()
    names = {c["name"] for c in shown}
    assert LARK in names
    assert "mce" not in {c["kind"] for c in shown}
    assert not names & {KV_A, SEED}


@pytest.mark.parametrize("sub", ["", "/addons", "/history"])
async def test_a_viewer_naming_a_kv_cluster_gets_what_an_unknown_one_gets(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, sub: str
) -> None:
    kv = await vic.get(f"/api/day2/clusters/{KV_A}{sub}")
    unknown = await vic.get(f"/api/day2/clusters/ocp4-prod-nothere-site1-a{sub}")
    assert kv.status_code == unknown.status_code == 404
    assert kv.json()["code"] == unknown.json()["code"]
    assert (await jane.get(f"/api/day2/clusters/{KV_A}{sub}")).status_code == 200


async def test_a_viewer_naming_an_mce_hub_gets_not_found(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    mce = next(c for c in (await jane.get("/api/day2/clusters")).json() if c["kind"] == "mce")
    assert (await vic.get(f"/api/day2/clusters/{mce['id']}")).status_code == 404
    assert (await jane.get(f"/api/day2/clusters/{mce['id']}")).status_code == 200
