"""Inventory Management's counting, InfraEnv matching and named-install picks (ADR-0057)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from wingman_day1.domain.inventory import (
    HardwareCount,
    PoolCount,
    candidates,
    infra_env_of,
    mce_inventory,
    named_refusals,
    why_not,
)
from wingman_day1.domain.servers import ServerRow

MCE = "ocp4-prod-mce-site1-a"
R650 = "dell-r650-site1-96c-768gb"
R760 = "dell-r760-site1-64c-512gb"
R760_20TB = "dell-r760-site1-64c-512gb-20tb"
UNTIL = datetime(2026, 11, 13, 18, 0, tzinfo=UTC)


def row(name: str, state: str = "INSTALLED_TO_INVENTORY", **fields: object) -> ServerRow:
    values: dict[str, object] = {
        "id": f"srv_{name}",
        "name": name,
        "state": state,
        "health": "HEALTHY",
        "vendor": "dell",
        "model": "PowerEdge R650",
        "mce": MCE if state != "AVAILABLE" else None,
    }
    values.update(fields)
    return ServerRow(**values)  # ty: ignore[invalid-argument-type]


# ── Which pool a server is in ────────────────────────────────────────────────


def test_a_server_is_in_the_infra_env_its_name_starts_with_the_longest_first() -> None:
    envs = [R760, R760_20TB, R650]
    assert infra_env_of(row(f"ocp-{R760_20TB}-DL1"), MCE, envs) == R760_20TB
    assert infra_env_of(row(f"ocp-{R760}-DL2"), MCE, envs) == R760
    assert infra_env_of(row(f"ocp-{R650}-DL3"), MCE, envs) == R650


def test_the_match_is_case_sensitive_as_the_workflows_pattern() -> None:
    assert infra_env_of(row(f"OCP-{R650}-DL3"), MCE, [R650]) is None


def test_a_held_lock_on_this_mce_names_the_pool_when_the_name_does_not() -> None:
    locked = row("ocp-odd-name", reserved_by="add-server-to-mce", reserved_for_mce=MCE,
                 reserved_for_infra_env=R650)  # fmt: skip
    assert infra_env_of(locked, MCE, []) == R650
    assert infra_env_of(locked, "ocp4-prod-mce-site1-b", []) is None
    assert infra_env_of(row("ocp-odd-name"), MCE, [R650]) is None


# ── Counting an MCE ──────────────────────────────────────────────────────────


def test_an_mce_is_counted_by_state_pool_and_hardware() -> None:
    rows = [
        row(f"ocp-{R650}-A"),
        row(f"ocp-{R650}-B", maintenance=True),
        row(f"ocp-{R760}-C", model="PowerEdge R760"),
        row(f"ocp-{R650}-D", state="INSTALLED", cluster_name="ocp4-prod-lark-site1"),
        row("ocp-mystery-E", vendor="hp", model="DL360"),
        row(f"ocp-{R650}-F", state="AVAILABLE"),
        row(f"ocp-{R650}-G", state="AVAILABLE", reserved_by="add-server-to-mce"),
        row(f"ocp-{R650}-H", state="INSTALLED_TO_INVENTORY", mce="ocp4-other"),
    ]
    found = mce_inventory("site1", MCE, rows, infra_envs=[R760, R650, "empty-pool"])
    assert (found.known, found.servers, found.in_clusters) == (True, 5, 1)
    assert (found.available, found.usable) == (4, 3)
    assert [p.infra_env for p in found.pools] == [R650, R760, "empty-pool", None]
    by_env = {p.infra_env: p for p in found.pools}
    assert by_env[R650] == PoolCount(
        R650, 2, 1, (HardwareCount("dell", "PowerEdge R650", 2, 1),), drawable=1
    )
    assert by_env["empty-pool"] == PoolCount("empty-pool", 0, 0, (), drawable=0)
    assert by_env[None] == PoolCount(None, 1, 1, (HardwareCount("hp", "DL360", 1, 1),), None)


def test_an_mce_server_scan_names_nothing_on_is_unknown_not_zero() -> None:
    found = mce_inventory("site1", MCE, [row("x", mce="ocp4-other")], infra_envs=[R650])
    assert not found.known
    assert found.pools == (PoolCount(R650, 0, 0, (), drawable=0),)


def test_unknown_infra_envs_leave_every_server_under_none_and_say_why() -> None:
    found = mce_inventory(
        "site1", MCE, [row(f"ocp-{R650}-A")], infra_envs=[], infra_envs_error="hub down"
    )
    assert [p.infra_env for p in found.pools] == [None]
    assert found.infra_envs_error == "hub down"


def test_drawable_is_what_a_pool_draw_could_pick() -> None:
    free = [
        row(f"ocp-{R650}-ok", state="AVAILABLE"),
        row(f"ocp-{R650}-sick", state="AVAILABLE", health="WARNING"),
        row(f"ocp-{R650}-gone", state="AVAILABLE", reachable=False),
        row(f"ocp-{R650}-maint", state="AVAILABLE", maintenance=True),
        row(f"ocp-{R760}-other", state="AVAILABLE"),
    ]
    found = mce_inventory("site1", MCE, free, infra_envs=[R650])
    assert found.pools[0].drawable == 1


# ── Named installs ───────────────────────────────────────────────────────────


def test_locked_maintenance_and_contested_servers_are_not_offered_with_why() -> None:
    locked = row("l", "AVAILABLE", reserved_by="uninstall-server-from-hc", reserved_until=UNTIL)
    assert why_not(locked) == "locked by uninstall-server-from-hc until 2026-11-13T18:00:00+00:00"
    assert why_not(row("m", "AVAILABLE", maintenance=True)) == "in maintenance"
    assert why_not(row("c", "AVAILABLE", contested=True)) == "contested: two clusters claim it"
    assert why_not(row("w", "AVAILABLE", health="WARNING")) is None, "health is shown, not refused"


def test_candidates_are_the_pools_available_servers_offered_first() -> None:
    rows = [
        row(f"ocp-{R650}-B", "AVAILABLE", reserved_by="add-server-to-mce"),
        row(f"ocp-{R650}-C", "AVAILABLE"),
        row(f"ocp-{R650}-A", "AVAILABLE", maintenance=True),
        row(f"ocp-{R650}-D"),
        row(f"ocp-{R760}-E", "AVAILABLE"),
    ]
    found = candidates(rows, R650)
    assert [(c.row.name[-1], c.offered) for c in found] == [
        ("C", True),
        ("A", False),
        ("B", False),
    ]


def test_a_named_install_refuses_each_server_it_cannot_offer() -> None:
    rows = [
        row(f"ocp-{R650}-ok", "AVAILABLE"),
        row(f"ocp-{R650}-locked", "AVAILABLE", reserved_by="add-server-to-mce"),
        row(f"ocp-{R650}-in", "INSTALLED"),
        row(f"ocp-{R760}-other", "AVAILABLE"),
    ]
    names = [
        f"OCP-{R650}-OK".lower(),
        f"ocp-{R650}-locked",
        f"ocp-{R650}-in",
        f"ocp-{R760}-other",
        "nope",
        f"ocp-{R650}-ok",
    ]
    assert named_refusals(names, rows, R650) == [
        f"ocp-{R650}-locked: locked by add-server-to-mce",
        f"ocp-{R650}-in: INSTALLED, not AVAILABLE",
        f"ocp-{R760}-other: not named ocp-{R650}…",
        "nope: server-scan has no such server",
        f"ocp-{R650}-ok: named twice",
    ]
    assert named_refusals([f"ocp-{R650}-ok"], rows, R650) == []


def test_a_lock_counts_only_while_server_scan_says_it_is_held() -> None:
    expired = dataclasses.replace(row(f"ocp-{R650}-x", "AVAILABLE"), reserved_by=None)
    assert why_not(expired) is None
