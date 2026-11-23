"""Seeds, KV clusters and what a viewer never knows of them (ADR-0067).

The fixtures' ``sites/site1/mces/ocp4-prod-seed-site1-az1-a/`` is a seed with
two KV cluster files, named by the platform's naming convention.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_day1.api.deps import Day1Context
from wingman_day1.domain.errors import InvalidInputError
from wingman_day1.domain.paths import ClusterRef

Auth = Callable[[User], dict[str, str]]
SEED = "ocp4-prod-seed-site1-az1-a"
KV_A = "ocp4-prod-kv-site1-az1-a"
KV_B = "ocp4-prod-kv-site1-az1-b"
LARK = "ocp4-prod-lark-site1"
HERZI = "ocp4-prod-herzi-site1"
PROD_MCE = "ocp4-prod-mce-site1-a"
MISSING = "ocp4-prod-nothere-site1-a"
CLUSTERS = "/api/day1/clusters"


# ── Kinds ────────────────────────────────────────────────────────────────────


async def test_an_admin_lists_every_cluster_with_its_kind(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    clusters = (await client.get(CLUSTERS, headers=auth(support.ALICE))).json()
    kinds = {c["name"]: c["kind"] for c in clusters}
    assert kinds[KV_A] == kinds[KV_B] == "kv"
    assert kinds[LARK] == "tenant"
    assert sum(kind == "tenant" for kind in kinds.values()) == 14
    kv = next(c for c in clusters if c["name"] == KV_A)
    assert (kv["site"], kv["mce"]) == ("site1", SEED)
    # The convention's KV name is not flagged off-convention any more
    assert kv["naming"] == {
        "follows_convention": True,
        "env": "prod",
        "short_name": "kv",
        "sequence": "a",
        "zone": "az1",
        "problems": [],
    }


async def test_an_admin_reads_the_seed_with_its_kind_and_zone(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    mces = (await client.get("/api/day1/mces?site=site1", headers=auth(support.ALICE))).json()
    seed = next(m for m in mces if m["name"] == SEED)
    assert seed | {"naming_problems": None} == seed | {
        "kind": "seed",
        "env": "prod",
        "letter": "a",
        "zone": "az1",
        "follows_convention": True,
        "naming_problems": None,
        "cluster_count": 2,
        "hub_version": "4.18.22-x86_64",
    }
    assert seed["naming_problems"] == []
    prod = next(m for m in mces if m["name"] == PROD_MCE)
    assert (prod["kind"], prod["zone"]) == ("mce", None)


async def test_a_kv_cluster_page_reads_like_any_hosted_cluster_for_an_admin(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    detail = await client.get(f"{CLUSTERS}/{KV_A}", headers=auth(support.ALICE))
    assert detail.status_code == 200, detail.text
    assert (detail.json()["kind"], detail.json()["mce"]) == ("kv", SEED)
    lark = (await client.get(f"{CLUSTERS}/{LARK}", headers=auth(support.VIEWER))).json()
    assert lark["kind"] == "tenant"


# ── What a viewer never receives ─────────────────────────────────────────────


async def test_a_viewers_lists_have_no_kv_cluster(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = auth(support.VIEWER)
    names = {c["name"] for c in (await client.get(CLUSTERS, headers=viewer)).json()}
    assert LARK in names
    assert not names & {KV_A, KV_B}
    drift = (await client.get(f"{CLUSTERS}/drift-summary", headers=viewer)).json()
    assert {d["name"] for d in drift} == names


@pytest.mark.parametrize("sub", ["", "/current-yaml", "/history", "/drift", "/network"])
async def test_a_viewer_opening_a_kv_cluster_gets_what_a_missing_cluster_gets(
    client: httpx.AsyncClient, auth: Auth, support: Any, sub: str
) -> None:
    viewer = auth(support.VIEWER)
    kv = await client.get(f"{CLUSTERS}/{KV_A}{sub}", headers=viewer)
    missing = await client.get(f"{CLUSTERS}/{MISSING}{sub}", headers=viewer)
    assert (kv.status_code, kv.json()["code"]) == (missing.status_code, missing.json()["code"])
    assert (kv.status_code, kv.json()["code"]) == (404, "NOT_FOUND")
    assert kv.json()["detail"] == missing.json()["detail"].replace(MISSING, KV_A)
    assert SEED not in kv.text
    admin = await client.get(f"{CLUSTERS}/{KV_A}{sub}", headers=auth(support.ALICE))
    assert admin.status_code == 200, admin.text


async def test_a_viewer_naming_the_seed_or_a_kv_cluster_gets_not_found(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = auth(support.VIEWER)
    for params in ({"site": "site1", "mce": SEED}, {"mce": SEED}):
        read = await client.get(f"{CLUSTERS}/{KV_A}", params=params, headers=viewer)
        assert read.status_code == 404
    status = await client.get(f"{CLUSTERS}/{KV_A}/status", params={"mce": SEED}, headers=viewer)
    assert (status.status_code, status.json()["code"]) == (404, "NOT_FOUND")
    run = await client.get(f"{CLUSTERS}/{KV_A}/provision-run", headers=viewer)
    assert run.status_code == 404


async def test_a_viewers_bulk_status_leaves_a_kv_cluster_out(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = {"clusters": [{"name": HERZI, "mce": PROD_MCE}, {"name": KV_A, "mce": SEED}]}
    viewer = await client.post(f"{CLUSTERS}/bulk-status", json=body, headers=auth(support.VIEWER))
    assert set(viewer.json()) == {HERZI}
    admin = await client.post(f"{CLUSTERS}/bulk-status", json=body, headers=auth(support.ALICE))
    assert set(admin.json()) == {HERZI, KV_A}


@pytest.mark.parametrize(
    "path",
    [
        "/api/day1/sites",
        "/api/day1/sites/site1/mces",
        "/api/day1/mces",
        f"/api/day1/mces/{PROD_MCE}/openshift-versions",
        f"/api/day1/mces/{PROD_MCE}/infraenvs",
        "/api/day1/placement?site=site1&env=prod",
    ],
)
async def test_a_viewer_never_receives_a_list_of_sites_or_mces(
    client: httpx.AsyncClient, auth: Auth, support: Any, path: str
) -> None:
    response = await client.get(path, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert (await client.get(path, headers=auth(support.ALICE))).status_code == 200


async def test_a_viewer_sees_no_merge_request_about_a_kv_cluster(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    admin, viewer = auth(support.ALICE), auth(support.VIEWER)
    fresh = (await client.get(f"{CLUSTERS}/{KV_A}", headers=admin)).json()
    edited = await client.patch(
        f"{CLUSTERS}/{KV_A}",
        json={
            "updated_yaml": fresh["yaml"].replace("replicas: 2", "replicas: 3"),
            "last_commit_id": fresh["last_commit_id"],
        },
        headers=admin,
    )
    assert edited.status_code == 200, edited.text
    iid = edited.json()["iid"]

    def titles(body: list[dict[str, Any]]) -> list[str]:
        return [mr["title"] for mr in body]

    listed = (await client.get("/api/day1/approvals", headers=admin)).json()
    assert any(KV_A in title for title in titles(listed))
    assert not any(
        KV_A in t for t in titles((await client.get("/api/day1/approvals", headers=viewer)).json())
    )
    audit = (await client.get("/api/day1/audit/merge-requests", headers=viewer)).json()
    assert not any(KV_A in title for title in titles(audit))
    one = await client.get(f"/api/day1/approvals/{iid}", headers=viewer)
    assert (one.status_code, one.json()["code"]) == (404, "NOT_FOUND")
    assert (await client.get(f"/api/day1/approvals/{iid}", headers=admin)).status_code == 200


# ── Delete: the only thing a KV cluster does differently ────────────────────


async def test_a_kv_clusters_delete_needs_its_name_and_says_its_vms_go(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    admin = auth(support.ALICE)
    for confirm in ({}, {"confirm": "ocp4-prod-kv-site1-az1"}):
        refused = await client.delete(f"{CLUSTERS}/{KV_A}", params=confirm, headers=admin)
        assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
        assert any("VM" in p for p in refused.json()["details"]["problems"])
    deleted = await client.delete(f"{CLUSTERS}/{KV_A}", params={"confirm": KV_A}, headers=admin)
    assert deleted.status_code == 200, deleted.text
    assert "tenants' VM workers it hosts are deleted with it" in deleted.json()["description"]


async def test_a_tenants_delete_needs_no_name(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    deleted = await client.delete(f"{CLUSTERS}/{LARK}", headers=auth(support.ALICE))
    assert deleted.status_code == 200, deleted.text
    assert "VM" not in deleted.json()["description"]


# ── Placement: a seed is never a tenant's MCE ────────────────────────────────


async def test_placement_never_offers_a_seed(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = (
        await client.get(
            "/api/day1/placement",
            params={"site": "site1", "env": "prod"},
            headers=auth(support.ALICE),
        )
    ).json()
    assert SEED not in {c["mce"] for c in body["candidates"]}
    assert PROD_MCE in {c["mce"] for c in body["candidates"]}


async def test_a_create_on_a_seed_is_refused_by_its_kind(context: Day1Context) -> None:
    assert context.placement is not None
    ref = ClusterRef("site1", SEED, "ocp4-prod-eck-site1-a")
    with pytest.raises(InvalidInputError, match="is a seed: it hosts KV clusters"):
        await context.placement.admit(ref, "mastertag: 4.18.22-x86_64\n", None, flavor="eck")
