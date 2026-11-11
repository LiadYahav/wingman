"""``GET /api/day1/clusters/{name}/network`` (docs/notes/2026-11-11-cluster-network-api.md).

The VLAN and the segment come from the cluster file (Git is the source of
truth); segments-manager adds the EPG and is checked against the file
(ADR-0039). Built on the fixtures' clusters, with the fake ledger.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_segments import (
    FakeSegmentLedger,
    default_segments_file,
    load_segments,
)

Auth = Callable[[User], dict[str, str]]
AMIT = "ocp4-prep-amit-site2-a"
HERZI = "ocp4-prod-herzi-site1"
HAWK = "ocp4-prod-hawk-site1"
AMIT_SEGMENT = "10.20.90.0/24"


def demo_ledger(**changes: Any) -> FakeSegmentLedger:
    """The demo ledger; ``changes`` replace fields of amit's segment."""
    records = load_segments(default_segments_file())
    return FakeSegmentLedger(
        dataclasses.replace(r, **changes) if r.segment == AMIT_SEGMENT else r for r in records
    )


async def get(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth | None,
    name: str,
    *,
    ledger: FakeSegmentLedger | None = None,
    query: str = "",
) -> httpx.Response:
    """``GET /clusters/{name}/network`` as a viewer, on an app without the MCE hubs."""
    app = support.build_app(
        gitlab=gitlab, hub=None, identity=None, day2=FakeDay2Addons(), clock=clock, ledger=ledger
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = auth(support.VIEWER) if auth else {}
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return await client.get(
            f"/api/day1/clusters/{quote(name, safe='')}/network{query}", headers=headers
        )


async def network(*args: Any, **kwargs: Any) -> dict[str, Any]:
    response = await get(*args, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


async def test_without_segments_manager_the_network_is_the_files(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await network(support, gitlab, clock, auth, AMIT)
    assert body == {
        "vlan_id": 2490,
        "segment": AMIT_SEGMENT,
        "epg": None,
        "ledger": None,
        "problems": [],
        "ledger_error": None,
    }


async def test_segments_manager_adds_the_epg_and_its_record(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    ledger = demo_ledger()
    body = await network(support, gitlab, clock, auth, AMIT, ledger=ledger)
    assert body == {
        "vlan_id": 2490,
        "segment": AMIT_SEGMENT,
        "epg": "EPG_site2_HC_2490",
        "ledger": {
            "vlan_id": 2490,
            "cluster_name": AMIT,
            "status": "Allocated",
            "type": "HC",
            "site": "site2",
        },
        "problems": [],
        "ledger_error": None,
    }


async def test_a_vlan_that_differs_is_a_warning_and_the_file_wins(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await network(support, gitlab, clock, auth, HERZI, ledger=demo_ledger())
    assert (body["vlan_id"], body["segment"]) == (1410, "10.20.44.0/24")
    assert body["ledger"]["vlan_id"] == 1418
    assert body["problems"] == [
        "segments-manager has VLAN 1418 for this segment; the file has 1410"
    ]


async def test_another_holder_and_a_free_status_are_warnings(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    other = demo_ledger(cluster_name="ocp4-prep-kite-site2")
    body = await network(support, gitlab, clock, auth, AMIT, ledger=other)
    assert body["problems"] == [
        f"segments-manager allocated this segment to ocp4-prep-kite-site2, not to {AMIT}"
    ]
    free = demo_ledger(status="Available", cluster_name=None, type=None)
    body = await network(support, gitlab, clock, auth, AMIT, ledger=free)
    assert body["problems"] == ["segments-manager marks this segment Available, not Allocated"]
    assert body["ledger"]["cluster_name"] is None


async def test_a_shared_segment_answers_its_clusters_as_a_list(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    shared = demo_ledger(type="UPI", cluster_name=("seed-a", AMIT))
    body = await network(support, gitlab, clock, auth, AMIT, ledger=shared)
    assert body["ledger"]["cluster_name"] == ["seed-a", AMIT]
    assert body["problems"] == []


async def test_a_segment_segments_manager_does_not_have_is_a_warning(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await network(support, gitlab, clock, auth, AMIT, ledger=FakeSegmentLedger())
    assert (body["epg"], body["ledger"], body["ledger_error"]) == (None, None, None)
    assert body["problems"] == [f"segments-manager has no segment {AMIT_SEGMENT}"]


async def test_segments_manager_failing_never_fails_the_read(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    down = FakeSegmentLedger(unavailable=True)
    body = await network(support, gitlab, clock, auth, AMIT, ledger=down)
    assert (body["vlan_id"], body["segment"]) == (2490, AMIT_SEGMENT)
    assert (body["epg"], body["ledger"], body["problems"]) == (None, None, [])
    assert body["ledger_error"] == (
        f"SegmentsManagerUnavailable: segments-manager answered 503 reading segment {AMIT_SEGMENT}"
    )


async def test_a_cluster_not_allocated_yet_asks_nothing(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    ledger = demo_ledger()
    body = await network(support, gitlab, clock, auth, HAWK, ledger=ledger)
    assert body == {
        "vlan_id": None,
        "segment": None,
        "epg": None,
        "ledger": None,
        "problems": [],
        "ledger_error": None,
    }
    assert ledger.reads == 0


async def test_a_file_that_does_not_parse_has_no_network(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    broken = "ocp4-prod-broken-site1"
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=f"sites/{support.PROD_SITE}/mces/{support.PROD_MCE}/hostedClusters/{broken}.yaml",
        content="dhcp_values: [\n",
    )
    ledger = demo_ledger()
    body = await network(support, gitlab, clock, auth, broken, ledger=ledger)
    assert (body["vlan_id"], body["segment"], body["problems"]) == (None, None, [])
    assert ledger.reads == 0


async def test_site_and_mce_pin_the_file_and_an_unknown_cluster_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    query = "?site=site2&mce=ocp4-prep-mce-site2-a"
    body = await network(support, gitlab, clock, auth, AMIT, ledger=demo_ledger(), query=query)
    assert body["epg"] == "EPG_site2_HC_2490"
    missing = await get(support, gitlab, clock, auth, "ocp4-prod-nope-site1")
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"


async def test_a_session_is_needed(support: Any, gitlab: InMemoryGitLab, clock: Any) -> None:
    response = await get(support, gitlab, clock, None, AMIT)
    assert response.status_code == 401


async def test_the_detail_carries_the_segment_too(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = support.build_app(
        gitlab=gitlab, hub=None, identity=None, day2=FakeDay2Addons(), clock=clock
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        response = await client.get(f"/api/day1/clusters/{AMIT}", headers=auth(support.VIEWER))
    assert response.json()["values"]["network"] == {
        "vlan_id": 2490,
        "dhcp_network": "10.20.90.0",
        "segment": AMIT_SEGMENT,
    }
