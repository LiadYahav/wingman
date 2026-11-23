"""server-scan's rows read whole: every field, in server-scan's order (ADR-0038).

server-scan's ``GET /api/v1/servers/rows``, ``server_type`` since v6.3.0 and
absent from an older server-scan; a row that does not fit is "unavailable".
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from wingman_day1.domain.errors import ServerScanUnavailableError
from wingman_day1.integrations.server_scan.infrastructure.adapter import HttpServerInventory
from wingman_day1.integrations.server_scan.infrastructure.parse import fleet_rows, server_row

# One row exactly as server-scan's GET /api/v1/servers/rows answers it, every field set.
ROW: dict[str, Any] = {
    "id": "srv_d226c05c968244e19f68e4aa8f16bad3",
    "name": "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
    "vendor": "cisco",
    "server_type": "physical",
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


@pytest.mark.parametrize("sent", ["vm", "physical", None])
def test_a_rows_server_type_is_server_scans_and_none_from_an_older_one(sent: str | None) -> None:
    raw = dict(ROW)
    if sent is None:
        del raw["server_type"]
    else:
        raw["server_type"] = sent
    assert server_row(raw).server_type == sent


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


def test_the_fleet_keeps_server_scans_order() -> None:
    second = {**ROW, "id": "srv_2", "name": "a-first-by-name"}
    rows = fleet_rows({"items": [ROW, second], "generated_at": "2026-11-11T08:00:00Z"})
    assert [row.id for row in rows] == [ROW["id"], "srv_2"]
    assert fleet_rows({"items": []}) == ()


@pytest.mark.parametrize(
    "body",
    [
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
        await inventory.rows()
