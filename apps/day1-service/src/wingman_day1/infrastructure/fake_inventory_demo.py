"""Inventory Management's demo for ``DAY1_FAKE_FLEET``: ``dev/fleet-fixtures/inventory.yaml``.

More servers for the fake server-scan (``AVAILABLE`` ones, for pool draws and
named installs), the sample phases a fake add-server run walks, the fake
herzi's pool, and past runs (ADR-0057). Development only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import yaml

from wingman_core.ports.clock import Clock
from wingman_day1.domain.add_server import ADD_SERVER_WORKFLOW_PREFIX, canonical_mce
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_add_server import (
    DEMO_PHASES,
    FakeAddServerWorkflow,
    FakeRun,
    HerziScript,
)
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.server_scan_parse import server_row

INVENTORY_FILE: Final = Path("dev/fleet-fixtures/inventory.yaml")
SEEDED_RUN_MINUTES: Final = 6
"""How long a seeded run took, for its close time."""


@dataclass(frozen=True, slots=True)
class InventoryDemo:
    """What the fixture holds."""

    rows: tuple[ServerRow, ...]
    phases: tuple[str, ...]
    phase_seconds: float
    herzi: HerziScript | None
    runs: tuple[FakeRun, ...]


def default_inventory_file() -> Path:
    """``dev/fleet-fixtures/inventory.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / INVENTORY_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{INVENTORY_FILE} not found above this file")


def _herzi(raw: Mapping[str, Any] | None) -> HerziScript | None:
    if not raw:
        return None
    return HerziScript(
        mce=str(raw["mce"]),
        infra_env=str(raw["infra_env"]),
        first_after=timedelta(seconds=float(raw["first_after_seconds"])),
        every=timedelta(seconds=float(raw["every_seconds"])),
        probe=timedelta(seconds=float(raw["probe_seconds"])),
    )


def _run(raw: Mapping[str, Any], now: datetime) -> FakeRun:
    started = now - timedelta(minutes=float(raw["minutes_ago"]))
    if "pool" in raw:
        mce, infra_env, slot = raw["pool"]
        workflow_id = f"{ADD_SERVER_WORKFLOW_PREFIX}{canonical_mce(mce)}_{infra_env}_{int(slot)}"
        named = False
    else:
        mce, server = raw["named"]
        infra_env = ""
        workflow_id = f"{ADD_SERVER_WORKFLOW_PREFIX}{canonical_mce(mce)}_{str(server).lower()}"
        named = True
    return FakeRun(
        workflow_id,
        canonical_mce(mce),
        infra_env,
        started,
        server=raw.get("server") or (raw["named"][1] if named else None),
        named=named,
        status=str(raw["status"]).lower(),
        phase=raw.get("phase"),
        error=raw.get("error"),
        closed=started + timedelta(minutes=SEEDED_RUN_MINUTES),
        walks=False,
    )


def load_inventory_demo(path: Path, *, now: datetime) -> InventoryDemo:
    """The fixture at ``path``; seeded runs started ``minutes_ago`` before ``now``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise TypeError(f"{path}: expected a mapping with an 'items' list")
    runs: Sequence[Mapping[str, Any]] = raw.get("runs") or []
    return InventoryDemo(
        rows=tuple(server_row(item) for item in raw["items"]),
        phases=tuple(str(p) for p in raw.get("phases") or DEMO_PHASES),
        phase_seconds=float(raw.get("phase_seconds", 8)),
        herzi=_herzi(raw.get("herzi")),
        runs=tuple(_run(item, now) for item in runs),
    )


def fake_add_server(
    inventory: FakeServerInventory, *, clock: Clock, path: Path | None = None
) -> FakeAddServerWorkflow:
    """The demo's fake workflow, its servers added to ``inventory``."""
    demo = load_inventory_demo(path or default_inventory_file(), now=clock())
    for row in demo.rows:
        inventory.replace(row)
    return FakeAddServerWorkflow(
        inventory,
        clock=clock,
        phases=demo.phases,
        phase_seconds=demo.phase_seconds,
        herzi=demo.herzi,
        runs=demo.runs,
    )
