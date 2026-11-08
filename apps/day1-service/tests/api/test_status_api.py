"""Live status routes: 501 when off, the legacy shapes, errors in the body, the SSE stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.types import Message

from wingman_core.domain.users import User
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi

Auth = Callable[[User], dict[str, str]]
MCE = "ocp4-prod-mce-site1-a"
HERZI = "ocp4-prod-herzi-site1"

STATUS_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"/api/day1/clusters/{HERZI}/status?mce={MCE}", None),
    ("GET", f"/api/day1/clusters/{HERZI}/status/stream?mce={MCE}", None),
    ("POST", "/api/day1/clusters/bulk-status", {"clusters": [{"name": HERZI, "mce": MCE}]}),
    ("GET", f"/api/day1/mces/{MCE}/infraenvs", None),
]


@pytest.fixture
def disabled(support: Any, gitlab: Any, identity: Any, clock: Any) -> FastAPI:
    return support.build_app(
        gitlab=gitlab, hub=None, identity=identity, day2=FakeDay2Addons(), clock=clock
    )


@pytest.mark.parametrize(("method", "path", "body"), STATUS_ROUTES)
async def test_every_status_route_is_501_when_status_is_off(
    disabled: FastAPI,
    auth: Auth,
    support: Any,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    transport = httpx.ASGITransport(app=disabled)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        response = await client.request(method, path, json=body, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert response.headers["content-type"] == "application/problem+json"


async def test_status_has_the_legacy_shape_and_names_the_hosted_cluster(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(
        f"/api/day1/clusters/{HERZI}/status", params={"mce": MCE}, headers=auth(support.VIEWER)
    )
    assert response.json() == {
        "cluster_name": HERZI,
        "hosted_cluster": "ocp4-prod-herzi-site1",
        "namespace": "hcp-prod-herzi-site1",
        "hc_phase": None,
        "ocp_version": "4.16.27",
        "hc_problems": [],
        "node_pools": [
            {
                "name": "prod-herzi-site1-dell",
                "ready_replicas": 2,
                "desired_replicas": 2,
                "problems": [],
            }
        ],
        "error": None,
    }


async def test_status_needs_the_mce(client: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    response = await client.get(f"/api/day1/clusters/{HERZI}/status", headers=auth(support.VIEWER))
    assert response.status_code == 422


async def test_an_unreachable_hub_is_an_error_in_a_200(
    support: Any, gitlab: Any, identity: Any, clock: Any, auth: Auth
) -> None:
    app = support.build_app(
        gitlab=gitlab,
        hub=FakeHubApi(unavailable=[MCE]),
        identity=identity,
        day2=FakeDay2Addons(),
        clock=clock,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://day1.test"
    ) as client:
        response = await client.get(
            f"/api/day1/clusters/{HERZI}/status", params={"mce": MCE}, headers=auth(support.VIEWER)
        )
    assert response.status_code == 200
    assert response.json()["error"].startswith("HubUnavailable:")


async def test_bulk_status_has_an_entry_for_every_cluster(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = {"clusters": [{"name": HERZI, "mce": MCE}, {"name": "ocp4-prod-hawk-site1", "mce": MCE}]}
    statuses = (
        await client.post("/api/day1/clusters/bulk-status", json=body, headers=auth(support.VIEWER))
    ).json()
    assert set(statuses) == {HERZI, "ocp4-prod-hawk-site1"}
    assert statuses[HERZI]["error"] is None
    assert statuses["ocp4-prod-hawk-site1"]["error"].startswith("HubObjectNotFound:")


async def test_infraenvs_list_and_an_unconfigured_mce(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    headers = auth(support.VIEWER)
    listed = await client.get(f"/api/day1/mces/{MCE}/infraenvs", headers=headers)
    assert listed.json() == ["dell-r660-site1-128c-1024gb-5tb"]
    unconfigured = await client.get(
        "/api/day1/mces/ocp4-prep-mce-site1-a/infraenvs", headers=headers
    )
    assert (unconfigured.status_code, unconfigured.json()["code"]) == (422, "VALIDATION_ERROR")


async def first_event(app: FastAPI, path: str, query: str, headers: dict[str, str]) -> str:
    """Drive the ASGI app directly and return the first SSE event, then disconnect.

    httpx's ASGITransport waits for the whole body, which an event stream never ends.
    """
    disconnect = asyncio.Event()
    chunks: list[bytes] = []
    started: dict[str, Any] = {}
    requested = False

    async def receive() -> Message:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            started.update(message)
        elif message["type"] == "http.response.body" and message.get("body"):
            chunks.append(message["body"])
            disconnect.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 1),
        "server": ("day1.test", 80),
    }
    async with asyncio.timeout(5):
        await app(scope, receive, send)
    assert started["status"] == 200
    assert (b"content-type", b"text/event-stream; charset=utf-8") in started["headers"]
    return chunks[0].decode()


async def test_the_status_stream_sends_the_status_as_an_event(
    app: FastAPI, auth: Auth, support: Any
) -> None:
    event = await first_event(
        app, f"/api/day1/clusters/{HERZI}/status/stream", f"mce={MCE}", auth(support.VIEWER)
    )
    assert event.startswith("data: ")
    assert event.endswith("\n\n")
    assert json.loads(event.removeprefix("data: "))["hosted_cluster"] == "ocp4-prod-herzi-site1"


async def test_the_status_stream_of_a_cluster_not_on_the_hub_reports_the_error(
    app: FastAPI, auth: Auth, support: Any
) -> None:
    # Not merged yet: the HostedCluster name is derived from the file name, and the
    # hub's 404 arrives as an event with ``error`` set, not as a broken stream.
    event = await first_event(
        app,
        "/api/day1/clusters/ocp4-prod-new-site1/status/stream",
        f"mce={MCE}",
        auth(support.VIEWER),
    )
    body = json.loads(event.removeprefix("data: "))
    assert body["hosted_cluster"] == "ocp4-prod-new-site1"
    assert body["error"].startswith("HubObjectNotFound:")
