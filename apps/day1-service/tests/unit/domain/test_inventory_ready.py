"""A pool's free servers, ready or needing a fix, and its total (ADR-0057's 3.38.0 amendment)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.add_server import WAIVER_NEEDS_NAMES, AddServerRequest
from wingman_day1.domain.inventory import candidates, health_problems, mce_inventory
from wingman_day1.domain.servers import ServerRow

MCE = "ocp4-prod-mce-site1-a"
R650 = "dell-r650-site1-96c-768gb"
R760 = "dell-r760-site1-64c-512gb"
R760_20TB = "dell-r760-site1-64c-512gb-20tb"


def free(name: str, **fields: object) -> ServerRow:
    values: dict[str, object] = {"id": f"srv_{name}", "name": name, "state": "AVAILABLE"}
    values["health"] = "HEALTHY"
    values.update(fields)
    return ServerRow(**values)  # ty: ignore[invalid-argument-type]


def agent(name: str) -> ServerRow:
    return ServerRow(id=f"srv_{name}", name=name, state="INSTALLED_TO_INVENTORY", health="HEALTHY",
                     mce=MCE)  # fmt: skip


# ── Why a server needs a fix ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fields", "problems"),
    [
        ({}, ()),
        ({"health": "WARNING"}, ("health WARNING",)),
        ({"health": "CRITICAL"}, ("health CRITICAL",)),
        ({"health": "UNKNOWN", "reachable": False}, ("health UNKNOWN", "BMC unreachable")),
        ({"reachable": False}, ("BMC unreachable",)),
        ({"stale": True}, ()),
    ],
)
def test_a_server_needs_a_fix_for_its_health_or_its_bmc_and_nothing_else(
    fields: dict[str, object], problems: tuple[str, ...]
) -> None:
    assert health_problems(free("x", **fields)) == problems


# ── Counting a pool ──────────────────────────────────────────────────────────


def test_a_pools_offered_free_servers_are_ready_or_need_a_fix_and_the_rest_are_neither() -> None:
    rows = [
        agent(f"ocp-{R650}-in-pool"),
        free(f"ocp-{R650}-ok"),
        free(f"ocp-{R650}-sick", health="CRITICAL"),
        free(f"ocp-{R650}-gone", reachable=False),
        free(f"ocp-{R650}-locked", reserved_by="add-server-to-mce", health="CRITICAL"),
        free(f"ocp-{R650}-maint", maintenance=True),
        free(f"ocp-{R650}-contested", contested_with="ocp4-prod-other-site1"),
        free(f"ocp-{R760}-other", health="CRITICAL"),
    ]
    [pool] = mce_inventory("site1", MCE, rows, infra_envs=[R650]).pools
    assert (pool.available, pool.ready, pool.needs_fix) == (1, 1, 2)
    assert pool.total == 4, "available + ready + needs fix; locked, maintenance, contested left out"


def test_the_pool_of_no_infra_env_has_no_free_servers_and_its_total_is_its_available() -> None:
    found = mce_inventory("site1", MCE, [agent("ocp-mystery-1")], infra_envs=[R650])
    none = next(p for p in found.pools if p.infra_env is None)
    assert (none.ready, none.needs_fix, none.total) == (None, None, 1)


def test_an_mce_counts_a_free_server_named_for_two_of_its_pools_once() -> None:
    rows = [
        agent(f"ocp-{R650}-in-pool"),
        free(f"ocp-{R760_20TB}-both"),  # ^ocp-<R760> draws it too
        free(f"ocp-{R760}-sick", health="MAJOR"),
        free(f"ocp-{R650}-ok"),
    ]
    found = mce_inventory("site1", MCE, rows, infra_envs=[R760, R760_20TB, R650])
    by_env = {p.infra_env: p for p in found.pools}
    assert (by_env[R760].ready, by_env[R760].needs_fix) == (1, 1)
    assert (by_env[R760_20TB].ready, by_env[R760_20TB].needs_fix) == (1, 0)
    assert (found.ready, found.needs_fix) == (2, 1)
    assert found.total == 1 + 2 + 1


def test_an_mce_with_no_pools_has_nothing_free() -> None:
    found = mce_inventory("site1", MCE, [free(f"ocp-{R650}-ok")], infra_envs=[])
    assert (found.ready, found.needs_fix, found.total) == (0, 0, 0)


# ── A pool's servers, for the list and the picker ────────────────────────────


def test_candidates_list_the_ready_then_those_that_need_a_fix_then_the_rest() -> None:
    rows = [
        free(f"ocp-{R650}-a-locked", reserved_by="add-server-to-mce"),
        free(f"ocp-{R650}-b-sick", health="CRITICAL", reachable=False),
        free(f"ocp-{R650}-c-ok"),
        free(f"ocp-{R650}-d-warning", health="WARNING"),
        free(f"ocp-{R650}-e-ok"),
    ]
    found = candidates(rows, R650)
    assert [(c.row.name.split("-")[-2], c.ready, c.offered) for c in found] == [
        ("c", True, True),
        ("e", True, True),
        ("b", False, True),
        ("d", False, True),
        ("a", False, False),
    ]
    sick = found[2]
    assert sick.health_problems == ("health CRITICAL", "BMC unreachable")


# ── The waiver needs names ───────────────────────────────────────────────────


def test_a_request_waives_health_checks_only_for_named_servers() -> None:
    with pytest.raises(ValueError, match="only for servers named"):
        AddServerRequest(MCE, R650, None, count=2, allow_unhealthy=True)
    named = AddServerRequest(MCE, R650, None, server_names=("x",), allow_unhealthy=True)
    assert named.allow_unhealthy
    assert "pool draw" in WAIVER_NEEDS_NAMES
