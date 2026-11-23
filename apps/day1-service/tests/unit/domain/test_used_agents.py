"""herzi's used Agents: the keys, which Agents are used, placement's count."""

from __future__ import annotations

from dataclasses import replace

from wingman_day1.domain.cluster_file import WorkflowKeys
from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    INFRA_ENV_LABEL,
    AgentObservation,
)
from wingman_day1.domain.mce_capacity import NodeTypeSupply, Supply, node_type_supply
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import Condition
from wingman_day1.domain.used_agents import HERZI_LABEL, used_label, used_labels

DELL = "dell-r660"
MCE = "ocp4-prod-mce-site1-a"
FREE = (
    Condition("Bound", "False", "Unbound"),
    Condition("Connected", "True"),
    Condition("Validated", "True"),
)


def agent(name: str, *, used: str | None = None, bound: bool = False) -> AgentObservation:
    labels = {INFRA_ENV_LABEL: DELL, BMH_LABEL: name}
    if used is not None:
        labels[used] = "true"
    if bound:
        labels[AGENT_MACHINE_REF_LABEL] = f"am-{name}"
    return AgentObservation(name=f"agent-{name}", labels=labels, approved=True, conditions=FREE)


def row(name: str) -> ServerRow:
    return ServerRow(id=f"srv_{name}", name=name, state="INSTALLED_TO_INVENTORY", health="HEALTHY")


# ── The keys, from one place ─────────────────────────────────────────────────


def test_the_keys_are_the_excluded_labels_else_herzis() -> None:
    assert used_labels(()) == (HERZI_LABEL,) == ("redbull.io/ever-installed",)
    assert used_labels(("example.com/used", "example.com/old")) == (
        "example.com/used",
        "example.com/old",
    )
    assert WorkflowKeys().used_agent_labels == (HERZI_LABEL,)
    assert WorkflowKeys(excluded_agent_labels=("example.com/used",)).used_agent_labels == (
        "example.com/used",
    )


def test_an_agent_is_used_by_the_keys_presence_whatever_its_value() -> None:
    marked = replace(agent("s1"), labels={**agent("s1").labels, HERZI_LABEL: ""})
    assert used_label(marked, (HERZI_LABEL,)) == HERZI_LABEL
    assert used_label(agent("s2"), (HERZI_LABEL,)) is None
    assert used_label(agent("s3", used="example.com/used"), (HERZI_LABEL,)) is None


# ── Placement: a used Agent is no free server ────────────────────────────────


def test_placement_leaves_used_free_agents_out_and_counts_them_apart() -> None:
    agents = [
        agent("s1"),
        agent("s2", used=HERZI_LABEL),
        agent("s3", used=HERZI_LABEL),
        agent("s4", used=HERZI_LABEL, bound=True),
    ]
    rows = [row("s1"), row("s2"), row("s3"), row("s4")]
    (dell,) = node_type_supply([(DELL, 2)], agents, rows, used_labels=(HERZI_LABEL,))
    assert dell == NodeTypeSupply(DELL, 2, free_agents=1, healthy=1, used=2)
    assert dell.status is Supply.SHORT, "two used Agents would have made it enough"
    assert dell.detail == (
        "dell-r660: 1 healthy free of 2 needed; 2 used, left out (herzi removes them)"
    )


def test_without_used_labels_every_free_agent_counts_as_before() -> None:
    agents = [agent("s1"), agent("s2", used=HERZI_LABEL)]
    (dell,) = node_type_supply([(DELL, 2)], agents, [row("s1"), row("s2")])
    assert (dell.free_agents, dell.healthy, dell.used, dell.status) == (2, 2, 0, Supply.ENOUGH)


def test_the_used_count_is_said_without_server_scan_too() -> None:
    agents = [agent("s1"), agent("s2", used=HERZI_LABEL)]
    (dell,) = node_type_supply(
        [(DELL, 1)], agents, None, server_scan=False, used_labels=(HERZI_LABEL,)
    )
    assert dell == NodeTypeSupply(DELL, 1, 1, None, health_checked=False, used=1)
    assert dell.detail.endswith("; 1 used, left out (herzi removes it)")


def test_another_key_marks_used_agents_when_the_deployment_names_it() -> None:
    agents = [agent("s1", used=HERZI_LABEL), agent("s2", used="example.com/used")]
    (dell,) = node_type_supply([(DELL, 1)], agents, None, used_labels=("example.com/used",))
    assert (dell.free_agents, dell.used) == (1, 1), "the setting is the one source of the keys"

