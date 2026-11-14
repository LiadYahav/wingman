"""server-scan's classification rules and health policies through the adapter, and the fake's.

The answers are in server-scan's shapes (``ClassificationRuleListResponse``
and ``HealthPolicyListResponse`` in ``backend/app/api/v1/`` at 92146d3;
ADR-0048's 3.30.0 amendment): every field on every condition node, the
unused ones null, as server-scan dumps them.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import yaml
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import ServerScanDeniedError, ServerScanUnavailableError
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_records import default_records_file
from wingman_day1.infrastructure.fake_server_scan_rules import default_rules_file, load_rules
from wingman_day1.infrastructure.server_scan import HttpServerInventory

TOKEN = "server-scan-viewer-token-never-shown-0004"
ADMIN_TOKEN = "server-scan-admin-token-never-shown-0004"
AUDITOR_TOKEN = "server-scan-auditor-token-never-shown-0004"
AT = "2026-09-01T06:00:00Z"


def node(**fields: Any) -> dict[str, Any]:
    """A condition node as server-scan dumps it: every field, the unused ones null."""
    return {
        "all_of": None,
        "any_of": None,
        "not": None,
        "metric": None,
        "operator": None,
        "value": None,
        "equals": None,
    } | fields


def rule(rule_id: str = "rule_1", **changes: Any) -> dict[str, Any]:
    return {
        "id": rule_id,
        "name": "system-default-hypershift-hosted-cluster",
        "description": 'Hosted control planes: any name starting with "ocp4-hypershift".',
        "enabled": True,
        "system": True,
        "installation_type": "HOSTED_CLUSTER",
        "scope": {"vendor": None, "manager_type": None, "site_id": None},
        "field": "name",
        "pattern": "^ocp4-hypershift",
        "flags": {"ignore_case": True, "multiline": False, "dotall": False},
        "source": "SYSTEM_DEFAULT",
        "priority": 100,
        "order": 0,
        "stats": {"last_matched_at": AT, "timeout_count": 0, "quarantined": False},
        "revision": 1,
        "created_at": AT,
        "updated_at": AT,
        "created_by": None,
        "updated_by": None,
    } | changes


def policy(policy_id: str = "policy_1", **changes: Any) -> dict[str, Any]:
    return {
        "id": policy_id,
        "name": "Power supply failed (no redundancy left)",
        "description": "Fires when two or more power supplies report DOWN.",
        "enabled": True,
        "system": True,
        "policy_key": "power.psu_failed_critical",
        "mode": "EVALUATE",
        "category": "power",
        "severity": "CRITICAL",
        "condition": node(
            any_of=[
                node(metric="power.failed_psu_count", operator="GTE", value=2),
                node(
                    all_of=[
                        node(metric="power.failed_psu_count", operator="EQ", value=1),
                        node(metric="power.psu_count", operator="LTE", value=1),
                    ]
                ),
            ]
        ),
        "evidence": [{"key": "failed", "metric": "power.failed_psu_count"}],
        "message_template": "{failed} of {total} power supplies failed",
        "scope": {"site_id": None, "vendor": None, "manager_types": []},
        "source": "SYSTEM_DEFAULT",
        "priority": 100,
        "order": 0,
        "stats": {"fire_count": 3, "last_fired_at": None, "error_count": 0, "quarantined": False},
        "revision": 2,
        "created_at": AT,
        "updated_at": AT,
        "created_by": None,
        "updated_by": None,
    } | changes


RULES: dict[str, Any] = {
    "items": [
        rule(),
        rule(
            "rule_2",
            name="Lab nodes",
            scope={"vendor": "dell", "manager_type": "OPENMANAGE", "site_id": "tlv"},
            source="SITE_CUSTOM",
            priority=500,
        ),
    ]
}
POLICIES: dict[str, Any] = {
    "items": [
        policy(),
        policy(
            "policy_2",
            name="No RAID 1 configured for the OS",
            category="raid",
            condition=node(metric="raid.state", operator="EQ", value="ABSENT"),
            scope={"site_id": None, "vendor": None, "manager_types": ["OPENMANAGE", "UCS_MANAGER"]},
        ),
        policy(
            "policy_3",
            severity="WARNING",
            condition=node(**{"not": node(metric="gpu.models", operator="ANY", value=["A100"])}),
            evidence=[],
        ),
    ]
}

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, token: str = TOKEN, metrics: WingmanMetrics | None = None
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000/",
        token=token,
        admin_token=ADMIN_TOKEN,
        auditor_token=AUDITOR_TOKEN,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return inventory, requests


def answer(rules: object = RULES, policies: object = POLICIES) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/classification-rules":
            return httpx.Response(200, json=rules)
        if request.url.path == "/api/v1/health-policies":
            return httpx.Response(200, json=policies)
        return httpx.Response(404, json={})

    return handler


def reply(status: int) -> Handler:
    return lambda _request: httpx.Response(status, json={"detail": "no"})


# ── The real adapter ──────────────────────────────────────────────────────────


async def test_both_are_read_enabled_only_with_the_viewer_token() -> None:
    inventory, requests = make(answer())
    rules = await inventory.classification_rules()
    policies = await inventory.health_policies()
    assert [r.url.path for r in requests] == [
        "/api/v1/classification-rules",
        "/api/v1/health-policies",
    ]
    # As server-scan's page asks: a disabled rule is not something the deployment does
    assert [dict(r.url.params) for r in requests] == [{"enabled": "true"}, {"enabled": "true"}]
    # The viewer token, never the admin's or the auditor's
    assert {r.headers["Authorization"] for r in requests} == {f"Bearer {TOKEN}"}
    assert [r.name for r in rules.items] == [
        "system-default-hypershift-hosted-cluster",
        "Lab nodes",
    ]
    assert rules.items[1].scope.site_id == "tlv"
    assert policies.items[0].condition.any_of is not None
    assert policies.items[0].condition.any_of[1].all_of is not None
    negated = policies.items[2].condition.not_
    assert negated is not None
    assert (negated.metric, negated.value) == ("gpu.models", ["A100"])
    assert policies.items[1].scope.manager_types == ("OPENMANAGE", "UCS_MANAGER")


async def test_the_answers_go_on_in_server_scan_s_shape_field_for_field() -> None:
    inventory, _ = make(answer())
    rules = await inventory.classification_rules()
    policies = await inventory.health_policies()
    dumped = [
        rules.model_dump(mode="json", by_alias=True),
        policies.model_dump(mode="json", by_alias=True),
    ]
    assert dumped == [RULES, POLICIES]


async def test_a_rule_or_policy_holding_only_the_required_fields_gets_server_scan_s_defaults() -> (
    None
):
    bare_rule = {
        k: v
        for k, v in rule().items()
        if k in {"id", "name", "installation_type", "field", "pattern", "source", "priority"}
        or k.endswith("_at")
    }
    bare_policy = {
        k: v
        for k, v in policy().items()
        if k
        in {
            "id",
            "name",
            "policy_key",
            "category",
            "severity",
            "message_template",
            "source",
            "priority",
        }
        or k.endswith("_at")
    } | {"condition": {"metric": "bmc.unreachable_count", "operator": "GTE", "value": 1}}
    inventory, _ = make(answer({"items": [bare_rule]}, {"items": [bare_policy]}))
    (only_rule,) = (await inventory.classification_rules()).items
    (only_policy,) = (await inventory.health_policies()).items
    assert (only_rule.enabled, only_rule.flags.ignore_case, only_rule.scope.vendor) == (
        True,
        True,
        None,
    )
    assert (only_rule.stats.timeout_count, only_rule.description) == (0, "")
    assert (only_policy.mode, only_policy.evidence, only_policy.scope.manager_types) == (
        "EVALUATE",
        (),
        (),
    )
    assert only_policy.condition.all_of is None


def changed(base: dict[str, Any], path: tuple[str | int, ...], value: object) -> dict[str, Any]:
    body = copy.deepcopy(base)
    target: Any = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return body


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"items": "rules"},
        changed(RULES, ("items", 0, "priority"), "100"),
        changed(RULES, ("items", 0, "flags", "ignore_case"), "yes"),
        changed(RULES, ("items", 0, "created_at"), "yesterday"),
        changed(RULES, ("items", 0, "pattern"), None),
    ],
)
async def test_malformed_rules_are_unavailable(body: object) -> None:
    inventory, _ = make(answer(rules=body))
    with pytest.raises(ServerScanUnavailableError, match="malformed classification rules"):
        await inventory.classification_rules()


@pytest.mark.parametrize(
    "body",
    [
        {},
        changed(POLICIES, ("items", 0, "condition"), "storage.failed_drive_count >= 1"),
        changed(POLICIES, ("items", 0, "condition", "any_of"), "x"),
        changed(POLICIES, ("items", 0, "evidence"), [{"key": "failed"}]),
        changed(POLICIES, ("items", 0, "scope", "manager_types"), "OPENMANAGE"),
        changed(POLICIES, ("items", 0, "severity"), 3),
    ],
)
async def test_malformed_policies_are_unavailable(body: object) -> None:
    inventory, _ = make(answer(policies=body))
    with pytest.raises(ServerScanUnavailableError, match="malformed health policies"):
        await inventory.health_policies()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_token_is_denied_and_names_the_setting(status: int) -> None:
    inventory, _ = make(reply(status))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.classification_rules()
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.health_policies()


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_any_other_answer_is_unavailable(status: int) -> None:
    inventory, _ = make(reply(status))
    with pytest.raises(
        ServerScanUnavailableError, match=f"answered {status} listing classification"
    ):
        await inventory.classification_rules()
    with pytest.raises(ServerScanUnavailableError, match=f"answered {status} listing health"):
        await inventory.health_policies()


async def test_server_scan_not_reached_is_unavailable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    inventory, _ = make(down)
    with pytest.raises(ServerScanUnavailableError, match="unreachable listing health policies"):
        await inventory.health_policies()


async def test_each_read_is_counted_under_its_own_operation() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(answer(), metrics=metrics)
    await ok.classification_rules()
    await ok.health_policies()
    denied, _ = make(reply(403), metrics=metrics)
    with pytest.raises(ServerScanDeniedError):
        await denied.health_policies()
    malformed, _ = make(answer(rules={}), metrics=metrics)
    with pytest.raises(ServerScanUnavailableError):
        await malformed.classification_rules()

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("list_classification_rules", "ok") == 1
    assert count("list_classification_rules", "unavailable") == 1
    assert count("list_health_policies", "ok") == 1
    assert count("list_health_policies", "denied") == 1


# ── The fake ──────────────────────────────────────────────────────────────────


async def test_the_fake_serves_its_fixture_with_nothing_dropped() -> None:
    path = default_rules_file()
    fake_rules = load_rules(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    fake = FakeServerInventory(rules=fake_rules)
    rules = await fake.classification_rules()
    policies = await fake.health_policies()
    assert [r.id for r in rules.items] == [r["id"] for r in raw["classification_rules"]["items"]]
    assert len(policies.items) == 20
    assert {p.severity for p in policies.items} == {"CRITICAL", "MAJOR", "WARNING"}
    fabric = [p for p in policies.items if p.scope.vendor == "cisco"]
    assert [p.scope.manager_types for p in fabric] == [("UCS_CENTRAL", "INTERSIGHT")] * 2
    # Every fixture field reaches the answer
    for parsed, fixture in zip(policies.items, raw["health_policies"]["items"], strict=True):
        dumped = parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
        for key, value in fixture.items():
            if key not in {"condition", "scope"}:
                assert dumped[key] == value, key


def test_the_fake_rules_are_the_ones_the_fake_records_say_matched() -> None:
    """The server page's "Matched rule" and the Rules & Policies page agree in the demo."""
    records = yaml.safe_load(default_records_file().read_text(encoding="utf-8"))["rules"]
    rules = load_rules(default_rules_file()).rules.items
    by_id = {r.id: r for r in rules}
    for installation_type, named in records.items():
        found = by_id[named["id"]]
        assert (found.installation_type, found.name) == (installation_type, named["name"])
        assert (found.field, found.pattern) == (named["field"], named["pattern"])
    assert len(rules) == len(records)


async def test_a_fake_without_rules_has_none_and_fails_when_down() -> None:
    assert (await FakeServerInventory().classification_rules()).items == ()
    assert (await FakeServerInventory().health_policies()).items == ()
    with pytest.raises(ServerScanUnavailableError):
        await FakeServerInventory(unavailable=True).health_policies()
