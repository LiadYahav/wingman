"""A server's page: its record, a VM's host and its History (ADR-0048, 3.25.0).

The adapter against server-scan's answers (MockTransport), in the shape its
``backend/app/api/v1/schemas.py`` and ``events_schemas.py`` send at 92146d3,
internals included: read and typed, malformed answers refused, the viewer
token on the record and the host, the auditor token on History only, the
metrics. The cache reads every one through; the fake builds them from its
fixture; the use case keeps History off without the auditor token
(docs/notes/2026-11-13-server-scan-area-api.md §9).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanAuditOffError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_events import HISTORY_OFF, EventPage, audit_detail
from wingman_day1.domain.server_scan_record import ServerRecord
from wingman_day1.domain.server_scan_servers import MaintenanceStart
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_records import (
    FakeRecords,
    default_records_file,
    load_records,
)
from wingman_day1.infrastructure.server_scan import HttpServerInventory

VIEWER = "server-scan-viewer-token-never-shown-0002"
AUDITOR = "server-scan-auditor-token-never-shown-0004"
SERVER_ID = "srv_d226c05c968244e19f68e4aa8f16bad3"
NAME = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0101"
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def server_scan_detail(**changes: Any) -> dict[str, Any]:
    """server-scan's ``ServerDetail`` for one Dell server, its internals included."""
    detail: dict[str, Any] = {
        "id": SERVER_ID,
        "schema_version": 3,
        "name": NAME,
        "name_normalized": NAME.lower(),
        "model": "PowerEdge R660",
        "model_normalized": "poweredge r660",
        "identity": {
            "vendor": "dell",
            "serial": "DLFAKE0101",
            "serial_normalized": "dlfake0101",
            "system_uuid": "4c4c4544-0000-1010-8000-c0c04f303130",
            "nic_macs": ["02:00:00:00:01:01"],
            "external_ids": {"openmanage-site1": "10123"},
        },
        "profile_template": {"name": "R660-Standard", "external_id": "tmpl-1"},
        "hardware": {
            "cpu": {"sockets": 2, "cores": 64, "threads": 128, "model": "Xeon Gold 6438Y+"},
            "memory": {
                "total_bytes": 1099511627776,
                "modules": [
                    {
                        "slot": "A1",
                        "size_bytes": 68719476736,
                        "type": "DDR5",
                        "speed_mhz": 4800,
                        "serial": "M1",
                        "health": "HEALTHY",
                        "health_detail": "OK",
                    }
                ],
            },
            "storage": {
                "total_bytes": 960197124096,
                "drives": [
                    {
                        "id": "Disk.Bay.0",
                        "model": "MZ7L3960",
                        "serial": "S0",
                        "media_type": "SSD",
                        "protocol": "SATA",
                        "capacity_bytes": 960197124096,
                        "slot": "0",
                        "health": "HEALTHY",
                        "health_detail": "OK",
                        "firmware_version": "1.0",
                        "controller_id": "RAID.SL.3-1",
                    }
                ],
                "controllers": [
                    {"id": "RAID.SL.3-1", "name": "PERC", "kind": "RAID", "drive_count": 1}
                    | {"volumes": []}
                ],
                "raid": {"state": "PRESENT", "method": "redfish_storage", "bmc": "iDRAC9"}
                | {"reason": None},
            },
            "gpus": [],
            "power": {
                "psus": [
                    {
                        "id": "PSU.Slot.1",
                        "model": "1400W",
                        "serial": "P1",
                        "health": "UP",
                        "health_detail": None,
                        "capacity_watts": 1400,
                        "power_watts": 318,
                    }
                ]
            },
        },
        "network": {
            "bmc": {
                "address_raw": "https://192.0.2.101",
                "scheme": "https",
                "host": "192.0.2.101",
                "host_is_ip": True,
                "port": None,
                "path": None,
                "mac": "02:00:00:00:01:ff",
            },
            "interfaces": [
                {
                    "name": "NIC.Integrated.1-1-1",
                    "mac": "02:00:00:00:01:01",
                    "speed_mbps": 25000,
                    "link_state": "UP",
                    "location": "1/1/1",
                }
            ],
        },
        "connectivity": {
            "attachments": [],
            "facts": {
                "fabric_paths_total": 0,
                "fabric_paths_up": 0,
                "fabric_paths_down": 0,
                "fabrics_present": [],
            },
        },
        "classification": {
            "installation_type": "HOSTED_CLUSTER",
            "matched_rule_id": "r1",
            "matched_rule_name": "Hosted cluster nodes",
            "matched_pattern": "^ocp-",
            "matched_field": "name",
            "classified_at": "2026-09-01T06:01:00Z",
            "classification_version": 4,
        },
        "health": {
            "overall": "WARNING",
            "memory": "WARNING",
            "storage": "HEALTHY",
            "raid": "HEALTHY",
            "network": "HEALTHY",
            "connectivity": "UNKNOWN",
            "power": "HEALTHY",
            "gpu": "UNKNOWN",
            "bmc": "HEALTHY",
            "name": "HEALTHY",
            "evaluated_at": "2026-11-11T08:00:03Z",
            "active_policy_keys": ["memory.correctable_errors"],
            "reasons": [
                {
                    "policy_key": "memory.correctable_errors",
                    "policy_name": "Correctable memory errors",
                    "category": "memory",
                    "severity": "WARNING",
                    "message": "DIMM B3",
                }
            ],
        },
        "maintenance": {
            "enabled": True,
            "reason": "Replacing PSU 2",
            "created_by": "api-token-admin",
            "created_at": "2026-11-12T09:14:00Z",
            "updated_at": "2026-11-12T09:14:00Z",
            "expected_end": "2026-11-14T16:00:00Z",
        },
        "reservation": {
            "holder": None,
            "mce_cluster": None,
            "infra_env": None,
            "namespace": None,
            "workflow_id": None,
            "created_at": None,
            "expires_at": None,
        },
        "openshift": {
            "lifecycle_state": "INSTALLED",
            "cluster_name": "ocp4-prod-lark-site1",
            "mce_name": "ocp4-prod-mce-site1-a",
            "last_reported_at": "2026-11-11T08:00:03Z",
            "reported_by_agent_id": "agent-1",
            "reported_name": None,
            "agent_uid": "uid-1",
            "previous_reporter": None,
            "previous_agent_uid": None,
            "claim_changed_at": None,
            "contested_with": None,
            "contested_name": None,
        },
        "vm_host": None,
        "site_id": "site1",
        "manager_id": "openmanage-site1",
        "tags": [],
        "search_tokens": ["dlfake0101"],
        "source_provider": "OPENMANAGE",
        "unread_fields": ["hardware.gpus"],
        "nic_os_names": {"NIC.Integrated.1-1-1": "eno12399np0"},
        "last_seen_at": "2026-11-11T08:00:03Z",
        "stale": False,
        "reachable": True,
        "unreachable_since": None,
        "unreachable_reason": None,
        "revision": 17,
        "created_at": "2026-09-01T06:00:00Z",
        "updated_at": "2026-11-11T08:00:03Z",
    }
    detail.update(changes)
    return detail


