"""``/api/day1/segments`` (docs/notes/2026-11-13-segments-area-api.md, ADR-0047).

Admins only (decision 13, until RBAC); off (501) without segments-manager;
502 when it fails. Built on the fixtures' day1 repo and the demo ledger of
``dev/fleet-fixtures/segments.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_segments import (
    FakeSegmentLedger,
    default_segments_file,
    load_fake_ledger,
)

Auth = Callable[[User], dict[str, str]]
ROUTES = ("/api/day1/segments/sites", "/api/day1/segments/stats", "/api/day1/segments")


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    *paths: str,
    ledger: FakeSegmentLedger | None = None,
) -> list[httpx.Response]:
    """GET each of ``paths``, in order, on one app over ``ledger`` (none: segments-manager off)."""
    app = support.build_app(
        gitlab=gitlab, hub=None, identity=None, day2=FakeDay2Addons(), clock=clock, ledger=ledger
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return [await client.get(path, headers=headers) for path in paths]


def demo() -> FakeSegmentLedger:
    return load_fake_ledger(default_segments_file())


async def test_only_admins_read_the_segments(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    for response in await call(support, gitlab, clock, {}, *ROUTES, ledger=demo()):
        assert response.status_code == 401, response.request.url
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), *ROUTES, ledger=demo())
    for response in viewer:
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    admin = await call(support, gitlab, clock, auth(support.ALICE), *ROUTES, ledger=demo())
    assert [r.status_code for r in admin] == [200, 200, 200]


async def test_without_segments_manager_every_route_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    for response in await call(support, gitlab, clock, auth(support.ALICE), *ROUTES):
        assert response.status_code == 501
        body = response.json()
        assert body["code"] == "FEATURE_DISABLED"
        assert "SEGMENTS_MANAGER_URL" in body["detail"]


async def test_segments_manager_failing_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    down = FakeSegmentLedger(unavailable=True)
    for response in await call(support, gitlab, clock, auth(support.ALICE), *ROUTES, ledger=down):
        assert response.status_code == 502
        assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


async def test_the_sites_and_the_stats(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    sites, stats = await call(
        support, gitlab, clock, auth(support.ALICE), *ROUTES[:2], ledger=demo()
    )
    assert sites.json() == {"sites": ["site1", "site2", "site3"]}
    by_site = {s["site"]: s for s in stats.json()["sites"]}
    assert list(by_site) == ["site1", "site2", "site3"]
    assert by_site["site1"] == {
        "site": "site1",
        "total_segments": 12,
        "allocated": 10,
        "by_type": [
            {"type": "HC", "allocated": 6},
            {"type": "MCE", "allocated": 1},
            {"type": "INVENTORY", "allocated": 1},
            {"type": "PXE", "allocated": 1},
            {"type": "UPI", "allocated": 1},
            {"type": "HUB", "allocated": 0},
        ],
    }
    assert (by_site["site3"]["total_segments"], by_site["site3"]["allocated"]) == (0, 0)


async def segments(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, query: str = ""
) -> dict[str, Any]:
    (response,) = await call(
        support, gitlab, clock, auth(support.ALICE), f"/api/day1/segments{query}", ledger=demo()
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_every_segment_with_its_holders_joined_to_day1(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await segments(support, gitlab, clock, auth)
    assert (body["unreadable"], body["clusters_error"], body["fresh"]) == ([], None, False)
    rows = {row["segment"]: row for row in body["segments"]}
    assert len(rows) == 18
    assert rows["10.20.44.0/24"] == {
        "segment": "10.20.44.0/24",
        "site": "site1",
        "vlan_id": 1418,
        "epg_name": "EPG_site1_HC_1418",
        "dhcp": True,
        "status": "Allocated",
        "type": "HC",
        "cluster_name": "ocp4-prod-herzi-site1",
        "allocated_at": "2026-10-05T14:01:22+00:00",
        "holders": [
            {
                "name": "ocp4-prod-herzi-site1",
                "day1": {"site": "site1", "mce": "ocp4-prod-mce-site1-a"},
            }
        ],
    }
    upi = rows["10.20.60.0/24"]
    assert upi["cluster_name"] == ["ocp4-upi-a", "ocp4-upi-b"]
    assert upi["holders"] == [
        {"name": "ocp4-upi-a", "day1": None},
        {"name": "ocp4-upi-b", "day1": None},
    ]
    assert upi["dhcp"] is False
    # An MCE, and an HC holder day1 has no file for, are names only
    assert rows["10.20.31.0/24"]["holders"] == [{"name": "ocp4-prod-mce-site1-a", "day1": None}]
    assert rows["10.20.53.0/24"]["holders"] == [{"name": "ocp4-prep-ghost-site2", "day1": None}]
    free = rows["10.20.49.0/24"]
    assert (free["status"], free["type"], free["holders"]) == ("Available", None, [])
    assert free["allocated_at"] == "2026-08-30T10:15:00+00:00"


async def test_segments_managers_filters_pass_through(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    upi = await segments(support, gitlab, clock, auth, "?type=UPI")
    assert [row["segment"] for row in upi["segments"]] == ["10.20.60.0/24"]
    free = await segments(support, gitlab, clock, auth, "?site=site2&status=Available")
    assert [row["segment"] for row in free["segments"]] == ["10.20.52.0/24"]
    assert (await segments(support, gitlab, clock, auth, "?site=site3"))["segments"] == []


@pytest.mark.parametrize(
    "query", ["?status=allocated", "?status=Locked", "?type=hc", "?type=VM", "?site=a/b", "?site="]
)
async def test_a_filter_segments_manager_would_not_know_is_422(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, query: str
) -> None:
    (response,) = await call(
        support, gitlab, clock, auth(support.ALICE), f"/api/day1/segments{query}", ledger=demo()
    )
    assert response.status_code == 422, query


async def test_fresh_reads_segments_managers_database_once_per_cool_down(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    ledger = demo()
    fresh = "/api/day1/segments?fresh=true"
    first, held, plain = await call(
        support,
        gitlab,
        clock,
        auth(support.ALICE),
        fresh,
        fresh,
        "/api/day1/segments",
        ledger=ledger,
    )
    assert [r.json()["fresh"] for r in (first, held, plain)] == [True, False, False]
    assert ledger.fresh_reads == 1
    assert ledger.list_reads == 1, "the held press and the plain read are the fresh read's answer"
