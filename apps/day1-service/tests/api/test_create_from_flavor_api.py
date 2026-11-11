"""Creating from a flavor over HTTP: suggested name, letter sequence, ratio (ADR-0040)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]

SUGGEST = "/api/day1/clusters/name-suggestion"
PROD = {"site": "site1", "mce": "ocp4-prod-mce-site1-a"}


def flavor(name: str, **day1: Any) -> dict[str, Any]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": name, "version": "1.0.0"},
        "spec": {"day1": day1, "day2": {"addons": []}},
    }


async def merged(support: Any, gitlab: InMemoryGitLab, document: dict[str, Any]) -> None:
    """A flavor on the specs repo's main branch, as if its MR were merged."""
    name = document["metadata"]["name"]
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file=f"specs/{name}.yaml",
        content=yaml.safe_dump(document),
    )


async def test_the_name_is_suggested_from_the_flavor_and_the_next_letter(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    await merged(support, gitlab, flavor("rcs"))
    viewer = auth(support.VIEWER)

    first = await client.get(SUGGEST, params={**PROD, "flavor": "rcs"}, headers=viewer)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "name": "ocp4-prod-rcs-site1-a",
        "env": "prod",
        "short_name": "rcs",
        "sequence": "a",
        "problems": [],
    }

    # An open create MR holds its name: the next suggestion is -b
    body = support.create_body("ocp4-prod-rcs-site1-a", spec_name="rcs")
    created = await client.post("/api/day1/clusters", json=body, headers=alice)
    assert created.status_code == 201, created.text
    second = await client.get(SUGGEST, params={**PROD, "flavor": "rcs"}, headers=viewer)
    assert second.json()["name"] == "ocp4-prod-rcs-site1-b"

    prep = {"site": "site2", "mce": "ocp4-prep-mce-site2-a", "flavor": "rcs"}
    other = await client.get(SUGGEST, params=prep, headers=viewer)
    assert other.json()["name"] == "ocp4-prep-rcs-site2-a"


async def test_no_suggestion_under_an_off_convention_mce_and_404_for_unknowns(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = auth(support.VIEWER)
    lab = {"site": "site1", "mce": "ocp4-mce-workflow-test", "flavor": "agent-standard"}
    off = (await client.get(SUGGEST, params=lab, headers=viewer)).json()
    assert off["name"] is None
    assert off["problems"][0].startswith("MCE 'ocp4-mce-workflow-test' does not follow")
    unknown = await client.get(SUGGEST, params={**PROD, "flavor": "nope"}, headers=viewer)
    assert unknown.status_code == 404
    no_mce = {"site": "site1", "mce": "ocp4-prod-mce-site1-z", "flavor": "agent-standard"}
    assert (await client.get(SUGGEST, params=no_mce, headers=viewer)).status_code == 404
    assert (await client.get(SUGGEST, params=PROD, headers=viewer)).status_code == 422


async def test_a_numeric_sequence_is_refused_for_a_new_cluster(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body("ocp4-prod-falcon-site1-01")
    response = await client.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert response.status_code == 422
    assert response.json()["details"]["problems"] == [
        "sequence '01' of cluster 'ocp4-prod-falcon-site1-01' must be one letter, a to z "
        "(ocp4-prod-falcon-site1-a): a number is not the convention"
    ]


async def test_a_flavor_ratio_must_fit_its_nodepools_and_sizes_the_create(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    three = {"nodepools": [{}, {}, {}]}
    # On main before the API first reads the specs repo (it reads once per commit)
    await merged(support, gitlab, flavor("zones", structure=three, nodepool_ratio=[1, 2, 1]))

    short = flavor("zones-short", structure=three, nodepool_ratio=[1, 2])
    refused = await client.post("/api/day1/specs", json=short, headers=alice)
    assert refused.status_code == 422
    assert refused.json()["details"]["problems"] == [
        "nodepool_ratio: 2 entries for 3 nodepools; give one per nodepool"
    ]
    fits = flavor("zones-new", structure=three, nodepool_ratio=[1, 2, 1])
    saved = await client.post("/api/day1/specs", json=fits, headers=alice)
    assert saved.status_code == 201, saved.text

    response = await client.get("/api/day1/specs/zones", headers=alice)
    assert response.status_code == 200, response.text
    read = response.json()
    assert read["spec"]["day1"]["nodepool_ratio"] == [1, 2, 1]

    body = support.create_body("ocp4-prod-zones-site1-a", spec_name="zones")
    pools = support.nodepools("zone-a", "zone-b", "zone-c")
    for pool, replicas in zip(pools, (2, 3, 2), strict=True):
        pool["replicas"] = replicas
    body["variables"]["nodepools"] = pools
    off = await client.post("/api/day1/clusters/preview", json=body, headers=alice)
    assert off.status_code == 422
    assert off.json()["details"]["problems"] == [
        "nodepools[1].replicas: the flavor zones sizes its nodepools 1:2:1, so the replicas "
        "must be 1, 2 and 1 times one size (e.g. 2, 4, 2); got 2, 3, 2"
    ]
    pools[1]["replicas"] = 4
    on = await client.post("/api/day1/clusters/preview", json=body, headers=alice)
    assert on.status_code == 200, on.text
    assert [line.strip() for line in on.json()["yaml"].splitlines() if "replicas" in line] == [
        "replicas: 2",
        "replicas: 4",
        "replicas: 2",
    ]
