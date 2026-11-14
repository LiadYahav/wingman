"""FakeRecords: the fake fleet's server records and History (ADR-0048's 3.25.0 amendment).

With ``DAY1_FAKE_FLEET=true`` a server's record is its row (``servers.yaml``)
and its model's hardware from ``dev/fleet-fixtures/server-records.yaml``,
built in server-scan's own JSON shape and read by the same strict models as
the real answer, so the fixture cannot drift from the shape. Its History is
made up from the row (discovered, classified, installed, health, maintenance)
plus every maintenance change made in the fake since it started, by ``dev``,
as a server-scan with auth off records it; the fleet's audit trail joins them
(``fake_server_scan_events``). Nothing here is real.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import yaml

from wingman_day1.domain.server_scan_record import ServerRecord
from wingman_day1.domain.servers import ServerRow

RECORDS_FILE: Final = Path("dev/fleet-fixtures/server-records.yaml")
CREATED_AT: Final = datetime(2026, 9, 1, 6, tzinfo=UTC)
"""When every fake server was first discovered."""
DEV_ACTOR: Final = {"type": "USER", "id": "dev", "display": "dev"}
"""Who a server-scan with auth off records for a write."""
GIB: Final = 1024**3
_SIZES = re.compile(r"-(\d+)c-(\d+)gb-", re.IGNORECASE)
_FABRIC = frozenset({"UCS_CENTRAL", "UCS_MANAGER", "INTERSIGHT"})
_RAID = frozenset({"OPENMANAGE", "REDFISH_STANDALONE", "UCS_CENTRAL", "UCS_MANAGER"})
_NO_BMC = frozenset({"UCS_CENTRAL", "UCS_MANAGER", "INTERSIGHT", "KUBEVIRT"})
_EMPTY_HARDWARE: Final[Mapping[str, Any]] = {
    "cpu": {"sockets": 0, "cores": 0, "threads": 0, "model": None},
    "memory": {"modules": 0},
    "storage": {"drives": [], "controllers": [], "raid": None},
    "gpus": [],
    "power": {"psus": []},
}

JSONish = dict[str, Any]


class FakeRecords:
    """Builds a fake server's record and History from its row and the fixture."""

    def __init__(
        self,
        models: Mapping[str, JSONish] | None = None,
        rules: Mapping[str, JSONish] | None = None,
        servers: Mapping[str, JSONish] | None = None,
    ) -> None:
        """Hardware per model, the rule per installation type, and per-server differences."""
        self._models = dict(models or {})
        self._rules = dict(rules or {})
        self._servers = dict(servers or {})
        self._logged: dict[str, list[JSONish]] = {}
        self._since: dict[str, tuple[datetime, datetime | None]] = {}
        self._before: dict[str, ServerRow] = {}
        """Each written server as it was before the fake's first write: its seeded History."""

    def record(self, row: ServerRow, now: datetime) -> ServerRecord:
        """The row's record, as server-scan would answer it, its reservation judged at ``now``."""
        model = self._models.get(row.model or "", {})
        extra = self._servers.get(row.name, {})
        hardware = _hardware(model.get("hardware") or _EMPTY_HARDWARE, row)
        raw = {
            **_identity(row, model),
            "hardware": hardware,
            "network": _network(row, model.get("nics") or {}),
            "connectivity": _connectivity(row, model, extra),
            "classification": self._classification(row),
            "health": _health(row, extra, has_gpus=bool(hardware["gpus"])),
            "maintenance": self._maintenance(row),
            "reservation": _reservation(row),
            "openshift": _openshift(row),
            "vm_host": extra.get("vm_host"),
            "unread_fields": extra.get("unread_fields", []),
            "nic_os_names": (model.get("nics") or {}).get("os_names", {}),
            **_times(row, extra),
        }
        return ServerRecord.model_validate_json(json.dumps(raw, default=_iso)).judged(now)

    def log_maintenance(
        self,
        before: ServerRow,
        row: ServerRow,
        *,
        at: datetime,
        expected_end: datetime | None = None,
    ) -> None:
        """Record a maintenance change made in the fake (``before`` it, ``row`` after), as there."""
        self._before.setdefault(row.id, before)
        was_on = before.maintenance
        data: JSONish = {}
        if not row.maintenance:
            kind = "MAINTENANCE_DISABLED"
            self._since.pop(row.id, None)
        else:
            kind = "MAINTENANCE_UPDATED" if was_on else "MAINTENANCE_ENABLED"
            data = {"reason": row.maintenance_reason, "expected_end": expected_end}
            started = self._since.get(row.id, (at, None))[0] if was_on else at
            self._since[row.id] = (started, expected_end)
        self._logged.setdefault(row.id, []).append(_event(row, kind, at, DEV_ACTOR, data))

    def _classification(self, row: ServerRow) -> JSONish:
        kind = row.installation_type or "UNCLASSIFIED"
        rule = self._rules.get(kind, {})
        return {
            "installation_type": kind,
            "matched_rule_id": rule.get("id"),
            "matched_rule_name": rule.get("name"),
            "matched_field": rule.get("field"),
            "matched_pattern": rule.get("pattern"),
        }

    def _maintenance(self, row: ServerRow) -> JSONish:
        started, expected_end = self._since.get(row.id, (_seen(row) - timedelta(hours=1), None))
        on = row.maintenance
        return {
            "enabled": on,
            "reason": row.maintenance_reason,
            "created_by": row.maintenance_by,
            "created_at": started if on else None,
            "updated_at": started if on else None,
            "expected_end": expected_end if on else None,
        }

    def history(self, row: ServerRow) -> list[JSONish]:
        """The row's events, in server-scan's shape: as seeded, then the fake's own writes."""
        seeded = self._before.get(row.id, row)
        events = _history(seeded, self._classification(row), self._servers.get(row.name, {}))
        events += self._logged.get(row.id, [])
        for index, event in enumerate(events):
            event["id"] = f"evt_{row.id[-12:]}_{index:04d}"
        return events


