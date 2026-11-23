"""Inventory Management's counting, InfraEnv matching and named-install picks (ADR-0057).

The InfraEnvs and servers are named by the platform's naming convention
(2026-11-22): InfraEnv ``<flavor>-<size>-<zone>``, server
``ocp-<flavor>-<size>-<site>-<serial>``, a pool's servers named by its agentLabels.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from wingman_day1.domain.infra_env_pools import InfraEnvObservation, Pool
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

MCE = "ocp4-prod-mce-five-a"
R650 = "r650-mtl-az1"
R760 = "r760-mtl-az1"
R760_AZ2 = "r760-mtl-az2"
UNTIL = datetime(2026, 11, 13, 18, 0, tzinfo=UTC)


def pool(name: str, *, site: str = "five") -> Pool:
    """The pool of an InfraEnv labelled as the convention says, from its name's first two words."""
    flavor, size, zone = name.split("-")
    labels = {
        "redbull.io/flavor": flavor,
        "redbull.io/size": size,
        "redbull.io/site": site,
        "topology.kubernetes.io/zone": zone,
    }
    return Pool.observed(InfraEnvObservation(name, labels))


def server(infra_env: str, serial: str) -> str:
    """The name of a server the InfraEnv's pool draws: ``ocp-<flavor>-<size>-five-<serial>``."""
    flavor, size, _zone = infra_env.split("-")
    return f"ocp-{flavor}-{size}-five-{serial}"


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


def test_a_server_is_in_the_one_infra_env_whose_labels_name_it() -> None:
    pools = [pool(R760), pool(R650)]
    assert infra_env_of(row(server(R760, "dl1")), MCE, pools) == R760
    assert infra_env_of(row(server(R650, "dl3")), MCE, pools) == R650
    assert infra_env_of(row("ocp-r650-mtl-fivex-dl4"), MCE, pools) is None, "the prefix ends in -"


def test_two_zones_of_one_flavor_name_the_same_servers_so_neither_is_guessed() -> None:
    pools = [pool(R760), pool(R760_AZ2)]
    assert infra_env_of(row(server(R760, "dl1")), MCE, pools) is None
    locked = row(server(R760, "dl1"), reserved_by="add-server-to-mce", reserved_for_mce=MCE,
                 reserved_for_infra_env=R760_AZ2)  # fmt: skip
    assert infra_env_of(locked, MCE, pools) == R760_AZ2, "the held lock says which"


def test_the_match_is_case_sensitive_as_the_workflows_pattern() -> None:
    assert infra_env_of(row(server(R650, "dl3").upper()), MCE, [pool(R650)]) is None


def test_a_pool_whose_labels_are_unread_names_no_server() -> None:
    assert infra_env_of(row(server(R650, "dl3")), MCE, [Pool.unread(R650)]) is None


def test_a_held_lock_on_this_mce_names_the_pool_when_the_name_does_not() -> None:
    locked = row("ocp-odd-name", reserved_by="add-server-to-mce", reserved_for_mce=MCE,
                 reserved_for_infra_env=R650)  # fmt: skip
    assert infra_env_of(locked, MCE, []) == R650
    assert infra_env_of(locked, "ocp4-prod-mce-five-b", []) is None
    assert infra_env_of(row("ocp-odd-name"), MCE, [pool(R650)]) is None


# ── Counting an MCE ──────────────────────────────────────────────────────────


def test_an_mce_is_counted_by_state_pool_and_hardware() -> None:
    rows = [
        row(server(R650, "a")),
        row(server(R650, "b"), maintenance=True),
        row(server(R760, "c"), model="PowerEdge R760"),
        row(server(R650, "d"), state="INSTALLED", cluster_name="ocp4-prod-lark-five-a"),
        row("ocp-mystery-e", vendor="hp", model="DL360"),
        row(server(R650, "f"), state="AVAILABLE"),
        row(server(R650, "g"), state="AVAILABLE", reserved_by="add-server-to-mce"),
        row(server(R650, "h"), state="INSTALLED_TO_INVENTORY", mce="ocp4-other"),
    ]
    empty = pool("e1-mtl-az1")
    found = mce_inventory("five", MCE, rows, pools=[pool(R760), pool(R650), empty])
    assert (found.known, found.servers, found.in_clusters) == (True, 5, 1)
    assert (found.available, found.usable) == (4, 3)
    assert [p.infra_env for p in found.pools] == ["e1-mtl-az1", R650, R760, None]
    by_env = {p.infra_env: p for p in found.pools}
    assert by_env[R650] == PoolCount(
        R650,
        2,
        1,
        (HardwareCount("dell", "PowerEdge R650", 2, 1),),
        ready=1,
        needs_fix=0,
        server_prefix="ocp-r650-mtl-five-",
    )
    assert by_env["e1-mtl-az1"] == PoolCount(
        "e1-mtl-az1", 0, 0, (), ready=0, needs_fix=0, server_prefix="ocp-e1-mtl-five-"
    )
    assert by_env[None] == PoolCount(
        None, 1, 1, (HardwareCount("hp", "DL360", 1, 1),), ready=None, needs_fix=None
    )


