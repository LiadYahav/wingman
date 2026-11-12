"""HttpHubApi's nodes and pods per node (placement's free pods, ADR-0050), on MockTransport.

The shapes are the API server's: a ``v1`` NodeList, and a pod list asked for
as a ``meta.k8s.io/v1`` Table (``kubectl get pods -A -o wide`` asks the same),
whose priority-1 ``Node`` column is served to every client.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import HubDeniedError, HubObjectNotFoundError, HubUnavailableError
from wingman_day1.domain.machines import BMH_LABEL, INFRA_ENV_LABEL
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.infrastructure.hub_api import (
    MAX_PAGES,
    NON_TERMINAL_PODS,
    PAGE_SIZE,
    TABLE,
    HttpHubApi,
    node_from,
    pod_quantity,
    pods_per_node_from,
)

TOKEN = "sha256~hub-token-never-shown-0002"
MCE = "ocp4-prod-mce-site1-a"
Handler = Callable[[httpx.Request], httpx.Response]

POD_COLUMNS = [
    {"name": name, "type": "string", "format": fmt, "description": "", "priority": priority}
    for name, fmt, priority in (
        ("Name", "name", 0),
        ("Ready", "", 0),
        ("Status", "", 0),
        ("Restarts", "", 0),
        ("Age", "", 0),
        ("IP", "", 1),
        ("Node", "", 1),
        ("Nominated Node", "", 1),
        ("Readiness Gates", "", 1),
    )
]


def node(
    name: str,
    *,
    roles: tuple[str, ...] = ("worker",),
    ready: str = "True",
    unschedulable: bool | None = None,
    pods: object = "250",
) -> dict[str, object]:
    """A Node as the API server serves it, trimmed of what nothing reads."""
    spec: dict[str, object] = {"podCIDR": "10.128.0.0/23"}
    if unschedulable is not None:
        spec["unschedulable"] = unschedulable
    return {
        "metadata": {
            "name": name,
            "labels": {
                "kubernetes.io/hostname": name,
                **{f"node-role.kubernetes.io/{role}": "" for role in roles},
            },
        },
        "spec": spec,
        "status": {
            "allocatable": {"cpu": "63500m", "memory": "500Gi", "pods": pods},
            "capacity": {"cpu": "64", "memory": "512Gi", "pods": pods},
            "conditions": [
                {
                    "type": "MemoryPressure",
                    "status": "False",
                    "reason": "KubeletHasSufficientMemory",
                },
                {"type": "Ready", "status": ready, "reason": "KubeletReady"},
            ],
            "images": [{"names": ["quay.io/openshift/x@sha256:0"], "sizeBytes": 1}],
        },
    }


def pod_table(*nodes: str, continue_token: str = "") -> dict[str, object]:
    """A pod list as a Table, one row per pod on ``nodes`` (``<none>``: not bound yet)."""
    rows: list[dict[str, object]] = [
        {
            "cells": [f"pod-{i}", "1/1", "Running", "0", "5d", "10.128.0.9", n, "<none>", "<none>"],
            **({"object": None} if i % 2 else {}),
        }
        for i, n in enumerate(nodes)
    ]
    return {
        "kind": "Table",
        "apiVersion": "meta.k8s.io/v1",
        "metadata": {"resourceVersion": "4711", "continue": continue_token},
        "columnDefinitions": POD_COLUMNS,
        "rows": rows,
    }


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make(handler: Handler, *, metrics: WingmanMetrics | None = None) -> tuple[HttpHubApi, Recorder]:
    recorder = Recorder(handler)
    ticks: Iterator[int] = iter(range(10_000))
    api = HttpHubApi(
        tokens={MCE: TOKEN},
        domain="hubs.example.invalid",
        verify=False,
        metrics=metrics,
        transport=httpx.MockTransport(recorder),
        timer=ticks.__next__,
    )
    return api, recorder


def pages(*bodies: object) -> Handler:
    replies = iter(bodies)
    return lambda _request: httpx.Response(200, json=next(replies))


async def test_nodes_are_read_whole_and_classified() -> None:
    api, recorder = make(
        pages(
            {
                "kind": "NodeList",
                "metadata": {"continue": ""},
                "items": [
                    node("worker-1"),
                    node("master-0", roles=("master", "control-plane")),
                    node("compact-0", roles=("master", "worker")),
                    node("worker-0", ready="Unknown"),
                    node("worker-2", unschedulable=True, pods="1k"),
                    node("infra-0", roles=("infra",), pods=None),
                ],
            }
        )
    )
    nodes = await api.nodes(MCE)
    assert [n.name for n in nodes] == [
        "compact-0",
        "infra-0",
        "master-0",
        "worker-0",
        "worker-1",
        "worker-2",
    ]
    by_name = {n.name: n for n in nodes}
    assert by_name["worker-1"] == NodeObservation("worker-1", True, False, False, 250)
    assert by_name["master-0"].control_plane
    assert by_name["compact-0"].control_plane, "a master that is also a worker is control plane"
    assert not by_name["worker-0"].ready
    assert by_name["worker-2"] == NodeObservation("worker-2", True, True, False, 1000)
    assert by_name["infra-0"].allocatable_pods == 0
    (request,) = recorder.requests
    assert request.url.path == "/api/v1/nodes"
    assert request.url.params["limit"] == str(PAGE_SIZE)
    assert "continue" not in request.url.params
    assert request.headers["accept"] == "application/json"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


async def test_pods_are_table_rows_of_the_non_terminal_ones_counted_per_node() -> None:
    api, recorder = make(
        pages(
            pod_table("worker-1", "worker-1", "<none>", "master-0", continue_token="page-2"),
            pod_table("worker-1", "worker-2", "", continue_token="page-3"),
            pod_table("worker-2"),
        )
    )
    assert await api.pods_per_node(MCE) == {"worker-1": 3, "master-0": 1, "worker-2": 2}
    first, second, third = recorder.requests
    for request in recorder.requests:
        assert request.url.path == "/api/v1/pods"
        assert request.headers["accept"] == TABLE
        assert request.url.params["fieldSelector"] == NON_TERMINAL_PODS
        assert request.url.params["includeObject"] == "None"
        assert request.url.params["limit"] == str(PAGE_SIZE)
    assert "continue" not in first.url.params
    assert second.url.params["continue"] == "page-2"
    assert third.url.params["continue"] == "page-3"


async def test_every_page_is_counted_as_one_call() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    api, _ = make(pages(pod_table("a", continue_token="2"), pod_table("b")), metrics=metrics)
    await api.pods_per_node(MCE)
    labels = {"dependency": "kubernetes", "operation": "list_pods", "outcome": "ok"}
    assert metrics.registry.get_sample_value("wingman_dependency_requests_total", labels) == 2


async def test_a_list_that_never_stops_paging_is_refused() -> None:
    calls = 0

    def forever(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=pod_table("a", continue_token=f"page-{calls}"))

    api, _ = make(forever)
    with pytest.raises(HubUnavailableError, match="still paging"):
        await api.pods_per_node(MCE)
    assert calls == MAX_PAGES


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ({"kind": "PodList", "items": []}, "expected a Table"),
        ({**pod_table("a"), "columnDefinitions": POD_COLUMNS[:5]}, "no Node column"),
        ({**pod_table("a"), "rows": [{"cells": ["short"]}]}, "no Node cell"),
        ({**pod_table("a"), "rows": "x"}, "not a list"),
        ({**pod_table("a"), "metadata": {"continue": 7}}, "continue"),
    ],
)
async def test_anything_but_a_pod_table_is_malformed(body: object, match: str) -> None:
    api, _ = make(pages(body))
    with pytest.raises(HubUnavailableError, match=match):
        await api.pods_per_node(MCE)


async def test_a_node_with_a_bad_pod_quantity_is_malformed() -> None:
    api, _ = make(pages({"items": [node("w", pods="250Mi")]}))
    with pytest.raises(HubUnavailableError, match="not a whole number"):
        await api.nodes(MCE)


async def test_a_token_without_the_grant_names_the_path_and_never_the_token() -> None:
    api, _ = make(lambda _r: httpx.Response(403, json={"kind": "Status", "code": 403}))
    with pytest.raises(HubDeniedError, match="/api/v1/nodes") as caught:
        await api.nodes(MCE)
    assert TOKEN not in str(caught.value)
    with pytest.raises(HubDeniedError, match="/api/v1/pods"):
        await api.pods_per_node(MCE)


async def test_a_hub_that_does_not_serve_the_list_is_unavailable() -> None:
    api, _ = make(lambda _r: httpx.Response(404, json={}))
    with pytest.raises(HubUnavailableError, match="does not serve"):
        await api.nodes(MCE)


@pytest.mark.parametrize(
    ("value", "pods"), [("250", 250), (" 110 ", 110), (500, 500), ("1k", 1000), (None, 0)]
)
def test_pod_quantities(value: object, pods: int) -> None:
    assert pod_quantity(value) == pods


@pytest.mark.parametrize("value", ["", "2.5", "-1", "250Mi", True, -3, 2.0])
def test_pod_quantities_that_are_not_whole_numbers(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        pod_quantity(value)


def test_parsers_on_their_own() -> None:
    assert node_from(node("w", ready="False")).ready is False
    assert pods_per_node_from(pod_table()) == {}
    assert pods_per_node_from({**pod_table(), "rows": None}) == {}


@pytest.mark.parametrize(
    ("effects", "tainted"),
    [
        (["NoSchedule"], True),
        (["NoExecute"], True),
        (["PreferNoSchedule"], False),
        (["PreferNoSchedule", "NoSchedule"], True),
        ([], False),
    ],
)
def test_a_node_is_tainted_by_a_no_schedule_or_no_execute_taint(
    effects: list[str], tainted: bool
) -> None:
    raw = node("infra-0", roles=("infra",))
    spec = raw["spec"]
    assert isinstance(spec, dict)
    spec["taints"] = [{"key": f"k{i}", "effect": e} for i, e in enumerate(effects)]
    parsed = node_from(raw)
    assert (parsed.infra, parsed.tainted, parsed.control_plane) == (True, tainted, False)


def test_taints_that_are_not_a_list_are_malformed() -> None:
    raw = node("w")
    spec = raw["spec"]
    assert isinstance(spec, dict)
    spec["taints"] = "NoSchedule"
    with pytest.raises(TypeError):
        node_from(raw)


def agent_object(name: str, infra_env: str) -> dict[str, object]:
    return {
        "metadata": {
            "name": name,
            "namespace": "inventory",
            "labels": {INFRA_ENV_LABEL: infra_env, BMH_LABEL: name},
        },
        "spec": {"approved": True},
        "status": {"conditions": [{"type": "Bound", "status": "False"}]},
    }


async def test_agents_of_the_needed_infra_envs_are_listed_by_label_across_the_hub() -> None:
    api, recorder = make(
        pages(
            {"items": [agent_object("b-1", "hp")], "metadata": {"continue": "2"}},
            {"items": [agent_object("a-1", "dell")], "metadata": {"continue": ""}},
        )
    )
    agents = await api.infra_env_agents(MCE, infra_envs=["hp", "dell", "hp"], namespace=None)
    assert [(a.name, a.infra_env, a.approved) for a in agents] == [
        ("a-1", "dell", True),
        ("b-1", "hp", True),
    ]
    first, second = recorder.requests
    assert first.url.path == "/apis/agent-install.openshift.io/v1beta1/agents"
    assert first.url.params["labelSelector"] == f"{INFRA_ENV_LABEL} in (dell,hp)"
    assert first.url.params["limit"] == str(PAGE_SIZE)
    assert second.url.params["continue"] == "2"


async def test_agents_are_listed_in_the_infraenv_namespace_when_it_is_set() -> None:
    api, recorder = make(pages({"items": []}))
    assert await api.infra_env_agents(MCE, infra_envs=["dell"], namespace="inventory") == []
    (request,) = recorder.requests
    assert (
        request.url.path == "/apis/agent-install.openshift.io/v1beta1/namespaces/inventory/agents"
    )


async def test_no_needed_type_reads_nothing_and_a_bad_name_never_reaches_the_hub() -> None:
    api, recorder = make(pages())
    assert await api.infra_env_agents(MCE, infra_envs=[], namespace=None) == []
    with pytest.raises(HubObjectNotFoundError):
        await api.infra_env_agents(MCE, infra_envs=["dell) or (x"], namespace=None)
    assert recorder.requests == []
