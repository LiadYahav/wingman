"""The Servers page's read: server-scan's rows, every field, and the conditional GET (ADR-0048).

server-scan's ``GET /api/v1/servers/rows`` read whole (22 fields and
``generated_at``), the same fleet object answered while server-scan says
``304`` (day1 encodes it once), one cache entry for the rows and the fleet,
the fake's ``generated_at``, and day1's own ``ETag`` rule (server-scan's).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.api.conditional import etag_matches, weak_etag
from wingman_day1.domain.errors import ServerScanUnavailableError
from wingman_day1.domain.server_scan_servers import FleetRows
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.server_scan import HttpServerInventory
from wingman_day1.infrastructure.server_scan_parse import fleet_rows, server_row

# One row exactly as server-scan's GET /api/v1/servers/rows answers it, every field set.
ROW: dict[str, Any] = {
    "id": "srv_d226c05c968244e19f68e4aa8f16bad3",
    "name": "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
    "vendor": "cisco",
    "model": "UCS C220 M6",
    "site_id": "bat-yam",
    "source_provider": "INTERSIGHT",
    "installation_type": "HOSTED_CLUSTER",
    "health": "MAJOR",
    "maintenance": {
        "enabled": True,
        "reason": "donor: parts for R2",
        "created_by": "api-token-admin",
    },
    "reservation": {
        "held": True,
        "holder": "add-server-to-mce",
        "mce_cluster": "mce-bat-yam",
        "infra_env": "cisco-m6-bat-yam-128c-128gb",
        "expires_at": "2026-11-13T18:00:00Z",
    },
    "openshift_state": "INSTALLED",
    "cluster_name": "hc-bat-yam-03",
    "mce_name": "mce-bat-yam",
    "openshift_reported_name": "worker-7.hc-bat-yam-03",
    "contested_with": "hc-bat-yam-02",
    "profile_template_name": "UCS-X-Standard",
    "last_seen_at": "2026-11-10T22:00:03.530203Z",
    "stale": True,
    "reachable": False,
    "serial": "CIS0000630",
    "bmc_host": "192.0.2.118",
    "macs": ["02:00:00:00:00:01", "02:00:00:00:00:02"],
}
BODY = {"items": [ROW], "generated_at": "2026-11-11T08:00:00Z"}
ETAG = 'W/"5e1f"'


def test_every_field_of_a_row_is_read() -> None:
    row = server_row(ROW)
    assert (row.source_provider, row.profile_template, row.bmc_host) == (
        "INTERSIGHT",
        "UCS-X-Standard",
        "192.0.2.118",
    )
    assert (row.maintenance, row.maintenance_reason, row.maintenance_by) == (
        True,
        "donor: parts for R2",
        "api-token-admin",
    )
    assert (row.reported_name, row.contested_with, row.contested) == (
        "worker-7.hc-bat-yam-03",
        "hc-bat-yam-02",
        True,
    )
    assert (row.reserved_by, row.reserved_for_mce, row.reserved_for_infra_env) == (
        "add-server-to-mce",
        "mce-bat-yam",
        "cisco-m6-bat-yam-128c-128gb",
    )
    assert (row.stale, row.reachable, row.health, row.state) == (True, False, "MAJOR", "INSTALLED")


def test_an_uncontested_row_with_nothing_optional_reads_as_blanks() -> None:
    bare = {
        **ROW,
        **dict.fromkeys(
            ("source_provider", "openshift_reported_name", "contested_with", "bmc_host"), None
        ),
        "profile_template_name": None,
        "maintenance": None,
        "reservation": None,
    }
    row = server_row(bare)
    assert (row.source_provider, row.reported_name, row.profile_template, row.bmc_host) == (
        None,
        None,
        None,
        None,
    )
    assert (row.contested, row.maintenance, row.maintenance_reason, row.reserved_by) == (
        False,
        False,
        None,
        None,
    )


def test_the_fleet_keeps_server_scans_order_and_generated_at() -> None:
    second = {**ROW, "id": "srv_2", "name": "a-first-by-name"}
    fleet = fleet_rows({"items": [ROW, second], "generated_at": "2026-11-11T08:00:00Z"})
    assert [row.id for row in fleet.rows] == [ROW["id"], "srv_2"]
    assert fleet.generated_at == datetime(2026, 11, 11, 8, tzinfo=UTC)
    assert fleet_rows({"items": [], "generated_at": None}).generated_at is None


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "generated_at": "yesterday"},
        {"items": [{**ROW, "bmc_host": 7}]},
        {"items": [{**ROW, "maintenance": {"enabled": True, "reason": 3}}]},
        {"items": [{**ROW, "contested_with": ["two"]}]},
    ],
)
async def test_a_malformed_fleet_is_unavailable_never_blank(body: object) -> None:
    inventory = HttpServerInventory(
        base_url="http://server-scan.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)),
    )
    with pytest.raises(ServerScanUnavailableError, match="malformed server rows"):
        await inventory.fleet()


async def test_a_304_answers_the_same_fleet_object() -> None:
    answers = [httpx.Response(200, json=BODY, headers={"ETag": ETAG}), httpx.Response(304)]
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return answers.pop(0)

    inventory = HttpServerInventory(
        base_url="http://server-scan.test", transport=httpx.MockTransport(handler)
    )
    first = await inventory.fleet()
    assert await inventory.fleet() is first, "day1 encodes an unchanged fleet once"
    assert sent[1].headers["if-none-match"] == ETAG


async def test_rows_are_the_fleets_rows() -> None:
    changed = copy.deepcopy(BODY)
    inventory = HttpServerInventory(
        base_url="http://server-scan.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=changed)),
    )
    assert await inventory.rows() == list((await inventory.fleet()).rows)


async def test_the_cache_holds_the_rows_and_the_fleet_as_one_entry() -> None:
    reads: list[int] = []

    class Counting(FakeServerInventory):
        async def fleet(self) -> FleetRows:
            reads.append(1)
            return await super().fleet()

    cached = CachedServerInventory(Counting([server_row(ROW)]), TtlCache(), ttl=30)
    fleet = await cached.fleet()
    assert await cached.fleet() is fleet
    assert await cached.rows() == list(fleet.rows)
    assert len(reads) == 1


async def test_the_fake_fleet_changed_when_its_newest_row_was_seen() -> None:
    older = server_row({**ROW, "id": "srv_old", "last_seen_at": "2026-11-01T00:00:00Z"})
    never = server_row({**ROW, "id": "srv_never", "last_seen_at": None})
    fleet = await FakeServerInventory([older, server_row(ROW), never]).fleet()
    assert fleet.generated_at == datetime(2026, 11, 10, 22, 0, 3, 530203, tzinfo=UTC)
    assert (await FakeServerInventory().fleet()).generated_at is None


@pytest.mark.parametrize(
    ("header", "matches"),
    [
        (None, False),
        ("", False),
        ('W/"abc"', True),
        ('"abc"', True),
        ('W/"zzz", W/"abc"', True),
        ("*", True),
        ('W/"zzz"', False),
    ],
)
def test_if_none_match_compares_weakly_as_server_scan_does(
    header: str | None, matches: bool
) -> None:
    assert etag_matches(header, 'W/"abc"') is matches


def test_the_etag_is_weak_and_follows_the_body() -> None:
    assert weak_etag(b"{}").startswith('W/"')
    assert weak_etag(b"{}") == weak_etag(b"{}")
    assert weak_etag(b"{}") != weak_etag(b"[]")