def events_page() -> dict[str, Any]:
    """server-scan's ``AuditEventListResponse``, one event."""
    return {
        "items": [
            {
                "id": "evt_1",
                "event_type": "MAINTENANCE_ENABLED",
                "server_id": SERVER_ID,
                "server_name": NAME,
                "actor": {
                    "type": "TOKEN",
                    "id": "api-token-admin",
                    "display": None,
                    "role": "ADMIN",
                },
                "request_id": "req-1",
                "created_at": "2026-11-12T09:14:00Z",
                "data": {"reason": "Replacing PSU 2", "nested": {"a": [1, None]}},
            }
        ],
        "page": {"next_cursor": "c2", "has_more": True, "page_size": 1, "total": 7},
    }


def make(
    *answers: httpx.Response | Exception,
    token: str = VIEWER,
    auditor: str = AUDITOR,
    metrics: WingmanMetrics | None = None,
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    sent: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000",
        token=token,
        admin_token="server-scan-admin-token-never-shown-0003",
        auditor_token=auditor,
        metrics=metrics,
        transport=httpx.MockTransport(handler),
        timer=iter(range(1000)).__next__,
        clock=lambda: NOW,
    )
    return inventory, sent


# ── The record ───────────────────────────────────────────────────────────────


async def test_the_record_is_read_whole_with_the_viewer_token() -> None:
    inventory, sent = make(httpx.Response(200, json=server_scan_detail()))
    record = await inventory.record(SERVER_ID)
    (request,) = sent
    assert (request.method, request.url.path) == ("GET", f"/api/v1/servers/{SERVER_ID}")
    assert request.headers["authorization"] == f"Bearer {VIEWER}"
    assert record.hardware.cpu.threads == 128
    assert record.hardware.storage.drives[0].media_type == "SSD"
    assert record.hardware.power.psus[0].power_watts == 318.0
    assert record.health.reasons[0].message == "DIMM B3"
    assert record.maintenance.expected_end == datetime(2026, 11, 14, 16, tzinfo=UTC)
    assert record.nic_os_names == {"NIC.Integrated.1-1-1": "eno12399np0"}
    assert record.reservation.held is False


