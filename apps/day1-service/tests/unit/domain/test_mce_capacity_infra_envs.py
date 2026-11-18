"""Free servers for nodepools drawing from several InfraEnvs (ADR-0064): none counted twice."""

from __future__ import annotations

from dataclasses import replace

from wingman_day1.domain.machines import BMH_LABEL, INFRA_ENV_LABEL, AgentObservation
from wingman_day1.domain.mce_capacity import (
    NodeTypeSupply,
    Supply,
    infra_envs_in,
    judged_together,
    node_type,
    node_type_supply,
    summed_needs,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import Condition

MCE = "ocp4-prod-mce-site1-a"
A, B, C = "infraenv-a", "infraenv-b", "infraenv-c"
FREE = (
    Condition("Bound", "False", "Unbound"),
    Condition("Connected", "True"),
    Condition("Validated", "True"),
)


def agents(infra_env: str, count: int, *, prefix: str = "") -> list[AgentObservation]:
    """``count`` free Agents in ``infra_env``, each with its server in server-scan."""
    return [
        AgentObservation(
            name=f"agent-{prefix}{infra_env}-{i}",
            labels={INFRA_ENV_LABEL: infra_env, BMH_LABEL: f"{prefix}{infra_env}-{i}"},
            approved=True,
            conditions=FREE,
        )
        for i in range(count)
    ]


def rows(found: list[AgentObservation], **changes: object) -> list[ServerRow]:
    base = ServerRow(id="", name="", state="INSTALLED_TO_INVENTORY", health="HEALTHY", mce=MCE)
    return [replace(base, id=f"srv_{a.name}", name=a.labels[BMH_LABEL], **changes) for a in found]


def test_a_node_type_of_several_infraenvs_is_sorted_and_read_back() -> None:
    assert node_type([B, A, B]) == f"{A} + {B}"
    assert infra_envs_in(f"{A} + {B}") == (A, B)
    assert node_type([A]) == A


def test_needs_of_the_same_infraenvs_are_summed_whatever_their_order() -> None:
    assert summed_needs([(f"{B} + {A}", 2), (f"{A} + {B}", 1), (A, 1)]) == (
        (A, 1),
        (f"{A} + {B}", 3),
    )


def test_node_types_that_share_an_infraenv_are_judged_together() -> None:
    needs = [(A, 1), (C, 2), (f"{A} + {B}", 3), ("other", 1)]
    assert judged_together(needs) == [[(A, 1), (f"{A} + {B}", 3)], [(C, 2)], [("other", 1)]]
    bridged = [(A, 1), (C, 1), (f"{A} + {C}", 1)]
    assert judged_together(bridged) == [[(A, 1), (C, 1), (f"{A} + {C}", 1)]]


def test_a_multi_infraenv_nodepool_counts_the_free_servers_of_all_its_infraenvs() -> None:
    found = agents(A, 2) + agents(B, 1)
    (supply,) = node_type_supply([(f"{A} + {B}", 3)], found, rows(found))
    assert supply == NodeTypeSupply(f"{A} + {B}", 3, free_agents=3, healthy=3)
    assert supply.status is Supply.ENOUGH
    assert supply.infra_envs == (A, B)
    assert supply.detail == f"{A} + {B}: 3 healthy free of 3 needed"


def test_two_nodepools_that_share_an_infraenv_never_count_a_server_twice() -> None:
    """Three free servers in A; one nodepool draws on A, the other on A and B (none free)."""
    found = agents(A, 3)
    (supply,) = node_type_supply([(A, 2), (f"{A} + {B}", 2)], found, rows(found))
    assert (supply.infra_env, supply.needed, supply.free_agents) == (f"{A} + {B}", 4, 3)
    assert supply.status is Supply.SHORT
    alone = node_type_supply([(A, 2)], found, rows(found)) + node_type_supply(
        [(f"{A} + {B}", 2)], found, rows(found)
    )
    assert all(s.status is Supply.ENOUGH for s in alone), "separately, each would pass"


def test_a_nodepool_that_draws_only_on_a_short_infraenv_is_short_however_many_the_other_has() -> (
    None
):
    found = agents(A, 1) + agents(B, 5)
    (supply,) = node_type_supply([(A, 2), (f"{A} + {B}", 1)], found, rows(found))
    assert (supply.free_agents, supply.needed) == (6, 3), "all of it would hold"
    assert supply.status is Supply.SHORT
    assert supply.within == NodeTypeSupply(A, 2, free_agents=1, healthy=1)
    assert supply.detail == (
        f"{A} + {B}: 6 healthy free of 3 needed; of those, {A}: 1 healthy free of 2 needed"
    )


def test_every_part_is_checked_not_only_each_need_alone() -> None:
    """A on A, B on A+B, C on B+C: A and B together need two from A and B, which have one."""
    found = agents(A, 1) + agents(C, 5)
    needs = [(A, 1), (f"{A} + {B}", 1), (f"{B} + {C}", 1)]
    (supply,) = node_type_supply(needs, found, rows(found))
    assert supply.status is Supply.SHORT
    assert supply.within is not None
    assert (supply.within.infra_env, supply.within.needed) == (f"{A} + {B}", 2)


def test_health_unknown_in_a_part_makes_the_row_unknown_not_short() -> None:
    found = agents(A, 2) + agents(B, 3)
    known = rows(found[:1]) + rows(found[2:])  # A's second server is not in server-scan
    assert node_type_supply([(f"{A} + {B}", 4)], found, known)[0].status is Supply.ENOUGH
    (supply,) = node_type_supply([(A, 2), (f"{A} + {B}", 2)], found, known)
    assert supply.status is Supply.UNKNOWN
    assert supply.within is not None and supply.within.infra_env == A


def test_unread_agents_leave_a_shared_row_unknown() -> None:
    (supply,) = node_type_supply([(A, 1), (f"{A} + {B}", 1)], None, None)
    assert supply == NodeTypeSupply(f"{A} + {B}", 2, None, None)
    assert supply.status is Supply.UNKNOWN


def test_without_server_scan_the_free_agents_of_all_infraenvs_count() -> None:
    found = agents(A, 1) + agents(B, 1)
    (supply,) = node_type_supply([(f"{A} + {B}", 2)], found, None, server_scan=False)
    assert supply == NodeTypeSupply(f"{A} + {B}", 2, 2, None, health_checked=False)
    assert supply.status is Supply.ENOUGH