def test_a_pool_whose_infra_env_lacks_a_label_says_so_and_counts_no_free_server() -> None:
    lacking = Pool.observed(InfraEnvObservation(R650, {"redbull.io/flavor": "r650"}))
    rows = [row(server(R650, "f"), state="AVAILABLE")]
    [counted] = mce_inventory("five", MCE, rows, pools=[lacking]).pools
    assert (counted.server_prefix, counted.ready, counted.needs_fix) == (None, None, None)
    assert counted.label_problems == ("redbull.io/size is missing", "redbull.io/site is missing")


def test_an_mce_server_scan_names_nothing_on_is_unknown_not_zero() -> None:
    found = mce_inventory("five", MCE, [row("x", mce="ocp4-other")], pools=[pool(R650)])
    assert not found.known
    assert found.pools == (
        PoolCount(R650, 0, 0, (), ready=0, needs_fix=0, server_prefix="ocp-r650-mtl-five-"),
    )


def test_unknown_infra_envs_leave_every_server_under_none_and_say_why() -> None:
    found = mce_inventory(
        "five", MCE, [row(server(R650, "a"))], pools=[], infra_envs_error="hub down"
    )
    assert [p.infra_env for p in found.pools] == [None]
    assert found.infra_envs_error == "hub down"


def test_pools_named_by_the_day1_files_count_their_locked_servers_only() -> None:
    locked = row("ocp-x-1", reserved_by="add-server-to-mce", reserved_for_mce=MCE,
                 reserved_for_infra_env=R650)  # fmt: skip
    rows = [locked, row(server(R650, "a")), row(server(R650, "f"), state="AVAILABLE")]
    found = mce_inventory("five", MCE, rows, pools=[Pool.unread(R650)], infra_envs_from="day1")
    by_env = {p.infra_env: p for p in found.pools}
    assert (by_env[R650].available, by_env[R650].ready, by_env[R650].server_prefix) == (
        1,
        None,
        None,
    )
    assert by_env[None].available == 1
    assert (found.ready, found.needs_fix) == (0, 0)


def test_ready_is_what_a_pool_draw_could_pick() -> None:
    free = [
        row(server(R650, "ok"), state="AVAILABLE"),
        row(server(R650, "sick"), state="AVAILABLE", health="WARNING"),
        row(server(R650, "gone"), state="AVAILABLE", reachable=False),
        row(server(R650, "maint"), state="AVAILABLE", maintenance=True),
        row(server(R760, "other"), state="AVAILABLE"),
    ]
    found = mce_inventory("five", MCE, free, pools=[pool(R650)])
    assert (found.pools[0].ready, found.pools[0].needs_fix) == (1, 2), "maintenance is neither"


# ── Named installs ───────────────────────────────────────────────────────────


def test_locked_maintenance_and_contested_servers_are_not_offered_with_why() -> None:
    locked = row("l", "AVAILABLE", reserved_by="uninstall-server-from-hc", reserved_until=UNTIL)
    assert why_not(locked) == "locked by uninstall-server-from-hc until 2026-11-13T18:00:00+00:00"
    assert why_not(row("m", "AVAILABLE", maintenance=True)) == "in maintenance"
    assert (
        why_not(row("c", "AVAILABLE", contested_with="ocp4-prod-other-five-a"))
        == "contested: two clusters claim it"
    )
    assert why_not(row("w", "AVAILABLE", health="WARNING")) is None, "health is shown, not refused"


def test_candidates_are_the_pools_available_servers_offered_first() -> None:
    rows = [
        row(server(R650, "b"), "AVAILABLE", reserved_by="add-server-to-mce"),
        row(server(R650, "c"), "AVAILABLE"),
        row(server(R650, "a"), "AVAILABLE", maintenance=True),
        row(server(R650, "d")),
        row(server(R760, "e"), "AVAILABLE"),
    ]
    found = candidates(rows, pool(R650))
    assert [(c.row.name[-1], c.offered) for c in found] == [
        ("c", True),
        ("a", False),
        ("b", False),
    ]


def test_without_its_labels_a_pool_lists_every_free_server() -> None:
    rows = [row(server(R650, "c"), "AVAILABLE"), row(server(R760, "e"), "AVAILABLE"), row("x")]
    assert [c.row.name for c in candidates(rows, Pool.unread(R650))] == [
        server(R650, "c"),
        server(R760, "e"),
    ]


def test_a_named_install_refuses_each_server_it_cannot_offer() -> None:
    rows = [
        row(server(R650, "ok"), "AVAILABLE"),
        row(server(R650, "locked"), "AVAILABLE", reserved_by="add-server-to-mce"),
        row(server(R650, "in"), "INSTALLED"),
        row(server(R760, "other"), "AVAILABLE"),
    ]
    names = [
        server(R650, "ok").upper().lower(),
        server(R650, "locked"),
        server(R650, "in"),
        server(R760, "other"),
        "nope",
        server(R650, "ok"),
    ]
    assert named_refusals(names, rows) == [
        f"{server(R650, 'locked')}: locked by add-server-to-mce",
        f"{server(R650, 'in')}: INSTALLED, not AVAILABLE",
        "nope: server-scan has no such server",
        f"{server(R650, 'ok')}: named twice",
    ], "another pool's server may be named: the workflow does not match names to the pool"
    assert named_refusals([server(R650, "ok")], rows) == []


def test_a_lock_counts_only_while_server_scan_says_it_is_held() -> None:
    expired = dataclasses.replace(row(server(R650, "x"), "AVAILABLE"), reserved_by=None)
    assert why_not(expired) is None
