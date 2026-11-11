"""A cluster's nodes by NodePool, and starting the uninstall of one (ADR-0038).

The NodePools and their Machines come from the cluster's MCE, read only,
through the same hub access as live status; each Machine is followed to its
Agent and its server (``wingman_day1.domain.node_pools``). server-scan is
optional: it adds each server's record, and the servers it places in the
cluster that no Machine leads to (``unassigned``). The orchestrator adds each
server's newest uninstall run. If server-scan or the orchestrator cannot be
read, the nodes are still listed and ``server_scan_error`` or ``runs_error``
says why; if the MCE cannot be read, nothing is listed and the error
propagates.

Wingman starts the ``uninstall-server-from-hc`` workflow and shows its run;
the procedure and its checks are the workflow's. Day1 checks only what makes
the button act on what the page showed: the server is one of this cluster's
nodes (a Machine of the cluster leads to it, or a fresh server-scan read
places it in the cluster), and the name typed to confirm is its name.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import quote

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    InvalidInputError,
    NodeNotInClusterError,
    ServerScanNotConfiguredError,
    ServerScanUnavailableError,
    WorkflowsError,
    WorkflowsNotConfiguredError,
)
from wingman_day1.domain.machines import AgentObservation
from wingman_day1.domain.names import HostedClusterRef
from wingman_day1.domain.node_pools import ClusterMachines, NodePoolView, NodesByPool, nodes_by_pool
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.servers import (
    RunSummary,
    ServerRow,
    is_node_of,
    same_server_name,
    uninstall_run_ids,
)
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.ports import HubApi, ServerInventory, UninstallWorkflow

logger = logging.getLogger(__name__)

ORCHESTRATOR_NOT_CONFIGURED: Final = (
    "Uninstalling a node is not available in this deployment: the workflows orchestrator "
    "is not configured (WORKFLOWS_API_URL)."
)
SERVER_SCAN_NOT_CONFIGURED: Final = (
    "Uninstalling a node is not available in this deployment: server-scan is not "
    "configured (SERVER_SCAN_URL)."
)


@dataclass(frozen=True, slots=True)
class ClusterNodes:
    """A cluster's NodePools and nodes, the servers no Machine leads to, and their runs."""

    hosted_cluster: str
    node_pools: tuple[NodePoolView, ...]
    unassigned: tuple[ServerRow, ...]
    uninstall_available: bool
    uninstall_detail: str | None
    """Why uninstall is not offered, when it is not."""
    runs: Mapping[str, WorkflowRun] = field(default_factory=dict)
    """Each server's newest uninstall run, by server id."""
    server_urls: Mapping[str, str] = field(default_factory=dict)
    """Each server's page in server-scan's UI, by server id."""
    server_scan_error: str | None = None
    """Set when server-scan could not be read: no ``server`` and no ``unassigned``."""
    runs_error: str | None = None
    """Set when the orchestrator could not be read: every run is then unknown."""


class NodeService:
    """Read a cluster's nodes from its MCE and server-scan; start an uninstall of one."""

    def __init__(
        self,
        hub: HubApi,
        clusters: ClusterService,
        *,
        inventory: ServerInventory | None,
        ui_url: str,
        workflows: UninstallWorkflow | None,
        infraenv_namespace: str | None,
    ) -> None:
        """``inventory`` and ``workflows`` may be ``None``: nodes are listed without them.

        ``ui_url`` is server-scan's UI, where server links point.
        ``infraenv_namespace`` is passed to the workflow as ``namespace`` when set
        (the orchestrator's default is ``inventory``).
        """
        self._hub = hub
        self._clusters = clusters
        self._inventory = inventory
        self._ui_url = ui_url.rstrip("/")
        self._workflows = workflows
        self._namespace = infraenv_namespace

    @property
    def uninstall_detail(self) -> str | None:
        """Why uninstall cannot be offered here, or ``None`` when it can."""
        if self._workflows is None:
            return ORCHESTRATOR_NOT_CONFIGURED
        if self._inventory is None:
            return SERVER_SCAN_NOT_CONFIGURED
        return None

    async def nodes(self, ref: ClusterRef) -> ClusterNodes:
        """The cluster's NodePools with their nodes, and the unassigned servers."""
        hosted = await self._clusters.hosted_cluster(ref)
        observed, (servers, scan_error) = await asyncio.gather(
            self._observe(ref.mce, hosted), self._servers()
        )
        found = nodes_by_pool(hosted, observed, servers)
        shown = found.servers()
        runs, runs_error = await self._runs(shown)
        detail = self.uninstall_detail
        return ClusterNodes(
            hosted_cluster=hosted.name,
            node_pools=found.node_pools,
            unassigned=found.unassigned,
            uninstall_available=detail is None,
            uninstall_detail=detail,
            runs=runs,
            server_urls={row.id: self._url(row.id) for row in shown},
            server_scan_error=scan_error,
            runs_error=runs_error,
        )

    async def uninstall(
        self, ref: ClusterRef, server_id: str, *, server_name: str, user: User
    ) -> WorkflowRun:
        """Start the uninstall of one of the cluster's nodes. Never retried (ADR-0006)."""
        if self._workflows is None:
            raise WorkflowsNotConfiguredError(ORCHESTRATOR_NOT_CONFIGURED)
        if self._inventory is None:
            raise ServerScanNotConfiguredError(SERVER_SCAN_NOT_CONFIGURED)
        hosted = await self._clusters.hosted_cluster(ref)
        server = await self._inventory.server(server_id)
        if not is_node_of(server, hosted):
            found = await self._tree(ref.mce, hosted)
            if not found.leads_to(server.id, server.name):
                where = server.cluster_name or "no cluster"
                raise NodeNotInClusterError(
                    f"no Machine of {hosted.name} leads to {server.name}, and server-scan "
                    f"places it in {where}: reload the cluster's nodes"
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

    async def _observe(self, mce: str, hosted: HostedClusterRef) -> ClusterMachines:
        """The MCE's objects for the cluster; any failure propagates (the view needs them all)."""
        cluster = await self._hub.hosted_cluster(mce, namespace=hosted.namespace, name=hosted.name)
        control_plane = hosted.control_plane_namespace
        pools, machines, machine_sets, agent_machines, agents = await asyncio.gather(
            self._hub.node_pools(mce, namespace=hosted.namespace),
            self._hub.machines(mce, namespace=control_plane),
            self._hub.machine_sets(mce, namespace=control_plane),
            self._hub.agent_machines(mce, namespace=control_plane),
            self._agents(mce, cluster.agent_namespace),
        )
        return ClusterMachines(
            hosted_cluster=cluster,
            node_pools=pools,
            machines=machines,
            machine_sets=machine_sets,
            agent_machines=agent_machines,
            agents=agents,
        )

    async def _agents(self, mce: str, namespace: str | None) -> list[AgentObservation] | None:
        """The cluster's Agents; ``None`` when its HostedCluster names no agent namespace."""
        if not namespace:
            return None
        return await self._hub.agents(mce, namespace=namespace)

    async def _tree(self, mce: str, hosted: HostedClusterRef) -> NodesByPool:
        servers, _ = await self._servers()
        return nodes_by_pool(hosted, await self._observe(mce, hosted), servers)

    async def _servers(self) -> tuple[list[ServerRow] | None, str | None]:
        """The whole fleet, or why it could not be read; ``(None, None)`` without server-scan."""
        if self._inventory is None:
            return None, None
        try:
            return await self._inventory.rows(), None
        except ServerScanUnavailableError as exc:
            return None, f"{type(exc).__name__.removesuffix('Error')}: {exc}"

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
