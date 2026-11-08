"""Every error is an RFC 9457 problem; writes need an admin, reads a session."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User

Auth = Callable[[User], dict[str, str]]
PROBLEM_MEMBERS = {"type", "title", "status", "detail", "instance", "code", "request_id", "details"}

SPEC = {"metadata": {"name": "agent-mini", "version": "1.0.0"}}
WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("POST", "/api/day1/clusters", {"use": "create"}),
    ("POST", "/api/day1/clusters/preview", {"use": "create"}),
    ("PATCH", "/api/day1/clusters/ocp4-prod-herzi-site1", {"updated_yaml": "mastertag: 4.1.1\n"}),
    ("DELETE", "/api/day1/clusters/ocp4-prod-herzi-site1", None),
    ("POST", "/api/day1/specs", SPEC),
    ("PUT", "/api/day1/specs/agent-single", SPEC),
    ("DELETE", "/api/day1/specs/agent-single", None),
    ("POST", "/api/day1/approvals/1/approve", {"sha": "abcdef12"}),
    ("POST", "/api/day1/approvals/1/reject", None),
    ("PUT", "/api/day1/approvals/1", {"files": [{"path": "a.yaml", "content": "x"}]}),
]


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == PROBLEM_MEMBERS
    assert (body["status"], body["code"]) == (status, code)
    assert body["type"] == f"/problems/{code.lower().replace('_', '-')}"
    assert body["request_id"]
    return body


def payload(support: Any, body: dict[str, Any] | None) -> dict[str, Any] | None:
    return support.create_body() if body == {"use": "create"} else body


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
async def test_a_viewer_cannot_change_anything(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    response = await client.request(
        method, path, json=payload(support, body), headers=auth(support.VIEWER)
    )
    problem = assert_problem(response, 403, "FORBIDDEN")
    assert problem["instance"] == path
    assert problem["details"] == {"role": "viewer"}


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
async def test_without_a_session_nothing_can_be_changed(
    client: httpx.AsyncClient, support: Any, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = await client.request(method, path, json=payload(support, body))
    assert_problem(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize(
    "path",
    [
        "/api/day1/clusters",
        "/api/day1/clusters/drift-summary",
        "/api/day1/sites",
        "/api/day1/mces",
        "/api/day1/specs",
        "/api/day1/approvals",
        "/api/day1/audit/commits",
        "/api/auth/me",
    ],
)
async def test_reads_need_a_session(client: httpx.AsyncClient, path: str) -> None:
    assert_problem(await client.get(path), 401, "UNAUTHORIZED")
    assert_problem(
        await client.get(path, headers={"Authorization": "Bearer not-a-token"}),
        401,
        "UNAUTHORIZED",
    )


async def test_a_viewer_can_read(client: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    response = await client.get("/api/day1/clusters", headers=auth(support.VIEWER))
    assert response.status_code == 200


async def test_an_unknown_route_is_a_not_found_problem(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    assert_problem(
        await client.get("/api/day1/nothing-here", headers=auth(support.VIEWER)), 404, "NOT_FOUND"
    )


async def test_an_unknown_cluster_is_a_not_found_problem(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = assert_problem(
        await client.get("/api/day1/clusters/ocp4-prod-ghost-site1", headers=auth(support.VIEWER)),
        404,
        "NOT_FOUND",
    )
    assert "ocp4-prod-ghost-site1" in body["detail"]


async def test_an_unknown_field_in_a_request_body_is_refused(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body(colour="blue")
    problem = assert_problem(
        await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE)),
        422,
        "VALIDATION_ERROR",
    )
    assert problem["details"]["errors"][0]["loc"] == ["body", "colour"]


async def test_a_rule_violation_lists_every_problem(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body("ocp4-prep-falcon-site2")
    problem = assert_problem(
        await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE)),
        422,
        "VALIDATION_ERROR",
    )
    assert problem["details"]["problems"]
    assert all(isinstance(p, str) for p in problem["details"]["problems"])


async def test_a_bad_path_segment_is_a_validation_problem(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(
        "/api/day1/clusters/x/history",
        params={"site": "..", "mce": "m"},
        headers=auth(support.VIEWER),
    )
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("method", "path"), [("POST", "/api/day1/sites"), ("POST", "/api/day1/sites/site1/mces")]
)
async def test_sites_and_mces_cannot_be_created_any_more(
    client: httpx.AsyncClient, auth: Auth, support: Any, method: str, path: str
) -> None:
    # Legacy: these opened MRs that wrote .gitkeep files, one into hostedClusters/,
    # which broke that MCE's ApplicationSet.
    response = await client.request(
        method, path, json={"name": "site9"}, headers=auth(support.ALICE)
    )
    assert_problem(response, 405, "VALIDATION_ERROR")


async def test_metrics_count_requests_by_route_template_and_gitlab_calls(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await client.get("/api/day1/clusters/ocp4-prod-herzi-site1", headers=auth(support.VIEWER))
    text = (await client.get("/metrics")).text
    assert (
        'wingman_http_requests_total{method="GET",route="/api/day1/clusters/{name}",'
        'status_class="2xx"} 1.0'
    ) in text
    assert "ocp4-prod-herzi-site1" not in text
    assert (
        'wingman_dependency_requests_total{dependency="gitlab",operation="read_file",outcome="ok"}'
        in text
    )
    assert 'wingman_build_info{commit="unknown",component="day1"' in text
