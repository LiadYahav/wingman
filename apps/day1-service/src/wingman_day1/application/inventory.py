"""Inventory Management: each MCE's pools, its servers, the add-server runs, adding servers.

ADR-0057. The counts are server-scan's, through the one cached
``ServerInventory`` the Nodes tab and placement read; the MCEs are the day1
repo's folders (read-only); each MCE's InfraEnvs and their agentLabels come
from its hub, cached as for the create form, and name each pool's servers
(``domain/infra_env_pools.py``). Without them (live status off, or the hub
unreadable) the pools are the InfraEnvs the MCE's day1 cluster files name,
their servers' names unknown, and the MCE says why its own list is unknown.
server-scan unreadable fails the read: the page is its numbers.

Each MCE's used Agents (``domain/used_agents.py``: herzi's
``redbull.io/ever-installed``, or the deployment's excluded labels) are read
from its hub, only those labelled and held by no AgentMachine, for as long as
the page refreshes; they are shown apart and never counted as available. Its
agent nodepools that do not exclude those keys come from its cluster files:
herzi removes no used Agent of their InfraEnvs until each does, and they may
bind one meanwhile. Without live status the used Agents are unknown.

Installing servers starts the platform's ``add-server-to-mce`` workflow and
needs no hub (ADR-0057's amendment). Day1 checks only that the MCE is a day1
MCE, that the InfraEnv is a DNS label, and that each named server is one a
pool may offer (an ``AVAILABLE`` server, not locked, out of maintenance, not
contested): the workflow does not match a named server to the pool. Whether
the InfraEnv exists on the MCE is the workflow's first check
(``validating-infraenv``), as on the orchestrator's own form. A start is
never retried (ADR-0006) and is logged with who asked. ``allow_unhealthy``
(the workflow's health waiver, ADR-0057's 3.38.0 amendment) is refused
without server names, before anything is sent, and a start that carries it
is logged as one with health checks waived.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.domain.add_server import (
    WAIVER_NEEDS_NAMES,
    AddServerRequest,
    AddServerRun,
    AddServerStart,
    ListedRun,
    RunTarget,
    run_target,
)
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    HubError,
    InvalidClusterFileError,
    InvalidInputError,
    ResourceNotFoundError,
    WorkflowsNotConfiguredError,
)
from wingman_day1.domain.infra_env_pools import Pool
from wingman_day1.domain.inventory import (
    FROM_DAY1,
    FROM_MCE,
    Candidate,
    MceInventory,
    candidates,
    mce_inventory,
    named_refusals,
)
from wingman_day1.domain.names import dns_label_problems
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.used_agents import (
    Unguarded,
    UsedAgent,
    unguarded,
    used_labels,
    used_servers,
)
from wingman_day1.integrations.server_scan.ports import ServerInventory
from wingman_day1.ports import AddServerWorkflow, HubApi

logger = logging.getLogger(__name__)

ADD_SERVERS_OFF: Final = "Installing servers is off on this Wingman (DAY1_ADD_SERVERS=false)."
NO_ORCHESTRATOR: Final = (
    "The workflows orchestrator is not configured (WORKFLOWS_API_URL): no add-server runs."
)
NO_HUB: Final = (
    "Live status is off (CLUSTER_STATUS_ENABLED=false): the MCE's own InfraEnv list is not read."
)
SHOWN_RUNS: Final = 50
"""The newest runs shown."""
READ_RUNS: Final = 20
"""The newest runs read one by one for their phase, server and error."""


@dataclass(frozen=True, slots=True)
class Availability:
    """Whether a part of the page works here, and why not."""

    available: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class InventoryOverview:
    """Every MCE's counts, and what this deployment offers."""

    mces: tuple[MceInventory, ...]
    add_servers: Availability
    runs: Availability
    used_labels: tuple[str, ...] = ()
    """The keys that mark a used Agent here (``WorkflowKeys.used_agent_labels``)."""
    excluded: bool = False
    """Whether they are the deployment's excluded labels; else herzi's label alone."""
    unguarded: tuple[Unguarded, ...] = ()
    """Agent nodepools of the day1 repo that do not exclude every key, with their MCE."""
    unguarded_mces: tuple[str, ...] = ()
    """Each ``unguarded`` entry's MCE, in the same order."""


@dataclass(frozen=True, slots=True)
class PoolServers:
    """A pool, as its servers are matched, and the free servers it lists."""

    pool: Pool
    candidates: list[Candidate]


@dataclass(frozen=True, slots=True)
class ShownRun:
    """One add-server run: the list's entry, what its id says, and its own read when made."""

    listed: ListedRun
    target: RunTarget | None
    detail: AddServerRun | None

    @property
    def server_name(self) -> str | None:
        """The server the run names: its own read's, else its id's (lowercased)."""
        named = self.detail.server_name if self.detail is not None else None
        return named or (self.target.server if self.target is not None else None)


