"""``/api/day1/server-scan/classification-rules`` and ``/health-policies`` (the note's §10).

The Server Scan area's Rules & Policies page (ADR-0048's 3.30.0 amendment):
server-scan's enabled rules and policies in its shapes. Admins only; off
(501) without server-scan; 502 when it fails or refuses Wingman's token.
Built on the fake fleet's ``dev/fleet-fixtures/rules.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_rules import default_rules_file, load_rules
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
RULES = "/api/day1/server-scan/classification-rules"
POLICIES = "/api/day1/server-scan/health-policies"
BOTH = pytest.mark.parametrize("path", [RULES, POLICIES])
DENIED = "server-scan refused Wingman's token (401): check SERVER_SCAN_TOKEN"


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    path: str,
    *,
    inventory: ServerInventory | None = None,
) -> httpx.Response:
    """GET ``path`` on an app over ``inventory`` (none: server-scan not configured)."""
    app = support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return await client.get(path, headers=headers)


def seeded() -> FakeServerInventory:
    return FakeServerInventory(rules=load_rules(default_rules_file()))


class DeniedInventory(FakeServerInventory):
    """server-scan refusing the viewer token."""

    async def classification_rules(self) -> ClassificationRuleList:
        raise ServerScanDeniedError(DENIED)

    async def health_policies(self) -> HealthPolicyList:
        raise ServerScanDeniedError(DENIED)


@BOTH
async def test_only_admins_read_them(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, path: str
) -> None:
    anonymous = await call(support, gitlab, clock, {}, path, inventory=seeded())
    assert anonymous.status_code == 401
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), path, inventory=seeded())
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    admin = await call(support, gitlab, clock, auth(support.ALICE), path, inventory=seeded())
    assert admin.status_code == 200


@BOTH
async def test_without_server_scan_the_page_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, path: str
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), path)
    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "FEATURE_DISABLED"
    assert "SERVER_SCAN_URL" in body["detail"]


@BOTH
async def test_server_scan_failing_or_refusing_the_token_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, path: str
) -> None:
    down = FakeServerInventory(unavailable=True)
    response = await call(support, gitlab, clock, auth(support.ALICE), path, inventory=down)
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    refused = await call(
        support, gitlab, clock, auth(support.ALICE), path, inventory=DeniedInventory()
    )
    assert (refused.status_code, refused.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_TOKEN" in refused.json()["detail"]


async def test_the_rules_in_server_scan_s_shape(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), RULES, inventory=seeded())
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["items"]
    first = body["items"][0]
    assert list(first) == [
        "id",
        "name",
        "description",
        "enabled",
        "system",
        "installation_type",
        "scope",
        "field",
        "pattern",
        "flags",
        "source",
        "priority",
        "order",
        "stats",
        "revision",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ]
    assert [r["installation_type"] for r in body["items"]] == ["HOSTED_CLUSTER", "MCE", "UPI"]
    assert first["scope"] == {"vendor": None, "manager_type": None, "site_id": None}
    assert first["stats"] == {"last_matched_at": None, "timeout_count": 0, "quarantined": False}


async def test_the_policies_in_server_scan_s_shape_every_condition_field_on_every_node(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), POLICIES, inventory=seeded())
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 20
    psu = next(p for p in items if p["policy_key"] == "power.psu_failed_critical")
    fields = ["all_of", "any_of", "not", "metric", "operator", "value", "equals"]
    assert list(psu["condition"]) == fields
    first, nested = psu["condition"]["any_of"]
    assert (first["metric"], first["operator"], first["value"], first["not"]) == (
        "power.failed_psu_count",
        "GTE",
        2,
        None,
    )
    assert [c["operator"] for c in nested["all_of"]] == ["EQ", "LTE"]
    assert psu["scope"] == {"site_id": None, "vendor": None, "manager_types": []}
    assert psu["evidence"][0] == {"key": "failed", "metric": "power.failed_psu_count"}
