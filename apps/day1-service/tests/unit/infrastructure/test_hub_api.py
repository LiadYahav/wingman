"""HttpHubApi against recorded-shape HyperShift and agent-install responses (MockTransport)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.status import Condition
from wingman_day1.infrastructure.hub_api import HttpHubApi, load_mce_tokens

TOKEN = "sha256~hub-token-never-shown-0001"
MCE = "ocp4-prod-mce-site1-a"

Handler = Callable[[httpx.Request], httpx.Response]

HOSTED_CLUSTER = {
    "metadata": {"name": "openshift-prod-herzi-site1", "namespace": "hcp-prod-herzi-site1"},
    "status": {
        "conditions": [
            {"type": "Available", "status": "True", "reason": "AsExpected", "message": ""},
            {"type": "Degraded", "status": "False"},
        ],
        "version": {"history": [{"version": "4.16.27"}, {"version": "4.16.20"}]},
    },
}
NODE_POOLS = {
    "items": [
        {
            "metadata": {"name": "zz-pool"},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 2,
                "conditions": [{"type": "Ready", "status": "False", "reason": "ScalingUp"}],
            },
        },
        {"metadata": {"name": "aa-pool"}, "spec": {}, "status": {"replicas": 1}},
        {"metadata": {"name": "mm-pool"}},
    ]
}


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def make(
    handler: Handler,
    *,
    domain: str = "hubs.example.invalid",
    metrics: WingmanMetrics | None = None,
) -> tuple[HttpHubApi, Recorder]:
    recorder = Recorder(handler)
    api = HttpHubApi(
        tokens={MCE: TOKEN, "ocp4-prep-mce-site1-a": "other-token"},
        domain=domain,
        verify=False,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(recorder),
        timer=iter(range(1000)).__next__,
    )
    return api, recorder


async def test_hosted_cluster_url_token_and_parsing() -> None:
    api, rec = make(reply(200, HOSTED_CLUSTER))
    hc = await api.hosted_cluster(
        MCE, namespace="hcp-prod-herzi-site1", name="openshift-prod-herzi-site1"
    )
    request = rec.requests[0]
    assert str(request.url) == (
        "https://api.ocp4-prod-mce-site1-a.hubs.example.invalid:6443"
        "/apis/hypershift.openshift.io/v1beta1/namespaces/hcp-prod-herzi-site1"
        "/hostedclusters/openshift-prod-herzi-site1"
    )
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert hc.name == "openshift-prod-herzi-site1"
    assert hc.namespace == "hcp-prod-herzi-site1"
    assert hc.phase is None
    assert hc.version == "4.16.27"
    assert hc.conditions == (
        Condition("Available", "True", "AsExpected", ""),
        Condition("Degraded", "False", "", ""),
    )
    await api.aclose()


async def test_hosted_cluster_with_phase_and_no_status() -> None:
    api, _ = make(reply(200, {"status": {"phase": "Completed", "version": {}}}))
    hc = await api.hosted_cluster(MCE, namespace="hcp-x", name="openshift-x")
    assert (hc.phase, hc.version, hc.conditions) == ("Completed", None, ())
    bare, _ = make(reply(200, {"metadata": {"name": "openshift-x"}}))
    hc = await bare.hosted_cluster(MCE, namespace="hcp-x", name="openshift-x")
    assert (hc.phase, hc.version, hc.conditions) == (None, None, ())


async def test_empty_domain_reaches_api_dot_mce() -> None:
    api, rec = make(reply(200, {"items": []}), domain="")
    assert await api.node_pools(MCE, namespace="hcp-x") == []
    assert rec.requests[0].url.host == f"api.{MCE}"
    assert rec.requests[0].url.port == 6443


async def test_node_pools_are_sorted_with_replica_defaults() -> None:
    api, rec = make(reply(200, NODE_POOLS))
    pools = await api.node_pools(MCE, namespace="hcp-prod-herzi-site1")
    assert rec.requests[0].url.path == (
        "/apis/hypershift.openshift.io/v1beta1/namespaces/hcp-prod-herzi-site1/nodepools"
    )
    assert [(p.name, p.desired_replicas, p.current_replicas) for p in pools] == [
        ("aa-pool", 1, 1),
        ("mm-pool", 0, 0),
        ("zz-pool", 3, 2),
    ]
    assert pools[2].conditions == (Condition("Ready", "False", "ScalingUp", ""),)


@pytest.mark.parametrize(
    ("namespace", "path"),
    [
        ("inventory", "/apis/agent-install.openshift.io/v1beta1/namespaces/inventory/infraenvs"),
        (None, "/apis/agent-install.openshift.io/v1beta1/infraenvs"),
        ("", "/apis/agent-install.openshift.io/v1beta1/infraenvs"),
    ],
)
async def test_infra_envs_namespaced_or_hub_wide(namespace: str | None, path: str) -> None:
    body = {"items": [{"metadata": {"name": "dell-b"}}, {"metadata": {"name": "dell-a"}}]}
    api, rec = make(reply(200, body))
    assert await api.infra_envs(MCE, namespace=namespace) == ["dell-a", "dell-b"]
    assert rec.requests[0].url.path == path


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, HubDeniedError),
        (403, HubDeniedError),
        (404, HubObjectNotFoundError),
        (400, HubUnavailableError),
        (500, HubUnavailableError),
        (503, HubUnavailableError),
    ],
)
async def test_status_codes_map_to_domain_errors(status: int, error: type[Exception]) -> None:
    api, _ = make(reply(status, {"message": f"leaked {TOKEN}?"}))
    with pytest.raises(error) as caught:
        await api.hosted_cluster(MCE, namespace="hcp-x", name="openshift-x")
    assert TOKEN not in str(caught.value)
    assert MCE in str(caught.value)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout])
async def test_transport_failures_are_unavailable(exc: type[httpx.TransportError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    api, _ = make(fail)
    with pytest.raises(HubUnavailableError) as caught:
        await api.infra_envs(MCE, namespace=None)
    assert TOKEN not in str(caught.value)
    assert exc.__name__ in str(caught.value)


async def test_a_body_that_is_not_json_is_unavailable() -> None:
    api, _ = make(lambda _r: httpx.Response(200, content=b"<html>proxy</html>"))
    with pytest.raises(HubUnavailableError, match="not JSON"):
        await api.node_pools(MCE, namespace="hcp-x")


@pytest.mark.parametrize(
    ("call", "body"),
    [
        ("hosted_cluster", {"status": {"conditions": [{"status": "True"}]}}),
        ("hosted_cluster", {"status": "broken"}),
        ("hosted_cluster", {"status": {"conditions": "nope"}}),
        ("hosted_cluster", {"status": {"version": {"history": "nope"}}}),
        ("node_pools", {"items": [{"metadata": {"name": "p"}, "spec": {"replicas": -1}}]}),
        ("node_pools", {"items": [{"metadata": {"name": "p"}, "status": {"replicas": "2"}}]}),
        ("node_pools", {"items": [{"metadata": {"name": "p"}, "spec": {"replicas": True}}]}),
        ("node_pools", {"items": "nope"}),
        ("node_pools", {"items": [{"metadata": {}}]}),
        ("infra_envs", {"items": [{"metadata": {"name": ""}}]}),
        ("infra_envs", {"items": [{}]}),
        ("infra_envs", ["not", "an", "object"]),
    ],
)
async def test_malformed_objects_are_unavailable(call: str, body: object) -> None:
    api, _ = make(reply(200, body))
    with pytest.raises(HubUnavailableError, match="malformed"):
        if call == "hosted_cluster":
            await api.hosted_cluster(MCE, namespace="hcp-x", name="openshift-x")
        elif call == "node_pools":
            await api.node_pools(MCE, namespace="hcp-x")
        else:
            await api.infra_envs(MCE, namespace="inventory")


async def test_an_mce_without_a_token_is_not_configured_and_lists_the_known_ones() -> None:
    api, rec = make(reply(200, {}))
    with pytest.raises(HubNotConfiguredError) as caught:
        await api.infra_envs("ocp4-test-mce-site9-a", namespace=None)
    message = str(caught.value)
    assert "ocp4-prep-mce-site1-a, ocp4-prod-mce-site1-a" in message
    assert TOKEN not in message
    assert "other-token" not in message
    assert rec.requests == []


async def test_no_tokens_at_all_says_none() -> None:
    api = HttpHubApi(tokens={}, domain="d.example.invalid")
    with pytest.raises(HubNotConfiguredError, match=r"\(none\)"):
        await api.infra_envs(MCE, namespace=None)


async def test_an_mce_key_that_is_not_a_dns_label_has_no_hub_address() -> None:
    api = HttpHubApi(
        tokens={"bad.host/evil": TOKEN},
        domain="d.example.invalid",
        transport=httpx.MockTransport(reply(200, {})),
    )
    with pytest.raises(HubNotConfiguredError, match="not a DNS label"):
        await api.infra_envs("bad.host/evil", namespace=None)


@pytest.mark.parametrize(
    ("namespace", "name"),
    [("hcp-x/../kube-system", "openshift-x"), ("hcp-x", "a?b=c"), ("HCP", "openshift-x")],
)
async def test_names_that_cannot_exist_never_reach_the_hub(namespace: str, name: str) -> None:
    api, rec = make(reply(200, HOSTED_CLUSTER))
    with pytest.raises(HubObjectNotFoundError, match="not a DNS label"):
        await api.hosted_cluster(MCE, namespace=namespace, name=name)
    with pytest.raises(HubObjectNotFoundError):
        await api.infra_envs(MCE, namespace="bad/ns")
    assert rec.requests == []


async def test_one_client_per_mce_is_reused_and_closed() -> None:
    api, rec = make(reply(200, {"items": []}))
    await api.node_pools(MCE, namespace="hcp-x")
    await api.node_pools(MCE, namespace="hcp-y")
    await api.node_pools("ocp4-prep-mce-site1-a", namespace="hcp-y")
    assert [r.headers["authorization"] for r in rec.requests] == [
        f"Bearer {TOKEN}",
        f"Bearer {TOKEN}",
        "Bearer other-token",
    ]
    assert len(api._clients) == 2
    await api.aclose()
    assert api._clients == {}


def sample(metrics: WingmanMetrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels)


async def test_calls_are_counted_and_timed_by_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), service="day1", version="t", commit="t")
    api, _ = make(reply(200, HOSTED_CLUSTER), metrics=metrics)
    await api.hosted_cluster(MCE, namespace="hcp-x", name="openshift-x")
    missing, _ = make(reply(404, {}), metrics=metrics)
    with pytest.raises(HubObjectNotFoundError):
        await missing.node_pools(MCE, namespace="hcp-x")
    with pytest.raises(HubNotConfiguredError):
        await missing.infra_envs("ocp4-test-mce-site9-a", namespace=None)
    base = {"dependency": "kubernetes"}
    total = "wingman_dependency_requests_total"
    assert sample(metrics, total, **base, operation="get_hosted_cluster", outcome="ok") == 1
    assert sample(metrics, total, **base, operation="list_node_pools", outcome="not_found") == 1
    assert sample(metrics, total, **base, operation="list_infra_envs", outcome="rejected") == 1
    seconds = "wingman_dependency_request_duration_seconds_sum"
    assert sample(metrics, seconds, **base, operation="get_hosted_cluster") == 1.0


def test_load_mce_tokens_reads_the_legacy_file(tmp_path: Path) -> None:
    path = tmp_path / "tokens"
    path.write_text(f"{MCE}: {TOKEN}\nocp4-prep-mce-site1-a: '  spaced  '\n", encoding="utf-8")
    assert load_mce_tokens(path) == {MCE: TOKEN, "ocp4-prep-mce-site1-a": "spaced"}
    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    assert load_mce_tokens(empty) == {}


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("- just\n- a list\n", "mapping"),
        ("1: tok\n", "every key"),
        (f"{MCE}: ''\n", MCE),
        (f"{MCE}: 42\n", MCE),
        (f'{MCE}: "line1\\nline2"\n', "more than one line"),
        (f'{MCE}: "tok\\r"\n', "more than one line"),
    ],
)
def test_load_mce_tokens_refuses_bad_files_without_echoing_tokens(
    tmp_path: Path, content: str, match: str
) -> None:
    path = tmp_path / "tokens"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=match) as caught:
        load_mce_tokens(path)
    message = str(caught.value).replace(str(path), "<path>")
    assert "line1" not in message
    assert "42" not in message


def test_a_ca_bundle_path_is_loaded_at_construction(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        HttpHubApi(tokens={}, domain="d.example.invalid", verify=str(tmp_path / "missing.pem"))