async def test_the_record_drops_server_scans_internals() -> None:
    inventory, _ = make(httpx.Response(200, json=server_scan_detail()))
    sent = (await inventory.record(SERVER_ID)).model_dump(mode="json")
    for internal in ("schema_version", "name_normalized", "search_tokens", "revision"):
        assert internal not in sent
    assert "external_ids" not in sent["identity"]
    assert "evaluated_at" not in sent["health"]
    assert "host_is_ip" not in sent["network"]["bmc"]
    assert set(sent["reservation"]) >= {"held", "holder", "mce_cluster", "expires_at"}


@pytest.mark.parametrize(
    ("holder", "expires", "held"),
    [
        (None, None, False),
        ("install-server", None, True),
        ("install-server", NOW + timedelta(minutes=5), True),
        ("install-server", NOW - timedelta(minutes=5), False),
    ],
)
async def test_the_reservation_is_held_by_server_scans_rule_for_rows(
    holder: str | None, expires: datetime | None, held: bool
) -> None:
    raw = server_scan_detail()
    raw["reservation"] |= {
        "holder": holder,
        "mce_cluster": "ocp4-prod-mce-site1-a" if holder else None,
        "expires_at": expires.isoformat() if expires else None,
    }
    inventory, _ = make(httpx.Response(200, json=raw))
    assert (await inventory.record(SERVER_ID)).reservation.held is held


async def test_an_older_document_without_reasons_controllers_or_raid_reads() -> None:
    raw = server_scan_detail()
    del raw["health"]["reasons"]
    del raw["hardware"]["storage"]["controllers"], raw["hardware"]["storage"]["raid"]
    inventory, _ = make(httpx.Response(200, json=raw))
    record = await inventory.record(SERVER_ID)
    assert (record.health.reasons, record.hardware.storage.controllers) == ((), ())
    assert record.hardware.storage.raid is None


def malformed() -> list[dict[str, Any]]:
    count_as_text = server_scan_detail()
    count_as_text["hardware"]["cpu"]["cores"] = "64"
    missing = server_scan_detail()
    del missing["openshift"]
    bad_time = server_scan_detail(updated_at="yesterday")
    return [count_as_text, missing, bad_time]


@pytest.mark.parametrize("raw", malformed())
async def test_a_malformed_record_is_unavailable_never_blank(raw: dict[str, Any]) -> None:
    inventory, _ = make(httpx.Response(200, json=raw))
    with pytest.raises(ServerScanUnavailableError, match="malformed server"):
        await inventory.record(SERVER_ID)


async def test_an_unknown_server_is_not_found_in_server_scans_words() -> None:
    problem = {"code": "NOT_FOUND", "detail": f"No server with id {SERVER_ID!r}."}
    inventory, _ = make(httpx.Response(404, json=problem))
    with pytest.raises(ServerNotFoundError, match="No server with id"):
        await inventory.record(SERVER_ID)


async def test_a_refused_viewer_token_names_its_setting() -> None:
    inventory, _ = make(httpx.Response(401, json={}))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.record(SERVER_ID)


async def test_server_scan_unreachable_is_unavailable() -> None:
    inventory, _ = make(httpx.ConnectError("refused"))
    with pytest.raises(ServerScanUnavailableError, match="unreachable"):
        await inventory.record(SERVER_ID)


# ── A VM's host ──────────────────────────────────────────────────────────────


async def test_a_vms_host_is_read_with_the_viewer_token() -> None:
    answer = {
        "cluster_name": "ocp4-prod-virt-site1",
        "node_name": "worker-3",
        "match": "MEMBERSHIP",
        "host": {
            "id": "srv_host",
            "name": "ocp-dell-r760-site1-host",
            "vendor": "dell",
            "model": "PowerEdge R760",
            "site_id": "site1",
            "cpu": {"sockets": 2, "cores": 96, "threads": 192, "model": "Xeon"},
            "memory_total_bytes": 1649267441664,
            "health": "HEALTHY",
            "maintenance": False,
            "cluster_name": "ocp4-prod-virt-site1",
        },
    }
    inventory, sent = make(httpx.Response(200, json=answer))
    host = await inventory.vm_host(SERVER_ID)
    assert sent[0].url.path == f"/api/v1/servers/{SERVER_ID}/vm-host"
    assert sent[0].headers["authorization"] == f"Bearer {VIEWER}"
    assert (host.match, host.host and host.host.cpu.cores) == ("MEMBERSHIP", 96)


