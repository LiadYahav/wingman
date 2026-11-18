"""Which server update-nodepool takes a Machine to be: what a scale-down names (ADR-0062)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.machines import BMH_LABEL, AgentObservation, machine_server

SERVER = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0102"


@pytest.mark.parametrize(
    ("agent", "node", "expected"),
    [
        # The BareMetalHost first, as add-server-to-mce names it after the server
        (
            AgentObservation("a1", labels={BMH_LABEL: SERVER}, hostname="other"),
            "node-x",
            SERVER.lower(),
        ),
        # No label: the Agent's hostname
        (AgentObservation("a1", hostname="Worker-7.Example"), "node-x", "worker-7.example"),
        # No Agent (or one that says nothing): the Machine's Node
        (None, "Worker-7", "worker-7"),
        (AgentObservation("a1", labels={BMH_LABEL: ""}), "worker-7", "worker-7"),
        # Nothing to go by: a Machine still provisioning cannot be named
        (None, None, None),
        (AgentObservation("a1"), None, None),
    ],
)
def test_a_machine_is_its_bmh_else_its_agents_hostname_else_its_node_lowercased(
    agent: AgentObservation | None, node: str | None, expected: str | None
) -> None:
    assert machine_server(agent, node) == expected
