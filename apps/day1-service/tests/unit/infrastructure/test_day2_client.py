"""HttpDay2Addons against day2's addon list (MockTransport), and FakeDay2Addons."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.day2_client import HttpDay2Addons
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

TOKEN = "service-session-token-never-shown-0001"
CLUSTER = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-hawk-site1")

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpDay2Addons, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = HttpDay2Addons(
        base_url="http://wingman-day2.test:8002/",
        token=lambda: TOKEN,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return client, requests


def reply(status: int, body: object) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


async def test_installed_addons_are_read_with_the_service_token() -> None:
    body = {
        "cluster": CLUSTER.name,
        "mce": CLUSTER.mce,
        "installed": [
            {"team": "redbull", "name": "cluster-roles", "version": "2.0.0", "override_values": {}},
            {"team": "orca", "name": "metrics", "version": ""},
            {"team": "lynx", "name": "backup"},
        ],
    }
    client, requests = make(reply(200, body))
    assert await client.installed(CLUSTER) == [
        InstalledAddon("redbull", "cluster-roles", "2.0.0"),
        InstalledAddon("orca", "metrics", ""),
        InstalledAddon("lynx", "backup", ""),
    ]
    request = requests[0]
    assert request.url.path == "/api/day2/clusters/ocp4-prod-hawk-site1/addons"
    assert dict(request.url.params) == {"mce": CLUSTER.mce, "site": CLUSTER.site}
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.url.host == "wingman-day2.test"
    await client.aclose()


async def test_the_cluster_name_is_encoded_into_one_path_segment() -> None:
    client, requests = make(reply(200, {"installed": []}))
    await client.installed(ClusterRef("site1", "mce", "odd/../name?x"))
    assert requests[0].url.raw_path.startswith(b"/api/day2/clusters/odd%2F..%2Fname%3Fx/addons")


@pytest.mark.parametrize("status", [401, 403, 404, 500, 502])
async def test_any_non_200_is_unavailable_not_empty(status: int) -> None:
    client, _ = make(reply(status, {"detail": f"echo {TOKEN}"}))
    with pytest.raises(Day2UnavailableError, match=f"answered {status}") as caught:
        await client.installed(CLUSTER)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_unavailable(exc: type[httpx.TransportError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    client, _ = make(fail)
    with pytest.raises(Day2UnavailableError, match=exc.__name__) as caught:
        await client.installed(CLUSTER)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        ["not", "an", "object"],
        {"cluster": "x"},
        {"installed": "nope"},
        {"installed": ["nope"]},
        {"installed": [{"team": "redbull"}]},
        {"installed": [{"team": "", "name": "x"}]},
        {"installed": [{"team": "t", "name": "x", "version": 3}]},
    ],
)
async def test_malformed_bodies_are_unavailable(body: object) -> None:
    client, _ = make(reply(200, body))
    with pytest.raises(Day2UnavailableError, match="malformed"):
        await client.installed(CLUSTER)


async def test_a_body_that_is_not_json_is_unavailable() -> None:
    client, _ = make(lambda _r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(Day2UnavailableError, match="malformed"):
        await client.installed(CLUSTER)


async def test_calls_are_counted_by_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), service="day1", version="t", commit="t")
    ok, _ = make(reply(200, {"installed": []}), metrics=metrics)
    await ok.installed(CLUSTER)
    down, _ = make(reply(503, {}), metrics=metrics)
    with pytest.raises(Day2UnavailableError):
        await down.installed(CLUSTER)
    labels = {"dependency": "day2", "operation": "list_installed_addons"}
    total = "wingman_dependency_requests_total"
    assert metrics.registry.get_sample_value(total, {**labels, "outcome": "ok"}) == 1
    assert metrics.registry.get_sample_value(total, {**labels, "outcome": "unavailable"}) == 1


async def test_fake_day2_reports_seeded_addons_or_fails_like_day2_down() -> None:
    addon = InstalledAddon("redbull", "cluster-roles", "main")
    fake = FakeDay2Addons({CLUSTER.name: [addon]})
    assert await fake.installed(CLUSTER) == [addon]
    assert await fake.installed(ClusterRef("site1", "m", "other")) == []
    fake.unavailable = True
    with pytest.raises(Day2UnavailableError):
        await fake.installed(CLUSTER)
    assert await FakeDay2Addons().installed(CLUSTER) == []