class InventoryService:
    """Read MCE pools from server-scan and the hubs; show and start add-server runs."""

    def __init__(
        self,
        sites: SiteCatalog,
        inventory: ServerInventory,
        *,
        clusters: ClusterService,
        hub: HubApi | None,
        workflows: AddServerWorkflow | None,
        add_servers: bool,
        namespace: str | None,
        agents: HubApi | None = None,
        excluded_agent_labels: Sequence[str] = (),
    ) -> None:
        """``hub`` lists InfraEnvs (``None``: live status off); ``workflows`` is the orchestrator.

        ``clusters`` names each MCE's InfraEnvs from its cluster files when its
        hub list is unknown. ``namespace`` is where InfraEnvs are listed and is
        sent to the workflow when set (the orchestrator's default is ``inventory``).
        ``agents`` reads the used Agents (cached for seconds; ``None``: not
        read); ``excluded_agent_labels`` is ``DAY1_EXCLUDED_AGENT_LABELS``.
        """
        self._sites = sites
        self._clusters = clusters
        self._inventory = inventory
        self._hub = hub
        self._workflows = workflows
        self._add_servers = add_servers
        self._namespace = namespace
        self._agents = agents
        self._excluded = bool(excluded_agent_labels)
        self._used_labels = used_labels(excluded_agent_labels)

    @property
    def runs_availability(self) -> Availability:
        """Whether the add-server runs can be read here."""
        if self._workflows is None:
            return Availability(False, NO_ORCHESTRATOR)
        return Availability(True)

    @property
    def add_availability(self) -> Availability:
        """Whether servers can be added here, and why not."""
        if not self._add_servers:
            return Availability(False, ADD_SERVERS_OFF)
        if self._workflows is None:
            return Availability(False, NO_ORCHESTRATOR)
        return Availability(True)

    async def overview(self) -> InventoryOverview:
        """Every day1 MCE's servers and pools, as server-scan counts them."""
        tree = await self._sites.tree()
        rows = await self._inventory.rows()
        found, used, files = await asyncio.gather(
            asyncio.gather(*(self._pools(mce) for _, mce in tree.mces)),
            asyncio.gather(*(self._used(mce, rows) for _, mce in tree.mces)),
            self._clusters.clusters(),
        )
        named = _named_by_files(files)
        mces = tuple(
            mce_inventory(
                site,
                mce,
                rows,
                pools=pools if error is None else [Pool.unread(n) for n in named.get(mce, [])],
                infra_envs_error=error,
                infra_envs_from=FROM_MCE if error is None else FROM_DAY1,
                used=agents,
                used_error=used_error,
            )
            for (site, mce), (pools, error), (agents, used_error) in zip(
                tree.mces, found, used, strict=True
            )
        )
        lacking = [(f.ref.mce, pool) for f in files for pool in self._unguarded(f)]
        return InventoryOverview(
            mces,
            self.add_availability,
            self.runs_availability,
            used_labels=self._used_labels,
            excluded=self._excluded,
            unguarded=tuple(pool for _, pool in lacking),
            unguarded_mces=tuple(mce for mce, _ in lacking),
        )

    async def candidates(self, mce: str, infra_env: str) -> PoolServers:
        """The servers a named install into ``infra_env`` on ``mce`` may pick, and why not.

        The free servers its agentLabels name; every free server when they are
        unknown (live status off, the hub unreadable, an InfraEnv the MCE does
        not list) or name none: the workflow checks the server named.
        """
        await self._require_pool(mce, infra_env)
        pools, _ = await self._pools(mce)
        pool = next((p for p in pools if p.infra_env == infra_env), Pool.unread(infra_env))
        return PoolServers(pool, candidates(await self._inventory.rows(), pool))

    async def runs(self) -> list[ShownRun]:
        """The newest add-server runs; the newest few read for their phase, server and error.

        A pool's slots are reused, so several runs may share an id, and a read
        by id answers for the newest of them: only that one gets the read.
        """
        if self._workflows is None:
            raise WorkflowsNotConfiguredError(NO_ORCHESTRATOR)
        workflows = self._workflows
        listed = (await workflows.runs())[:SHOWN_RUNS]
        newest = list(dict.fromkeys(r.workflow_id for r in listed))[:READ_RUNS]
        details = await asyncio.gather(*(workflows.run(workflow_id) for workflow_id in newest))
        read: dict[str, AddServerRun | None] = dict(zip(newest, details, strict=True))
        return [
            ShownRun(run, run_target(run.workflow_id), read.pop(run.workflow_id, None))
            for run in listed
        ]

    async def add_servers(
        self,
        mce: str,
        infra_env: str,
        *,
        count: int | None,
        server_names: Sequence[str],
        user: User,
        allow_unhealthy: bool = False,
    ) -> AddServerStart:
        """Start ``add-server-to-mce`` for ``count`` servers, or these. Never retried (ADR-0006).

        ``allow_unhealthy`` waives the workflow's health checks for the named
        servers, never its safety refusals; a pool draw may not carry it.
        """
        availability = self.add_availability
        if not availability.available or self._workflows is None:
            raise WorkflowsNotConfiguredError(availability.detail or ADD_SERVERS_OFF)
        if (count is None) == (not server_names):
            raise InvalidInputError("give either count or server_names", ["count or server_names"])
        if allow_unhealthy and not server_names:
            raise InvalidInputError(WAIVER_NEEDS_NAMES, ["allow_unhealthy: needs server_names"])
        await self._require_pool(mce, infra_env)
        names = await self._offered(server_names) if server_names else ()
        request = AddServerRequest(
            mce, infra_env, self._namespace, count, names, allow_unhealthy=allow_unhealthy
        )
        event = {
            "user": user.username,
            "mce": mce,
            "infra_env": infra_env,
            "count": str(count) if count is not None else "",
            "server_names": ",".join(names),
            "allow_unhealthy": "true" if allow_unhealthy else "",
        }
        waived = " with health checks waived" if allow_unhealthy else ""
        try:
            result = await self._workflows.start(request)
        except AmbiguousStartError:
            logger.warning(
                "servers add start%s unconfirmed: %s",
                waived,
                _fields(event),
                extra={"event": "servers_add_unconfirmed", **event},
            )
            raise
        ids = ",".join(result.workflow_ids)
        logger.log(
            logging.WARNING if allow_unhealthy else logging.INFO,
            "servers add started%s: %s",
            waived,
            _fields({**event, "workflow_ids": ids}),
            extra={"event": "servers_add_started", **event, "workflow_ids": ids},
        )
        return result

    async def _offered(self, names: Sequence[str]) -> tuple[str, ...]:
        """server-scan's own spelling of each named server; any not offered is a 422."""
        rows = await self._inventory.rows()
        if problems := named_refusals(names, rows):
            raise InvalidInputError(
                "these servers cannot be offered for a named install; reload the list", problems
            )
        spelling = {row.name.casefold(): row.name for row in rows}
        return tuple(spelling[name.casefold()] for name in names)

    async def _site_of(self, mce: str) -> str:
        tree = await self._sites.tree()
        site = next((s for s, m in tree.mces if m == mce), None)
        if site is None:
            raise ResourceNotFoundError(f"MCE {mce!r} does not exist in the day1 repo")
        return site

    async def _require_pool(self, mce: str, infra_env: str) -> None:
        """``mce`` is a day1 MCE and ``infra_env`` a DNS label; no MCE read.

        Whether the InfraEnv exists on the MCE is the workflow's first check
        (``validating-infraenv``), as on the orchestrator's own form.
        """
        await self._site_of(mce)
        if problems := dns_label_problems(infra_env, what="InfraEnv"):
            raise InvalidInputError(f"InfraEnv {infra_env!r} is not a DNS label", problems)

    def _unguarded(self, found: ClusterFile) -> list[Unguarded]:
        """The file's agent nodepools that do not exclude every used-Agent key."""
        try:
            values = load_values(found.content)
        except InvalidClusterFileError:
            return []  # its own page says why it does not parse
        name = found.hosted_cluster.cluster_name
        return unguarded(values, self._used_labels, cluster=found.ref.name, cluster_name=name)

    async def _used(
        self, mce: str, rows: Sequence[ServerRow]
    ) -> tuple[list[UsedAgent] | None, str | None]:
        """``mce``'s used Agents, joined to its rows; ``None`` and why, when not read."""
        if self._agents is None:
            return None, None
        try:
            agents = await self._agents.used_agents(
                mce, labels=self._used_labels, namespace=self._namespace
            )
        except HubError as exc:
            return None, f"{type(exc).__name__.removesuffix('Error')}: {exc}"
        return used_servers(agents, self._used_labels, [r for r in rows if r.mce == mce]), None

    async def _pools(self, mce: str) -> tuple[list[Pool], str | None]:
        """``mce``'s InfraEnvs as pools, by their agentLabels; or why they are unknown."""
        if self._hub is None:
            return [], NO_HUB
        try:
            found = await self._hub.infra_envs(mce, namespace=self._namespace)
            return [Pool.observed(infra_env) for infra_env in found], None
        except HubError as exc:
            return [], f"{type(exc).__name__.removesuffix('Error')}: {exc}"


def _named_by_files(files: Sequence[ClusterFile]) -> dict[str, list[str]]:
    """Each MCE's InfraEnvs, as its day1 cluster files name them.

    Every InfraEnv a nodepool draws from: ``infraEnvName`` and its
    ``additionalInfraEnvNames`` (ADR-0064).
    """
    named: dict[str, set[str]] = {}
    for found in files:
        pools = found.values.nodepools if found.values is not None else ()
        names = {name for pool in pools for name in pool.infra_envs}
        named.setdefault(found.ref.mce, set()).update(names)
    return {mce: sorted(names) for mce, names in named.items()}


def _fields(event: Mapping[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in event.items() if value)
