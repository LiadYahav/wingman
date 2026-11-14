"""server-scan's ``GET /api/v1/confs`` through HttpServerInventory, and the fake's catalog.

The answers are in server-scan's shape (``ConfListResponse`` in
``backend/app/api/v1/confs_schemas.py`` at 92146d3; ADR-0048's 3.29.0
amendment); the fake's fixture is server-scan's own fake catalog.
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
from wingman_day1.infrastructure.fake_server_scan_confs import default_confs_file, load_confs
from wingman_day1.infrastructure.server_scan import HttpServerInventory

TOKEN = "server-scan-viewer-token-never-shown-0003"
ADMIN_TOKEN = "server-scan-admin-token-never-shown-0003"
AUDITOR_TOKEN = "server-scan-auditor-token-never-shown-0003"


def conf(conf_id: str = "CONF200", **changes: Any) -> dict[str, Any]:
    """One conf as server-scan's API dumps it: every field, ``l1``/``l2``/``l3`` by name."""
    return {
        "conf_id": conf_id,
        "part_number": "210-AZKL",
        "model": "PowerEdge R650",
        "cpu": {
            "model": "Intel Xeon Gold 6338",
            "vendor": "Intel",
            "sockets": 2,
            "cores_per_cpu": 32,
            "total_cores_ht": 128,
            "clock_mhz": 2000,
            "max_clock_mhz": 3200,
            "cache_kb": {"l1": 2560, "l2": 40960, "l3": 49152},
        },
        "ram": {"total_gib": 512, "dimms": 16, "per_dimm_gb": 32, "type": ["DDR4"]},
        "disks": [{"count": 2, "type": "SSD", "capacity_tb": 0.48}],
        "gpus": [],
        "gpu_count": 0,
        "gpu_vram_gb": None,
        "adapters": [{"count": 1, "ports": 2, "speed": 100.0}],
        "adapter_count": 1,
    } | changes


