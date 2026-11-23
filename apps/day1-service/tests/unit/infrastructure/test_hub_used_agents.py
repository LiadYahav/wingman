"""The used Agents herzi removes, read from an MCE: the adapter, the fake and the cache.

One label-selected list per key (``<key>,!agentMachineRef``), so a hub sends
only the labelled Agents no AgentMachine holds, not its whole inventory.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.errors import HubObjectNotFoundError
from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    INFRA_ENV_LABEL,
    AgentObservation,
)
from wingman_day1.domain.used_agents import HERZI_LABEL
from wingman_day1.infrastructure.cached_hub import CachedHubApi
from wingman_day1.infrastructure.fake_hub import FREE_AGENT, FakeHubApi
from wingman_day1.infrastructure.hub_api import PAGE_SIZE, HttpHubApi

MCE = "ocp4-prod-mce-site1-a"
OTHER = "example.com/used"
Handler = Callable[[httpx.Request], httpx.Response]


def agent_object(name: str, *labels: str) -> dict[str, object]:
    return {
        "metadata": {
            "name": name,
            "labels": {INFRA_ENV_LABEL: "dell", BMH_LABEL: name, **dict.fromkeys(labels, "true")},
        },
        "spec": {"approved": True},
        "status": {"conditions": [{"type": "Bound", "status": "False"}]},
    }


def make(*bodies: object) -> tuple[HttpHubApi, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    replies = iter(bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=next(replies))

    api = HttpHubApi(
        tokens={MCE: "sha256~hub-token-never-shown-0003"},
        domain="hubs.example.invalid",
        verify=False,
        transport=httpx.MockTransport(handler),
    )
    return api, requests


async def test_each_key_is_one_label_selected_list_of_agents_no_agent_machine_holds() -> None:
    api, requests = make(
        {"items": [agent_object("s2", HERZI_LABEL)], "metadata": {"continue": "2"}},
        {"items": [agent_object("s1", HERZI_LABEL, OTHER)]},
        {"items": [agent_object("s1", HERZI_LABEL, OTHER), agent_object("s3", OTHER)]},
    )
    found = await api.used_agents(MCE, labels=[HERZI_LABEL, OTHER], namespace=None)
    assert [agent.name for agent in found] == ["s1", "s2", "s3"], "each Agent once, by name"
    first, second, third = requests
    assert first.url.path == "/apis/agent-install.openshift.io/v1beta1/agents"
    assert first.url.params["labelSelector"] == f"{HERZI_LABEL},!{AGENT_MACHINE_REF_LABEL}"
    assert first.url.params["limit"] == str(PAGE_SIZE)
    assert second.url.params["continue"] == "2"
    assert third.url.params["labelSelector"] == f"{OTHER},!{AGENT_MACHINE_REF_LABEL}"


async def test_used_agents_are_listed_in_the_infraenv_namespace_when_it_is_set() -> None:
    api, requests = make({"items": []})
    assert await api.used_agents(MCE, labels=[HERZI_LABEL], namespace="inventory") == []
    (request,) = requests
    assert request.url.path == (
        "/apis/agent-install.openshift.io/v1beta1/namespaces/inventory/agents"
    )


async def test_a_key_that_is_no_label_key_never_reaches_the_hub() -> None:
    api, requests = make()
    with pytest.raises(HubObjectNotFoundError, match="not a label key"):
        await api.used_agents(MCE, labels=["x,!y"], namespace=None)
    assert requests == []


def seeded(name: str, *labels: str) -> AgentObservation:
    return AgentObservation(
        name=name,
        labels={INFRA_ENV_LABEL: "dell", **dict.fromkeys(labels, "true")},
        approved=True,
        conditions=FREE_AGENT,
    )


async def test_the_fake_answers_with_the_labelled_agents_no_agent_machine_holds() -> None:
    hub = FakeHubApi(
        agents={
            (MCE, "inventory"): [
                seeded("used", HERZI_LABEL),
                seeded("held", HERZI_LABEL, AGENT_MACHINE_REF_LABEL),
                seeded("fresh"),
            ],
            (MCE, "elsewhere"): [seeded("other-ns", HERZI_LABEL)],
        }
    )
    every = await hub.used_agents(MCE, labels=[HERZI_LABEL], namespace=None)
    assert [a.name for a in every] == ["other-ns", "used"]
    here = await hub.used_agents(MCE, labels=[HERZI_LABEL], namespace="inventory")
    assert [a.name for a in here] == ["used"]


async def test_the_cache_keeps_one_read_per_mce_namespace_and_keys() -> None:
    inner = FakeHubApi(agents={(MCE, "inventory"): [seeded("used", HERZI_LABEL)]})
    calls: list[tuple[str, ...]] = []
    read = inner.used_agents

    async def counted(
        mce: str, *, labels: tuple[str, ...], namespace: str | None
    ) -> list[AgentObservation]:
        calls.append(tuple(labels))
        return await read(mce, labels=labels, namespace=namespace)

    inner.used_agents = counted  # type: ignore
    hub = CachedHubApi(inner, TtlCache(), ttl=30.0)
    for _ in range(3):
        assert len(await hub.used_agents(MCE, labels=(HERZI_LABEL,), namespace="inventory")) == 1
    await hub.used_agents(MCE, labels=(OTHER,), namespace="inventory")
    assert calls == [(HERZI_LABEL,), (OTHER,)]
