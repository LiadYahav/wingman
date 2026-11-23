"""herzi's used Agents: free Agents no NodePool may take, which herzi removes from the MCE.

herzi's plan to retire used servers (team-redbull/herzi, branch
``docs/retire-used-servers-plan``, ``578edf1``, its owner's decisions
approved; herzi's ``main`` labels nothing yet): herzi labels every Agent
bound to a tenant cluster ``redbull.io/ever-installed: "true"`` as it binds,
and once such an Agent is free again it starts ``remove-server-from-mce`` for
it. A labelled free Agent is **retiring**: never spare to herzi, and never
bound again, because every NodePool excludes the label (``{key:
redbull.io/ever-installed, operator: DoesNotExist}``, ADR-0065).

Which keys mark a used Agent comes from one place, :func:`used_labels`: the
deployment's ``DAY1_EXCLUDED_AGENT_LABELS`` when it is set (what its NodePools
exclude), else herzi's label. An Agent that carries no such key is untouched,
so nothing changes until herzi labels Agents. Placement counts a used Agent as
no free server (ADR-0050).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from wingman_day1.domain.machines import AgentObservation

HERZI_LABEL: Final = "redbull.io/ever-installed"
"""herzi's mark on an Agent that was ever bound to a cluster (the user's choice, 2026-11-23)."""


def used_labels(excluded: Sequence[str]) -> tuple[str, ...]:
    """The keys that mark a used Agent: the deployment's excluded labels, else herzi's."""
    return tuple(excluded) or (HERZI_LABEL,)


def used_label(agent: AgentObservation, keys: Sequence[str]) -> str | None:
    """The first of ``keys`` the Agent carries, whatever its value; ``None`` when none.

    Key presence, as the NodePool's ``DoesNotExist`` and herzi test it.
    """
    return next((key for key in keys if key in agent.labels), None)
