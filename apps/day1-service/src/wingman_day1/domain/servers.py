"""The servers under a hosted cluster, as server-scan reports them (ADR-0038).

server-scan is the platform's record of physical servers. A server's
``cluster_name`` comes from the ``nodes-status`` jobs, and between them they
write either the HostedCluster's name (``ocp4-<clusterName>``) or the bare
``clusterName``, so a cluster's nodes are the servers with either.

Taking a node out is the ``uninstall-server-from-hc`` workflow's job: it owns
the procedure and every check before it. Wingman starts it and shows its run;
the one thing it checks itself is that the server is still one of this
cluster's nodes, so the button acts on what the page showed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from wingman_day1.domain.names import HostedClusterRef

UNINSTALL_HOLDER: Final = "uninstall-server-from-hc"
"""The reservation holder server-scan shows while an uninstall run holds the server."""
UNINSTALL_WORKFLOW_PREFIX: Final = "uninstall-server-from-hc-"
"""The orchestrator's id for an uninstall is this and the server's name, lowercased."""


@dataclass(frozen=True, slots=True)
class ServerRow:
    """One server, from server-scan's fleet rows (``GET /api/v1/servers/rows``)."""

    id: str
    """server-scan's own stable id (``srv_<hex>``); names are not unique."""
    name: str
    state: str
    """``openshift_state``: ``AVAILABLE``, ``INSTALLED`` or ``INSTALLED_TO_INVENTORY``."""
    health: str
    """The overall verdict; ``UNKNOWN`` is not a verdict."""
    serial: str | None = None
    vendor: str | None = None
    model: str | None = None
    site: str | None = None
    cluster_name: str | None = None
    mce: str | None = None
    maintenance: bool = False
    reachable: bool = True
    stale: bool = False
    contested: bool = False
    """Two clusters' jobs claim it (``contested_with``). Shown only: the workflow refuses it."""
    last_seen_at: datetime | None = None
    reserved_by: str | None = None
    """The reservation's holder while the reservation is held, else ``None``."""
    macs: tuple[str, ...] = ()
    """Its NICs' MAC addresses, lowercase."""


@dataclass(frozen=True, slots=True)
class ServerDetail:
    """One server read fresh (``GET /api/v1/servers/{id}``), for the uninstall's one check."""

    id: str
    name: str
    cluster_name: str | None
    """``openshift.cluster_name``."""


@dataclass(frozen=True, slots=True)
class RunSummary:
    """One entry of the orchestrator's run list (newest first): which run, and its status."""

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase."""


def run_status(raw: str) -> str:
    """The orchestrator's status as the API shows it: ``RUNNING`` is ``running``."""
    return raw.strip().lower()


def node_cluster_names(hosted: HostedClusterRef) -> frozenset[str]:
    """The two ``cluster_name`` values server-scan may hold for this cluster's nodes."""
    return frozenset({hosted.name, hosted.cluster_name})


def is_node_of(server: ServerDetail, hosted: HostedClusterRef) -> bool:
    """Whether server-scan places ``server`` in this cluster."""
    return server.cluster_name in node_cluster_names(hosted)


def same_server_name(typed: str, actual: str) -> bool:
    """Whether the name typed to confirm is the server's, ignoring case."""
    return typed.strip().casefold() == actual.casefold()


def uninstall_workflow_id(server_name: str) -> str:
    """The orchestrator's id for an uninstall of ``server_name``: one run per server at a time."""
    return f"{UNINSTALL_WORKFLOW_PREFIX}{server_name.lower()}"


def uninstall_run_ids(nodes: Sequence[ServerRow], runs: Iterable[RunSummary]) -> Mapping[str, str]:
    """For each node with an uninstall run, its server id and that run's workflow id.

    A node has one when the orchestrator's run list holds its id, or when
    server-scan shows an uninstall holding it (the list is the newest runs of
    the whole fleet, so an old run may not be in it).
    """
    listed = {run.workflow_id for run in runs}
    found: dict[str, str] = {}
    for node in nodes:
        workflow_id = uninstall_workflow_id(node.name)
        if workflow_id in listed or node.reserved_by == UNINSTALL_HOLDER:
            found[node.id] = workflow_id
    return found
