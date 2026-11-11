"""The servers under a hosted cluster, and starting the uninstall of one (ADR-0038).

A cluster's nodes come from server-scan's fleet, one cached read for any
number of clusters; each node's newest uninstall run comes from the
orchestrator. If the orchestrator cannot be read, the nodes are still listed
and ``runs_error`` says why: run states are then unknown, not "none". If
server-scan cannot be read, nothing is listed: the error propagates.

Wingman starts the ``uninstall-server-from-hc`` workflow and shows its run;
the procedure and its checks are the workflow's (a contested server, another
MCE, a lock another run holds all fail the run, with the reason). Day1
checks only what makes the button act on what the page showed: a fresh read
places the server in this cluster, and the name typed to confirm is its name.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    InvalidInputError,
    NodeNotInClusterError,
    WorkflowsError,
    WorkflowsNotConfiguredError,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.servers import (
    RunSummary,
    ServerRow,
    is_node_of,
    nodes_of,
    same_server_name,
    uninstall_run_ids,
)
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.ports import ServerInventory, UninstallWorkflow

logger = logging.getLogger(__name__)

UNINSTALL_NOT_CONFIGURED: Final = (
    "Uninstalling a node is not available in this deployment: the workflows orchestrator "
    "is not configured (WORKFLOWS_API_URL)."
)


@dataclass(frozen=True, slots=True)
class Node:
    """One server under the cluster, its page in server-scan, and its newest uninstall run."""

    server: ServerRow
    url: str
    uninstall: WorkflowRun | None = None


@dataclass(frozen=True, slots=True)
class ClusterNodes:
    """A cluster's nodes, and whether uninstall can be offered."""

    hosted_cluster: str
    nodes: tuple[Node, ...]
    uninstall_available: bool
    uninstall_detail: str | None
    """Why uninstall is not offered, when it is not."""
    runs_error: str | None = None
    """Set when the orchestrator could not be read: every ``uninstall`` is then unknown."""


class NodeService:
    """Read a cluster's nodes from server-scan; start an uninstall through the orchestrator."""

    def __init__(
        self,
        inventory: ServerInventory,
        clusters: ClusterService,
        *,
        ui_url: str,
        workflows: UninstallWorkflow | None,
        infraenv_namespace: str | None,
    ) -> None:
        """``workflows`` ``None``: nodes are listed and uninstall is not offered.

        ``ui_url`` is server-scan's UI, where node links point. ``infraenv_namespace``
        is passed to the workflow as ``namespace`` when set (the orchestrator's
        default is ``inventory``).
        """
        self._inventory = inventory
        self._clusters = clusters
        self._ui_url = ui_url.rstrip("/")
        self._workflows = workflows
        self._namespace = infraenv_namespace

    async def nodes(self, ref: ClusterRef) -> ClusterNodes:
        """The cluster's nodes, sorted by name, each with its newest uninstall run."""
        hosted = await self._clusters.hosted_cluster(ref)
        servers = nodes_of(await self._inventory.rows(), hosted)
        runs, runs_error = await self._runs(servers)
        return ClusterNodes(
            hosted_cluster=hosted.name,
            nodes=tuple(
                Node(server=s, url=self._url(s.id), uninstall=runs.get(s.id)) for s in servers
            ),
            uninstall_available=self._workflows is not None,
            uninstall_detail=None if self._workflows is not None else UNINSTALL_NOT_CONFIGURED,
            runs_error=runs_error,
        )

    async def uninstall(
        self, ref: ClusterRef, server_id: str, *, server_name: str, user: User
    ) -> WorkflowRun:
        """Start the uninstall of one of the cluster's nodes. Never retried (ADR-0006)."""
        if self._workflows is None:
            raise WorkflowsNotConfiguredError(UNINSTALL_NOT_CONFIGURED)
        hosted = await self._clusters.hosted_cluster(ref)
        server = await self._inventory.server(server_id)
        if not is_node_of(server, hosted):
            where = server.cluster_name or "no cluster"
            raise NodeNotInClusterError(
                f"server-scan places {server.name} in {where}, not in {hosted.name}: "
                "reload the cluster's nodes"
            )
        if not same_server_name(server_name, server.name):
            raise InvalidInputError(
                "the name typed to confirm is not the server's name",
                [f"type {server.name} to confirm uninstalling it"],
            )
        event = {
            "user": user.username,
            "cluster": ref.name,
            "site": ref.site,
            "mce": ref.mce,
            "server_id": server.id,
            "server_name": server.name,
        }
        try:
            run = await self._workflows.start(
                server_name=server.name, mce=ref.mce, namespace=self._namespace
            )
        except AmbiguousStartError:
            logger.warning(
                "node uninstall start unconfirmed: %s",
                _fields(event),
                extra={"event": "node_uninstall_unconfirmed", **event},
            )
            raise
        logger.info(
            "node uninstall started: %s",
            _fields({**event, "workflow_id": run.workflow_id}),
            extra={"event": "node_uninstall_started", **event, "workflow_id": run.workflow_id},
        )
        return run

    async def _runs(
        self, servers: Sequence[ServerRow]
    ) -> tuple[Mapping[str, WorkflowRun], str | None]:
        if self._workflows is None or not servers:
            return {}, None
        workflows = self._workflows
        try:
            listed = await workflows.runs()
            ids = uninstall_run_ids(servers, listed)
            fetched = await asyncio.gather(*(workflows.run(wid) for wid in ids.values()))
        except WorkflowsError as exc:
            return {}, f"{type(exc).__name__.removesuffix('Error')}: {exc}"
        newest = _newest_by_id(listed)
        runs: dict[str, WorkflowRun] = {}
        for (server_id, workflow_id), run in zip(ids.items(), fetched, strict=True):
            if run is not None:
                runs[server_id] = run
            elif (summary := newest.get(workflow_id)) is not None:
                # Listed but not readable on its own (it just went away): its status is known.
                runs[server_id] = WorkflowRun(summary.workflow_id, summary.status)
        return runs, None

    def _url(self, server_id: str) -> str:
        return f"{self._ui_url}/servers/{quote(server_id, safe='')}"


def _newest_by_id(runs: Sequence[RunSummary]) -> Mapping[str, RunSummary]:
    """Each workflow id's newest run; ``runs`` is newest first."""
    newest: dict[str, RunSummary] = {}
    for run in runs:
        newest.setdefault(run.workflow_id, run)
    return newest


def _fields(event: Mapping[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in event.items())
