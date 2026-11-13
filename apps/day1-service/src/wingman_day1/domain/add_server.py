"""The platform's add-server-to-mce workflow: requests, answers and run ids (ADR-0057).

The workflow makes physical servers Agents in an MCE's InfraEnv pool; any
NodePool on that InfraEnv that is short of nodes takes one, whatever cluster
it belongs to. A person starts it from Inventory Management; herzi starts it
by itself. Wingman starts runs and shows them; the procedure and its checks
are the workflow's.

Run ids are the orchestrator's (``shared/workflow_ids.py``): a pool draw is
``add-server-to-mce-<mce>_<infraEnv>_<slot>`` (slot 1-100, the first free)
and a named install ``add-server-to-mce-<mce>_<server, lowercased>``; the
orchestrator adds ``ocp4-`` to the MCE. herzi only ever sends a count, and
the orchestrator records no ``requested_by``: a named run is a person's, a
pool draw is herzi's or a person's, and nothing tells which.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

ADD_SERVER_WORKFLOW_PREFIX: Final = "add-server-to-mce-"
ADD_SERVER_HOLDERS: Final = frozenset({"add-server-to-mce", "install-server"})
"""server-scan's reservation holders of an add-server run (``install-server`` before the rename)."""
MCE_PREFIX: Final = "ocp4-"
"""What the orchestrator adds to an MCE name that lacks it."""
MAX_SERVERS: Final = 20
"""The most servers one request may ask for, by count or by name (the orchestrator's limit)."""
MAX_SLOT: Final = 100


class Origin(StrEnum):
    """Who may have started a run, as far as its id tells."""

    NAMED = "named"
    """A named install: a person (herzi never names a server)."""
    POOL = "pool"
    """A pool draw: herzi or a person; nothing tells which."""


@dataclass(frozen=True, slots=True)
class RunTarget:
    """What an add-server run's id says: its MCE, and its slot or its server."""

    mce: str
    origin: Origin
    infra_env: str | None = None
    """A pool draw's InfraEnv; ``None`` for a named install (its id does not carry it)."""
    slot: int | None = None
    server: str | None = None
    """A named install's server, lowercased as in the id."""


def canonical_mce(mce: str) -> str:
    """The MCE as the orchestrator names it in run ids: with ``ocp4-``."""
    return mce if mce.startswith(MCE_PREFIX) else f"{MCE_PREFIX}{mce}"


def run_target(workflow_id: str) -> RunTarget | None:
    """What an add-server run id says; ``None`` for an id of neither shape."""
    rest = workflow_id.removeprefix(ADD_SERVER_WORKFLOW_PREFIX)
    if rest == workflow_id:
        return None
    parts = rest.split("_")
    if len(parts) == 3 and all(parts) and parts[2].isdigit():
        slot = int(parts[2])
        if 1 <= slot <= MAX_SLOT:
            return RunTarget(parts[0], Origin.POOL, infra_env=parts[1], slot=slot)
        return None
    if len(parts) == 2 and all(parts):
        return RunTarget(parts[0], Origin.NAMED, server=parts[1])
    return None


@dataclass(frozen=True, slots=True)
class AddServerRequest:
    """One start: fill ``infra_env`` on ``mce`` with ``count`` servers, or ``server_names``."""

    mce: str
    infra_env: str
    namespace: str | None
    """The InfraEnv's namespace; ``None``: the orchestrator's default (``inventory``)."""
    count: int | None = None
    server_names: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        """How many servers it asks for."""
        return self.count if self.count is not None else len(self.server_names)


@dataclass(frozen=True, slots=True)
class StartedRun:
    """The orchestrator's answer for one server of a start."""

    workflow_id: str
    status: str
    """``started``, ``already_running`` or ``failed``: the orchestrator's word."""
    server_name: str | None = None
    slot: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AddServerStart:
    """A start's answer: how many started, were already running or failed, and each run."""

    started: int
    already_running: int
    failed: int
    runs: tuple[StartedRun, ...]

    @property
    def workflow_ids(self) -> tuple[str, ...]:
        """Every run's id, for the log."""
        return tuple(run.workflow_id for run in self.runs)


@dataclass(frozen=True, slots=True)
class ListedRun:
    """One entry of the orchestrator's run list, newest first."""

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase."""
    started_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AddServerRun:
    """One run read on its own: its phase, the server it took, and its error."""

    workflow_id: str
    status: str
    phase: str | None = None
    """The workflow's own word; Wingman keeps no list of them."""
    server_name: str | None = None
    """The server the run took, once chosen."""
    error: str | None = None
