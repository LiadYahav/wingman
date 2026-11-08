"""The flavor rules over HTTP: every broken rule is in the 422 problem's ``details.problems``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.users import User

Auth = Callable[[User], dict[str, str]]


def flavor(name: str = "agent-flavor", **day1: Any) -> dict[str, Any]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": name, "version": "1.0.0"},
        "spec": {"day1": day1, "day2": {"addons": []}},
    }


def with_pools(support: Any, *configs: list[dict[str, Any]]) -> dict[str, Any]:
    body = support.create_body()
    variables = body["variables"]
    variables["nodepools"] = [
        {"infra_env": f"dell-r660-site1-pool{i}", "replicas": 2, "configs": c}
        for i, c in enumerate(configs)
    ]
    return body


async def test_the_preview_shows_the_expanded_network_config(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = with_pools(
        support, [{"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}]
    )
    response = await client.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    assert "    configs:\n      - name: nm-conf-prod-falcon-site1-dell\n" in response.json()["yaml"]


async def test_a_create_with_configs_that_do_not_resolve_is_a_422_listing_each(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = with_pools(
        support, [{"name": "nm-conf"}], [{"name": "nope"}, {"name": "nic-ring-buffer"}]
    )
    response = await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert problem["detail"] == "the cluster's inputs are not acceptable"
    assert problem["details"]["problems"] == [
        "nodepools[0].configs[0]: nm-conf needs a hardware type, one of cisco, dell, dell-data",
        "nodepools[1].configs[0]: no machine config 'nope' in mc-files/",
    ]


async def test_a_flavor_with_configs_that_do_not_resolve_is_a_422(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = flavor(values={"nodepools": [{"configs": [{"name": "nm-conf", "hardware": "hp"}]}]})
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    assert response.json()["detail"] == "spec 'agent-flavor' cannot be saved"
    assert response.json()["details"]["problems"] == [
        "nodepools[0].configs[0]: no hardware type 'hp', one of cisco, dell, dell-data"
    ]
    fixed = flavor(values={"nodepools": [{"configs": [{"name": "nm-conf", "hardware": "dell"}]}]})
    created = await client.post("/api/day1/specs", json=fixed, headers=auth(support.ALICE))
    assert created.status_code == 201, created.text


async def test_owners_must_be_numbers_on_create_and_on_flavor_save(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body()
    body["variables"]["owner_anaf"] = "5 6"
    response = await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    assert response.json()["details"]["problems"] == [
        "owner_anaf: must be a number of 1 to 10 digits, sent as a string like \"1234\" (got '5 6')"
    ]
    spec = flavor(values={"owner_mador": 7})
    saved = await client.post("/api/day1/specs", json=spec, headers=auth(support.ALICE))
    assert saved.status_code == 422
    assert saved.json()["details"]["problems"][0].startswith("owner_mador: must be a number")
