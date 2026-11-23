"""Inventory Management's used Agents: apart from the available ones, never in a total."""

from __future__ import annotations

from wingman_day1.domain.infra_env_pools import InfraEnvObservation, Pool
from wingman_day1.domain.inventory import mce_inventory
from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    INFRA_ENV_LABEL,
    AgentObservation,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import Condition
from wingman_day1.domain.used_agents import HERZI_LABEL, UsedAgent, used_servers

MCE = "ocp4-prod-mce-five-a"
R650 = "r650-mtl-az1"
KEYS = (HERZI_LABEL,)
FREE = (Condition("Bound", "False", "Unbound"),)
POOL = Pool.observed(
    InfraEnvObservation(
        R650,
        {"redbull.io/flavor": "r650", "redbull.io/size": "mtl", "redbull.io/site": "five"},
    )
)


def row(name: str, **fields: object) -> ServerRow:
    values: dict[str, object] = {
        "id": f"srv_{name}",
        "name": name,
        "state": "INSTALLED_TO_INVENTORY",
        "health": "HEALTHY",
        "mce": MCE,
        "macs": (),
    }
    values.update(fields)
    return ServerRow(**values)  # ty: ignore[invalid-argument-type]


def agent(
    bmh: str, *, used: bool = True, held: bool = False, infra_env: str = R650
) -> AgentObservation:
    labels = {INFRA_ENV_LABEL: infra_env, BMH_LABEL: bmh}
    if used:
        labels[HERZI_LABEL] = "true"
    if held:
        labels[AGENT_MACHINE_REF_LABEL] = "am-1"
    return AgentObservation(name=f"agent-{bmh}", labels=labels, approved=True, conditions=FREE)


def test_used_servers_are_the_retiring_agents_joined_to_their_rows() -> None:
    rows = [row("ocp-r650-mtl-five-dl1"), row("ocp-r650-mtl-five-dl2")]
    found = used_servers(
        [
            agent("ocp-r650-mtl-five-dl2"),
            agent("ocp-r650-mtl-five-dl1", used=False),
            agent("ocp-r650-mtl-five-dl3", held=True),
            agent("ghost-host"),
        ],
        KEYS,
        rows,
    )
    assert found == [
        UsedAgent("ghost-host", R650, None),
        UsedAgent("ocp-r650-mtl-five-dl2", R650, rows[1]),
    ], "a used Agent server-scan has no row for still counts, by its BareMetalHost's name"


def test_a_used_agents_row_is_never_available_and_never_in_a_total() -> None:
    rows = [
        row("ocp-r650-mtl-five-dl1"),
        row("ocp-r650-mtl-five-dl2"),
        row("ocp-r650-mtl-five-dl3"),
    ]
    used = used_servers([agent("ocp-r650-mtl-five-dl2")], KEYS, rows)
    counted = mce_inventory("five", MCE, rows, pools=[POOL], used=used)
    (pool,) = counted.pools
    assert (counted.available, counted.total) == (2, 2)
    assert (pool.available, pool.total, pool.used) == (2, 2, ("ocp-r650-mtl-five-dl2",))
    assert counted.used == tuple(used)


def test_a_used_agent_of_an_infra_env_no_pool_lists_gets_its_own_row() -> None:
    used = used_servers(
        [agent("dl9", infra_env="g12-mtl-az1"), agent("dl8", infra_env="")], KEYS, []
    )
    counted = mce_inventory("five", MCE, [], pools=[POOL], used=used)
    assert [(p.infra_env, p.used) for p in counted.pools] == [
        ("g12-mtl-az1", ("dl9",)),
        (R650, ()),
        (None, ("dl8",)),
    ]


def test_without_a_read_the_used_agents_are_unknown_and_the_counts_as_before() -> None:
    rows = [row("ocp-r650-mtl-five-dl1")]
    counted = mce_inventory("five", MCE, rows, pools=[POOL], used_error="Unavailable: down")
    assert (counted.used, counted.used_error, counted.available) == (None, "Unavailable: down", 1)
    assert mce_inventory("five", MCE, rows, pools=[POOL]).used is None
