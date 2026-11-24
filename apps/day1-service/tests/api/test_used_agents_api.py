"""herzi's used Agents over HTTP: placement leaves them out, Inventory shows them apart.

site1-a's free Dell Agents are ``s1`` (fresh), ``s2`` (``redbull.io/ever-installed``,
herzi's label) and ``s3`` (``example.com/used``); ``s4`` carries herzi's label
but an AgentMachine holds it. server-scan has a healthy spare row for each.
herzi paused the Dell InfraEnv, and its block marker is set.
The fixtures' cluster files on site1-a (heron and lark, two nodepools each)
exclude no label.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.herzi_marks import HerziMarks
from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    INFRA_ENV_LABEL,
    AgentObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.used_agents import HERZI_LABEL
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FREE_AGENT, FakeHubApi
from wingman_day1.integrations.server_scan.infrastructure.fake import FakeServerInventory

Auth = Callable[[User], dict[str, str]]
A = "ocp4-prod-mce-site1-a"
DELL = "dell-r660-site1-128c-1024gb-5tb"
OTHER = "example.com/used"
SERVER_SCAN = "http://server-scan-api.inventory.svc:8000"
BLOCKED = datetime(2026, 11, 23, 10, 5, tzinfo=UTC)
"""herzi's block marker on the Dell InfraEnv, which it also paused."""


def agent(server: str, *labels: str) -> AgentObservation:
    return AgentObservation(
        name=f"agent-{server}",
        labels={INFRA_ENV_LABEL: DELL, BMH_LABEL: server, **dict.fromkeys(labels, "true")},
        approved=True,
        conditions=FREE_AGENT,
    )


def hub() -> FakeHubApi:
    return FakeHubApi(
        nodes={A: (NodeObservation("w-0", True, False, False, 250),)},
        pods={A: {"w-0": 10}},
        infra_envs={A: {"inventory": [DELL]}},
        agents={
            (A, "inventory"): [
                agent("s1"),
                agent("s2", HERZI_LABEL),
                agent("s3", OTHER),
                agent("s4", HERZI_LABEL, AGENT_MACHINE_REF_LABEL),
            ]
        },
        herzi={A: {DELL: HerziMarks(paused=True, blocked_until=BLOCKED)}},
    )


def rows() -> list[ServerRow]:
    return [
        ServerRow(
            id=f"srv_{name}",
            name=name,
            state="INSTALLED_TO_INVENTORY",
            health="HEALTHY",
            site="site1",
            mce=A,
        )
        for name in ("s1", "s2", "s3", "s4")
    ]


def app_of(
    support: Any, gitlab: InMemoryGitLab, clock: Any, *, live: bool = True, **settings: object
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub() if live else None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=FakeServerInventory(rows()),
        SERVER_SCAN_URL=SERVER_SCAN,
        **settings,
    )


async def serve(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


@pytest.fixture
async def day1(
    support: Any, gitlab: InMemoryGitLab, clock: Any
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in serve(app_of(support, gitlab, clock)):
        yield client


async def dell_on_a(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(
        "/api/day1/placement",
        params={"site": "site1", "env": "prod", "version": "4.18.56", "need": f"{DELL}:2"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    candidate = next(c for c in response.json()["candidates"] if c["mce"] == A)
    return candidate["node_types"][0]


# ── Placement ────────────────────────────────────────────────────────────────


async def test_placement_counts_herzis_used_agents_as_no_free_server(
    day1: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    dell = await dell_on_a(day1, auth(support.ALICE))
    assert (dell["free_agents"], dell["healthy"], dell["used"]) == (2, 2, 1)
    assert dell["detail"] == (
        f"{DELL}: 2 healthy free of 2 needed; 1 used, left out (herzi removes it)"
    )


async def test_with_the_setting_its_keys_mark_the_used_agents_not_herzis(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock, DAY1_EXCLUDED_AGENT_LABELS=OTHER)
    async for client in serve(app):
        dell = await dell_on_a(client, auth(support.ALICE))
        assert (dell["free_agents"], dell["used"]) == (2, 1), "s2 counts, s3 does not"


# ── Inventory Management ─────────────────────────────────────────────────────


async def inventory(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get("/api/day1/inventory", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_inventory_shows_the_used_agents_apart_and_never_as_available(
    day1: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await inventory(day1, auth(support.ALICE))
    assert body["used_labels"] == {"keys": [HERZI_LABEL], "source": "herzi"}
    site1_a = next(m for m in body["mces"] if m["mce"] == A)
    assert (site1_a["used"], site1_a["used_error"]) == (1, None)
    assert site1_a["available"] == 3, "s1, s3 and s4 (held: not herzi's to remove yet)"
    pools = {p["infra_env"]: p for p in site1_a["pools"]}
    assert (pools[DELL]["used"], pools[DELL]["total"]) == (["s2"], 0), "by its InfraEnv label"
    assert (pools[None]["available"], pools[None]["used"]) == (3, []), "no labels name s1, s3, s4"


async def test_inventory_lists_the_nodepools_that_do_not_exclude_the_label(
    day1: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await inventory(day1, auth(support.ALICE))
    site1_a = next(m for m in body["mces"] if m["mce"] == A)
    found = {(u["cluster"], u["nodepool"]) for u in site1_a["unguarded"]}
    assert found == {
        ("ocp4-prod-heron-site1", "prod-heron-site1-hp-gen11-site1-64c"),
        ("ocp4-prod-heron-site1", "prod-heron-site1-dell-b"),
        ("ocp4-prod-lark-site1", "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"),
        ("ocp4-prod-lark-site1", "prod-lark-site1-dell-r760-site1-64c-512gb-20tb"),
    }
    assert all(u["missing"] == [HERZI_LABEL] and not u["replace"] for u in site1_a["unguarded"])


async def test_with_the_setting_inventory_names_its_keys(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock, DAY1_EXCLUDED_AGENT_LABELS=OTHER)
    async for client in serve(app):
        body = await inventory(client, auth(support.ALICE))
        assert body["used_labels"] == {"keys": [OTHER], "source": "setting"}
        site1_a = next(m for m in body["mces"] if m["mce"] == A)
        dell = next(p for p in site1_a["pools"] if p["infra_env"] == DELL)
        assert dell["used"] == ["s3"]


async def test_without_live_status_the_used_agents_are_unknown(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async for client in serve(app_of(support, gitlab, clock, live=False)):
        body = await inventory(client, auth(support.ALICE))
        site1_a = next(m for m in body["mces"] if m["mce"] == A)
        assert (site1_a["used"], site1_a["used_error"], site1_a["available"]) == (None, None, 4)
        assert site1_a["unguarded"], "the cluster files are read without live status"


async def test_a_pool_carries_herzis_marks_on_its_infraenv(
    day1: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await inventory(day1, auth(support.ALICE))
    site1_a = next(m for m in body["mces"] if m["mce"] == A)
    dell = next(p for p in site1_a["pools"] if p["infra_env"] == DELL)
    assert dell["herzi"] == {
        "ignored": False,
        "paused": True,
        "blocked_until": "2026-11-23T10:05:00+00:00",
        "no_hardware_since": None,
    }
    other = next(p for p in site1_a["pools"] if p["infra_env"] is None)
    assert other["herzi"]["paused"] is False, "the row of servers no pool names has no InfraEnv"