# As server-scan answers it: natural conf_id order (CONF9 before CONF10), and the skipped ids.
ANSWER: dict[str, Any] = {
    "items": [
        conf("CONF9"),
        conf(
            "CONF10",
            gpus=[{"count": 8, "model": "NVIDIA H200 SXM"}],
            gpu_count=8,
            gpu_vram_gb=141.0,
        ),
        conf(
            "CONF-21",
            part_number=None,
            ram={"total_gib": 0, "dimms": 0, "per_dimm_gb": 0, "type": []},
        ),
    ],
    "unreadable": ["CONF-98", "CONF-99"],
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


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


# ── The real adapter ──────────────────────────────────────────────────────────


async def test_the_confs_are_read_with_the_viewer_token_and_typed_in_server_scan_s_order() -> None:
    inventory, requests = make(reply(200, ANSWER))
    confs = await inventory.confs()
    (request,) = requests
    assert request.url.path == "/api/v1/confs"
    assert not request.url.query
    # The viewer token, never the admin's or the auditor's
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert [c.conf_id for c in confs.items] == ["CONF9", "CONF10", "CONF-21"]
    assert confs.unreadable == ("CONF-98", "CONF-99")
    gpu = confs.items[1]
    assert (gpu.gpu_count, gpu.gpus[0].model, gpu.gpu_vram_gb) == (8, "NVIDIA H200 SXM", 141.0)
    assert confs.items[0].cpu.cache_kb.l3 == 49152
    assert confs.items[2].part_number is None


async def test_the_answer_goes_on_in_server_scan_s_shape_field_for_field() -> None:
    inventory, _ = make(reply(200, ANSWER))
    confs = await inventory.confs()
    assert confs.model_dump(mode="json") == ANSWER


async def test_a_conf_holding_only_the_required_fields_gets_server_scan_s_defaults() -> None:
    bare = conf()
    for key in (
        "part_number",
        "disks",
        "gpus",
        "gpu_count",
        "gpu_vram_gb",
        "adapters",
        "adapter_count",
    ):
        del bare[key]
    del bare["cpu"]["vendor"]
    del bare["ram"]["type"]
    inventory, _ = make(reply(200, {"items": [bare]}))
    confs = await inventory.confs()
    (only,) = confs.items
    assert (only.part_number, only.cpu.vendor, only.ram.type) == (None, None, ())
    assert (only.disks, only.gpus, only.adapters) == ((), (), ())
    assert (only.gpu_count, only.gpu_vram_gb, only.adapter_count) == (0, None, 0)
    assert confs.unreadable == ()


async def test_without_a_token_no_authorization_header_is_sent() -> None:
    inventory, requests = make(reply(200, ANSWER), token="")
    await inventory.confs()
    assert "Authorization" not in requests[0].headers


def malformed() -> list[object]:
    def changed(path: tuple[str | int, ...], value: object) -> dict[str, Any]:
        answer = copy.deepcopy(ANSWER)
        target: Any = answer
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return answer

    return [
        [],
        {"unreadable": []},
        {"items": "CONF200"},
        changed(("items", 0, "cpu", "sockets"), "2"),
        changed(("items", 0, "cpu"), None),
        changed(("items", 0, "ram", "total_gib"), 512.5),
        changed(("items", 0, "disks", 0, "capacity_tb"), "0.48"),
        changed(("items", 0, "conf_id"), 200),
        changed(("unreadable",), [7]),
    ]


@pytest.mark.parametrize("body", malformed())
async def test_malformed_confs_are_unavailable_never_blanks(body: object) -> None:
    inventory, _ = make(reply(200, body))
    with pytest.raises(ServerScanUnavailableError, match="malformed confs"):
        await inventory.confs()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_token_is_denied_and_names_the_setting(status: int) -> None:
    inventory, _ = make(reply(status, {"detail": "no"}))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.confs()


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_any_other_answer_is_unavailable(status: int) -> None:
    inventory, _ = make(reply(status, {}))
    with pytest.raises(ServerScanUnavailableError, match=f"answered {status} listing confs"):
        await inventory.confs()


async def test_server_scan_not_reached_is_unavailable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    inventory, _ = make(down)
    with pytest.raises(ServerScanUnavailableError, match="unreachable listing confs"):
        await inventory.confs()


async def test_the_confs_read_is_counted_as_list_confs() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(reply(200, ANSWER), metrics=metrics)
    await ok.confs()
    denied, _ = make(reply(401, {}), metrics=metrics)
    with pytest.raises(ServerScanDeniedError):
        await denied.confs()
    failing, _ = make(reply(500, {}), metrics=metrics)
    with pytest.raises(ServerScanUnavailableError):
        await failing.confs()

    def count(outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": "list_confs", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("ok"), count("denied"), count("unavailable")) == (1, 1, 1)


# ── The fake ──────────────────────────────────────────────────────────────────


async def test_the_fake_fleet_serves_server_scan_s_fake_catalog_as_its_fixture_holds_it() -> None:
    path = default_confs_file()
    confs = load_confs(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    # Nothing in the fixture is dropped or changed on the way
    assert confs.model_dump(mode="json") == raw
    fake = FakeServerInventory(confs=confs)
    served = await fake.confs()
    assert len(served.items) == 20
    assert [c.conf_id for c in served.items if c.part_number is None] == ["CONF-21", "CONF-34"]
    assert next(c for c in served.items if c.conf_id == "CONF-34").ram.total_gib == 0
    assert [c.conf_id for c in served.items if c.gpu_count] == [
        "CONF202",
        "CONF211.2",
        "CONF221.2",
        "CONF231",
    ]
    assert served.unreadable == ("CONF-99",)


async def test_a_fake_without_a_catalog_has_no_confs_and_fails_when_down() -> None:
    assert (await FakeServerInventory().confs()).items == ()
    with pytest.raises(ServerScanUnavailableError):
        await FakeServerInventory(unavailable=True).confs()