async def test_a_server_that_is_not_a_vm_has_no_host() -> None:
    problem = {"detail": f"Server {NAME!r} is not a virtual machine."}
    inventory, _ = make(httpx.Response(404, json=problem))
    with pytest.raises(ServerNotFoundError, match="not a virtual machine"):
        await inventory.vm_host(SERVER_ID)


# ── History ──────────────────────────────────────────────────────────────────


async def test_history_is_read_with_the_auditor_token_only() -> None:
    inventory, sent = make(
        httpx.Response(200, json=events_page()), httpx.Response(200, json=server_scan_detail())
    )
    page = await inventory.server_events(SERVER_ID, cursor="c1", page_size=50)
    await inventory.record(SERVER_ID)
    history, record = sent
    assert history.url.path == f"/api/v1/servers/{SERVER_ID}/events"
    assert dict(history.url.params) == {"page_size": "50", "cursor": "c1"}
    assert history.headers["authorization"] == f"Bearer {AUDITOR}"
    assert record.headers["authorization"] == f"Bearer {VIEWER}", (
        "the auditor token reads History only"
    )
    (event,) = page.items
    assert (event.actor.id, event.data["nested"]) == ("api-token-admin", {"a": [1, None]})
    assert (page.page.next_cursor, page.page.total) == ("c2", 7)


async def test_the_first_page_sends_no_cursor() -> None:
    inventory, sent = make(httpx.Response(200, json=events_page()))
    await inventory.server_events(SERVER_ID, cursor=None, page_size=50)
    assert "cursor" not in sent[0].url.params


async def test_with_auth_off_history_sends_no_token() -> None:
    inventory, sent = make(httpx.Response(200, json=events_page()), token="", auditor="")
    await inventory.server_events(SERVER_ID, cursor=None, page_size=50)
    assert "authorization" not in sent[0].headers


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_auditor_token_names_its_setting(status: int) -> None:
    inventory, _ = make(httpx.Response(status, json={}))
    with pytest.raises(ServerScanDeniedError, match=r"auditor token .* SERVER_SCAN_AUDITOR_TOKEN"):
        await inventory.server_events(SERVER_ID, cursor=None, page_size=50)


async def test_a_malformed_history_is_unavailable() -> None:
    raw = events_page()
    raw["items"][0]["created_at"] = None
    inventory, _ = make(httpx.Response(200, json=raw))
    with pytest.raises(ServerScanUnavailableError, match="malformed history"):
        await inventory.server_events(SERVER_ID, cursor=None, page_size=50)


# ── Metrics ──────────────────────────────────────────────────────────────────


async def test_each_read_is_counted_under_its_operation() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=server_scan_detail()),
        httpx.Response(404, json={}),
        httpx.Response(403, json={}),
        metrics=metrics,
    )
    await inventory.record(SERVER_ID)
    with pytest.raises(ServerNotFoundError):
        await inventory.vm_host(SERVER_ID)
    with pytest.raises(ServerScanDeniedError):
        await inventory.server_events(SERVER_ID, cursor=None, page_size=50)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("get_server_record", "ok") == 1
    assert count("get_vm_host", "not_found") == 1
    assert count("list_server_events", "denied") == 1
    assert count("get_server", "ok") is None, "the uninstall's check is its own operation"


# ── The cache, the use case ──────────────────────────────────────────────────


def fixture_fleet() -> FakeServerInventory:
    rows, _ = load_fleet(default_fleet_file())
    return FakeServerInventory(
        rows, records=load_records(default_records_file()), clock=lambda: NOW
    )


class CountingFleet(FakeServerInventory):
    def __init__(self) -> None:
        rows, _ = load_fleet(default_fleet_file())
        super().__init__(rows)
        self.reads: list[str] = []

    async def record(self, server_id: str) -> ServerRecord:
        self.reads.append("record")
        return await super().record(server_id)

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        self.reads.append("events")
        return await super().server_events(server_id, cursor=cursor, page_size=page_size)


async def test_the_cache_reads_a_record_and_history_through_every_time() -> None:
    inner = CountingFleet()
    cached = CachedServerInventory(inner, TtlCache(), ttl=30, sites_ttl=10)
    server_id = inner.snapshot()[0].id
    for _ in range(2):
        await cached.record(server_id)
        await cached.server_events(server_id, cursor=None, page_size=50)
    assert inner.reads == ["record", "events", "record", "events"]