def _hardware(spec: Mapping[str, Any], row: ServerRow) -> JSONish:
    """The model's hardware for this server: its serials, and its name's cores and memory."""
    hardware = _with_serial(copy.deepcopy(dict(spec)), row.serial or row.id)
    sizes = _SIZES.search(row.name)
    if sizes:
        threads = int(sizes[1])
        hardware["cpu"] |= {"threads": threads, "cores": threads // 2}
    memory = hardware["memory"]
    count = int(memory.get("modules", 0))
    total = int(sizes[2]) * GIB if sizes else 0
    hardware["memory"] = {
        "total_bytes": total,
        "modules": [_module(i, total // count, memory.get("speed_mhz")) for i in range(count)]
        if count and total
        else [],
    }
    drives = hardware["storage"]["drives"]
    hardware["storage"]["total_bytes"] = sum(d["capacity_bytes"] or 0 for d in drives)
    return hardware


def _module(index: int, size: int, speed: int | None) -> JSONish:
    return {
        "slot": f"{'AB'[index % 2]}{index // 2 + 1}",
        "size_bytes": size,
        "speed_mhz": speed,
        "health": "HEALTHY",
        "health_detail": "OK",
    }


def _with_serial(value: Any, serial: str) -> Any:
    if isinstance(value, str):
        return value.replace("{serial}", serial)
    if isinstance(value, list):
        return [_with_serial(item, serial) for item in value]
    if isinstance(value, dict):
        return {key: _with_serial(item, serial) for key, item in value.items()}
    return value


def _identity(row: ServerRow, model: Mapping[str, Any]) -> JSONish:
    template = row.profile_template
    return {
        "id": row.id,
        "name": row.name,
        "model": row.model,
        "profile_template": {"name": template, "external_id": template and f"tmpl-{template}"},
        "identity": {
            "vendor": row.vendor or "standalone",
            "serial": row.serial,
            "system_uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, row.id)),
            "nic_macs": list(row.macs),
        },
        "site_id": row.site,
        "manager_id": model.get("manager"),
        "source_provider": row.source_provider,
        "tags": [],
    }


def _network(row: ServerRow, nics: Mapping[str, Any]) -> JSONish:
    names = nics.get("names", [])
    places = nics.get("locations", [])
    interfaces = [
        {
            "name": names[i] if i < len(names) else f"NIC.{i + 1}",
            "mac": mac,
            "speed_mbps": nics.get("speed_mbps"),
            "link_state": "UP",
            "location": places[i] if i < len(places) else None,
        }
        for i, mac in enumerate(row.macs)
    ]
    host = row.bmc_host
    bmc_mac = f"{row.macs[0][:-2]}ff" if row.macs else None
    return {
        "bmc": {
            "address_raw": f"https://{host}" if host else None,
            "scheme": "https" if host else None,
            "host": host,
            "port": None,
            "mac": bmc_mac,
        },
        "interfaces": interfaces,
    }


def _connectivity(row: ServerRow, model: Mapping[str, Any], extra: Mapping[str, Any]) -> JSONish:
    state = "DOWN" if extra.get("uplinks_down") else "UP"
    attachments = [
        {
            "type": "FABRIC_INTERCONNECT",
            "provider": row.source_provider,
            "fabric_id": uplink["fabric_name"],
            "admin_state": "ENABLED",
            "oper_state": state,
            "speed_mbps": (model.get("nics") or {}).get("speed_mbps"),
            "last_seen": row.last_seen_at,
            **uplink,
        }
        for uplink in model.get("uplinks", [])
    ]
    physical = [a for a in attachments if a["interface_kind"] == "PHYSICAL"]
    up = sum(1 for a in physical if a["oper_state"] == "UP")
    return {
        "attachments": attachments,
        "facts": {
            "fabric_paths_total": len(physical),
            "fabric_paths_up": up,
            "fabric_paths_down": len(physical) - up,
            "fabrics_present": sorted({str(a["fabric"]) for a in physical}),
        },
    }


def _health(row: ServerRow, extra: Mapping[str, Any], *, has_gpus: bool) -> JSONish:
    """Every category HEALTHY where server-scan judges it, UNKNOWN elsewhere; the fixture's say."""
    provider = row.source_provider or ""
    judged = {
        "memory": True,
        "storage": True,
        "network": True,
        "raid": provider in _RAID,
        "connectivity": provider in _FABRIC,
        "power": provider != "KUBEVIRT",
        "gpu": has_gpus,
        "bmc": provider not in _NO_BMC,
        "name": True,
    }
    fresh = not extra.get("unevaluated")
    health = {key: "HEALTHY" if on and fresh else "UNKNOWN" for key, on in judged.items()}
    return {**health, **extra.get("health", {}), "overall": row.health, "reasons": _reasons(extra)}


def _reasons(extra: Mapping[str, Any]) -> list[JSONish]:
    return [dict(reason) for reason in extra.get("reasons", [])]


def _reservation(row: ServerRow) -> JSONish:
    return {
        "holder": row.reserved_by,
        "mce_cluster": row.reserved_for_mce,
        "infra_env": row.reserved_for_infra_env,
        "namespace": None,
        "workflow_id": None,
        "created_at": None,
        "expires_at": row.reserved_until,
    }


def _openshift(row: ServerRow) -> JSONish:
    member = row.state != "AVAILABLE"
    return {
        "lifecycle_state": row.state,
        "cluster_name": row.cluster_name,
        "mce_name": row.mce,
        "last_reported_at": row.last_seen_at if member else None,
        "reported_by_agent_id": f"agent-{row.id[-8:]}" if member else None,
        "reported_name": row.reported_name,
        "contested_with": row.contested_with,
        "contested_name": row.name if row.contested_with else None,
    }


def _times(row: ServerRow, extra: Mapping[str, Any]) -> JSONish:
    seen = _seen(row)
    return {
        "last_seen_at": row.last_seen_at,
        "stale": row.stale,
        "reachable": row.reachable,
        "unreachable_since": None if row.reachable else seen,
        "unreachable_reason": None
        if row.reachable
        else extra.get("unreachable_reason", "network_unreachable"),
        "updated_at": seen,
        "created_at": CREATED_AT,
    }


def _seen(row: ServerRow) -> datetime:
    return row.last_seen_at or CREATED_AT + timedelta(days=30)


def _history(row: ServerRow, rule: Mapping[str, Any], extra: Mapping[str, Any]) -> list[JSONish]:
    """What server-scan would have recorded to bring the server where its row is."""
    collector = {"type": "SYSTEM", "id": f"collector-{(row.source_provider or 'redfish').lower()}"}
    jobs = {"type": "SYSTEM", "id": "membership-job"}
    events = [
        _event(row, "SERVER_CREATED", CREATED_AT, collector, {}),
        _event(
            row,
            "CLASSIFICATION_CHANGED",
            CREATED_AT + timedelta(minutes=1),
            collector,
            {"from": "UNCLASSIFIED", "to": rule["installation_type"]}
            | {"matched_rule": rule["matched_rule_name"], "matched_field": rule["matched_field"]}
            | {"matched_pattern": rule["matched_pattern"]},
        ),
    ]
    if row.state != "AVAILABLE":
        data = {"from": "AVAILABLE", "to": row.state, "cluster_name": row.cluster_name or row.mce}
        events.append(
            _event(row, "OPENSHIFT_STATE_CHANGED", CREATED_AT + timedelta(days=9), jobs, data)
        )
    if row.health not in ("HEALTHY", "UNKNOWN"):
        data = {"from": "HEALTHY", "to": row.health, "from_reasons": []}
        data["to_reasons"] = _reasons(extra)
        events.append(
            _event(row, "HEALTH_CHANGED", _seen(row) - timedelta(hours=2), collector, data)
        )
    if row.maintenance:
        events.append(_maintenance_event(row))
    return events


def _maintenance_event(row: ServerRow) -> JSONish:
    who = row.maintenance_by or "api-token-admin"
    kind = "TOKEN" if who.startswith("api-token-") else "USER"
    actor = {"type": kind, "id": who, "display": None if kind == "TOKEN" else who}
    at = _seen(row) - timedelta(hours=1)
    return _event(row, "MAINTENANCE_ENABLED", at, actor, {"reason": row.maintenance_reason})


def _event(
    row: ServerRow, kind: str, at: datetime, actor: Mapping[str, Any], data: JSONish
) -> JSONish:
    return {
        "id": "",
        "event_type": kind,
        "server_id": row.id,
        "server_name": row.name,
        "actor": {"display": None, **actor},
        "request_id": None,
        "created_at": at,
        "data": data,
    }


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON")


def default_records_file() -> Path:
    """``dev/fleet-fixtures/server-records.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / RECORDS_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{RECORDS_FILE} not found above this file")


def load_records(path: Path) -> FakeRecords:
    """The fixture's models, rules and servers."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: expected a mapping")
    return FakeRecords(raw.get("models"), raw.get("rules"), raw.get("servers"))
