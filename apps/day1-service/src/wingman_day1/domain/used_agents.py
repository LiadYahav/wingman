"""herzi's used Agents: free Agents no NodePool may take, which herzi removes from the MCE.

herzi's plan to retire used servers (team-redbull/herzi, branch
``docs/retire-used-servers-plan``, ``578edf1``, its owner's decisions
approved; herzi's ``main`` labels nothing yet): herzi labels every Agent
bound to a tenant cluster ``redbull.io/ever-installed: "true"`` as it binds,
and once such an Agent is free again it starts ``remove-server-from-mce`` for
it. A labelled free Agent is **retiring**: never spare to herzi, and never
bound again, because every NodePool excludes the label (``{key:
redbull.io/ever-installed, operator: DoesNotExist}``, ADR-0065). herzi holds
an Agent's removal while any Agent NodePool whose selector matches it lacks
that exclusion (its rule 6) and while its pool is paused (rule 7).

Which keys mark a used Agent comes from one place, :func:`used_labels`: the
deployment's ``DAY1_EXCLUDED_AGENT_LABELS`` when it is set (what its NodePools
exclude), else herzi's label. An Agent that carries no such key is untouched,
so nothing changes until herzi labels Agents. Placement counts a used Agent as
no free server (ADR-0050), Inventory Management shows it apart from the
available ones (ADR-0057), and the agent nodepools that do not exclude every
key are listed per MCE (:func:`unguarded`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.excluded_agent_labels import keys_of, nodepool_name
from wingman_day1.domain.machines import AgentObservation
from wingman_day1.domain.node_pools import ServerFinder, why_not_free
from wingman_day1.domain.nodepool_infra_envs import (
    REPLACE,
    additional_of,
    infra_envs_of,
    nodepool_entries,
)
from wingman_day1.domain.servers import ServerRow

HERZI_LABEL: Final = "redbull.io/ever-installed"
"""herzi's mark on an Agent that was ever bound to a cluster (the user's choice, 2026-11-23)."""
_KUBEVIRT: Final = "kubevirt"


def used_labels(excluded: Sequence[str]) -> tuple[str, ...]:
    """The keys that mark a used Agent: the deployment's excluded labels, else herzi's."""
    return tuple(excluded) or (HERZI_LABEL,)


def used_label(agent: AgentObservation, keys: Sequence[str]) -> str | None:
    """The first of ``keys`` the Agent carries, whatever its value; ``None`` when none.

    Key presence, as the NodePool's ``DoesNotExist`` and herzi test it.
    """
    return next((key for key in keys if key in agent.labels), None)


def retiring(agent: AgentObservation, keys: Sequence[str]) -> bool:
    """Used and bound to nothing: herzi's to remove, and no NodePool that excludes it takes it."""
    return used_label(agent, keys) is not None and why_not_free(agent) != "bound"


@dataclass(frozen=True, slots=True)
class UsedAgent:
    """A retiring Agent of an MCE, as Inventory Management lists it."""

    server: str
    """server-scan's name for it, else its BareMetalHost's, else the Agent's."""
    infra_env: str | None
    """Its InfraEnv label; ``None`` when it has none."""
    row: ServerRow | None
    """server-scan's row for it (an available server there), when one is found."""


def used_servers(
    agents: Sequence[AgentObservation], keys: Sequence[str], rows: Sequence[ServerRow]
) -> list[UsedAgent]:
    """The retiring Agents among ``agents``, each joined to its row in ``rows`` when there is one.

    Joined as the nodes view joins an Agent (``ServerFinder``: the
    BareMetalHost's name, then MAC, then serial), sorted by name.
    """
    finder = ServerFinder(rows)
    found: list[UsedAgent] = []
    for agent in agents:
        if not retiring(agent, keys):
            continue
        row = finder.find(agent)
        name = row.name if row is not None else agent.bmh or agent.hostname or agent.name
        found.append(UsedAgent(name, agent.infra_env, row))
    return sorted(found, key=lambda used: used.server)


@dataclass(frozen=True, slots=True)
class Unguarded:
    """An agent nodepool of a cluster file that does not exclude every used-Agent key."""

    cluster: str
    """The cluster's name in the day1 repo."""
    nodepool: str
    """Its NodePool's name, as the MCE shows it."""
    infra_envs: tuple[str, ...]
    """The InfraEnvs whose used Agents herzi holds while it lacks the exclusion."""
    missing: tuple[str, ...]
    """The keys it does not exclude."""
    replace: bool
    """``upgradeType: Replace``: its per-cluster merge request leaves it out (ADR-0065)."""


def unguarded(
    values: Mapping[str, object], keys: Sequence[str], *, cluster: str, cluster_name: str
) -> list[Unguarded]:
    """Each agent nodepool of a cluster file whose ``excludeAgentLabels`` lacks one of ``keys``.

    A KubeVirt cluster's nodepools take no Agents and are none of these.
    ``cluster_name`` is the chart's ``clusterName``, which names the NodePools.
    """
    if values.get("platform") == _KUBEVIRT:
        return []
    found: list[Unguarded] = []
    for index, pool in nodepool_entries(values, "nodepool"):
        have = set(keys_of(pool) or ())
        missing = tuple(key for key in keys if key not in have)
        if not missing:
            continue
        first = pool.get("infraEnvName")
        found.append(
            Unguarded(
                cluster=cluster,
                nodepool=nodepool_name(index, pool, cluster_name),
                infra_envs=infra_envs_of(
                    first if isinstance(first, str) else None, additional_of(pool)
                ),
                missing=missing,
                replace=pool.get("upgradeType") == REPLACE,
            )
        )
    return found