@pytest.mark.parametrize(
    ("viewer", "auditor", "detail"),
    [(True, True, None), (False, False, None), (False, True, None), (True, False, HISTORY_OFF)],
)
def test_history_needs_the_auditor_token_beside_a_viewer_token(
    viewer: bool, auditor: bool, detail: str | None
) -> None:
    assert audit_detail("History", viewer_token=viewer, auditor_token=auditor) == detail


async def test_the_use_case_keeps_history_off_without_the_auditor_token() -> None:
    fleet = fixture_fleet()
    service = ServerScanService(fleet, history_detail=HISTORY_OFF)
    server_id = fleet.snapshot()[0].id
    with pytest.raises(ServerScanAuditOffError, match="SERVER_SCAN_AUDITOR_TOKEN"):
        await service.history(server_id, cursor=None, page_size=50)
    assert (await service.record(server_id)).id == server_id, "the record reads all the same"


# ── The fake ─────────────────────────────────────────────────────────────────


async def test_every_fixture_server_has_a_record_with_its_models_hardware() -> None:
    fleet = fixture_fleet()
    for row in fleet.snapshot():
        record = await fleet.record(row.id)
        assert (record.name, record.identity.serial) == (row.name, row.serial)
    r760 = next(row for row in fleet.snapshot() if row.model == "PowerEdge R760")
    record = await fleet.record(r760.id)
    assert len(record.hardware.gpus) == 2
    assert record.hardware.memory.total_bytes == 512 * 1024**3, "from the name's 512gb"
    assert record.hardware.storage.drives[0].serial == f"{r760.serial}-S0"


async def test_the_fixtures_special_servers_show_their_states() -> None:
    fleet = fixture_fleet()
    cisco = next(row for row in fleet.snapshot() if row.name.endswith("CSFAKE0302"))
    record = await fleet.record(cisco.id)
    assert (record.reachable, record.unreachable_reason) == (False, "timeout")
    assert record.connectivity.facts.fabric_paths_down == 2
    assert record.health.connectivity == "CRITICAL"
    assert "hardware.power.psus" in record.unread_fields


async def test_the_fakes_history_pages_and_records_its_maintenance_writes() -> None:
    fleet = fixture_fleet()
    row = next(row for row in fleet.snapshot() if not row.maintenance)
    first = await fleet.server_events(row.id, cursor=None, page_size=2)
    assert first.page.has_more and first.page.total
    rest = await fleet.server_events(row.id, cursor=first.page.next_cursor, page_size=50)
    assert rest.page.total is None and not rest.page.has_more
    assert [e.event_type for e in rest.items][-1] == "SERVER_CREATED"
    end = datetime(2026, 11, 15, tzinfo=UTC)
    await fleet.start_maintenance(row.id, MaintenanceStart(reason="donor", expected_end=end))
    await fleet.end_maintenance(row.id)
    newest = (await fleet.server_events(row.id, cursor=None, page_size=2)).items
    assert [e.event_type for e in newest] == ["MAINTENANCE_DISABLED", "MAINTENANCE_ENABLED"]
    assert (newest[1].actor.id, newest[1].data["reason"]) == ("dev", "donor")


async def test_the_fakes_record_shows_its_maintenances_expected_end() -> None:
    fleet = fixture_fleet()
    row = next(row for row in fleet.snapshot() if not row.maintenance)
    end = datetime(2026, 11, 15, tzinfo=UTC)
    await fleet.start_maintenance(row.id, MaintenanceStart(reason="PSU", expected_end=end))
    maintenance = (await fleet.record(row.id)).maintenance
    assert (maintenance.enabled, maintenance.expected_end, maintenance.created_at) == (
        True,
        end,
        NOW,
    )


async def test_an_unknown_server_has_no_record_and_an_empty_history() -> None:
    fleet = fixture_fleet()
    with pytest.raises(ServerNotFoundError):
        await fleet.record("srv_unknown")
    page = await fleet.server_events("srv_unknown", cursor=None, page_size=50)
    assert (page.items, page.page.total) == ((), 0)


async def test_a_fake_vm_finds_its_host_by_name_and_a_server_is_no_vm() -> None:
    rows, _ = load_fleet(default_fleet_file())
    vm, host = rows[0], rows[1]
    records = FakeRecords(
        servers={vm.name: {"vm_host": {"cluster_name": "ocp4-virt", "node_name": host.name}}}
    )
    fleet = FakeServerInventory(rows, records=records, clock=lambda: NOW)
    answer = await fleet.vm_host(vm.id)
    assert (answer.match, answer.host and answer.host.id) == ("NAME", host.id)
    with pytest.raises(ServerNotFoundError, match="not a virtual machine"):
        await fleet.vm_host(host.id)
