"""Inventory Management: each MCE's pools, its servers, the add-server runs, adding servers.

ADR-0057. The counts are server-scan's, through the one cached
``ServerInventory`` the Nodes tab and placement read; the MCEs are the day1
repo's folders (read-only); each MCE's InfraEnvs come from its hub, cached as
for the create form. Without them (live status off, or the hub unreadable)
the pools are the InfraEnvs the MCE's day1 cluster files name, and the MCE
says why its own list is unknown. server-scan unreadable fails the read: the
page is its numbers.

Installing servers starts the platform's ``add-server-to-mce`` workflow and
needs no hub (ADR-0057's amendment). Day1 checks only that the MCE is a day1
MCE, that the InfraEnv is a DNS label, and that each named server is one the
page offered (an ``AVAILABLE`` server named for the pool, not locked, out of
maintenance, not contested). Whether the InfraEnv exists on the MCE is the
workflow's first check (``validating-infraenv``), as on the orchestrator's
own form. A start is never retried (ADR-0006) and is logged with who asked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.domain.add_server import (
    AddServerRequest,
    AddServerRun,
    AddServerStart,
    ListedRun,
    RunTarget,
    run_target,
)
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    HubError,
    InvalidInputError,
    ResourceNotFoundError,
    WorkflowsNotConfiguredError,
)
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
from wingman_day1.ports import AddServerWorkflow, HubApi, ServerInventory

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


@dataclass(frozen=True, slots=True)
class ShownRun:
    """One add-server run: the list's entry, what its id says, and its own read when made."""

    listed: ListedRun
    target: RunTarget | None
    detail: AddServerRun | None


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
    ) -> None:
        """``hub`` lists InfraEnvs (``None``: live status off); ``workflows`` is the orchestrator.

        ``clusters`` names each MCE's InfraEnvs from its cluster files when its
        hub list is unknown. ``namespace`` is where InfraEnvs are listed and is
        sent to the workflow when set (the orchestrator's default is ``inventory``).
        """
        self._sites = sites
        self._clusters = clusters
        self._inventory = inventory
        self._hub = hub
        self._workflows = workflows
        self._add_servers = add_servers
        self._namespace = namespace

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
        found = await asyncio.gather(*(self._infra_envs(mce) for _, mce in tree.mces))
        named = await self._named_by_files() if any(e for _, e in found) else {}
        mces = tuple(
            mce_inventory(
                site,
                mce,
                rows,
                infra_envs=names if error is None else named.get(mce, []),
                infra_envs_error=error,
                infra_envs_from=FROM_MCE if error is None else FROM_DAY1,
            )
            for (site, mce), (names, error) in zip(tree.mces, found, strict=True)
        )
        return InventoryOverview(mces, self.add_availability, self.runs_availability)

    async def candidates(self, mce: str, infra_env: str) -> list[Candidate]:
        """The servers a named install into ``infra_env`` on ``mce`` may pick, and why not."""
        await self._require_pool(mce, infra_env)
        return candidates(await self._inventory.rows(), infra_env)

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
    ) -> AddServerStart:
        """Start ``add-server-to-mce`` for ``count`` servers, or these. Never retried (ADR-0006)."""
        availability = self.add_availability
        if not availability.available or self._workflows is None:
            raise WorkflowsNotConfiguredError(availability.detail or ADD_SERVERS_OFF)
        if (count is None) == (not server_names):
            raise InvalidInputError("give either count or server_names", ["count or server_names"])
        await self._require_pool(mce, infra_env)
        names = await self._offered(server_names, infra_env) if server_names else ()
        request = AddServerRequest(mce, infra_env, self._namespace, count, names)
        event = {
            "user": user.username,
            "mce": mce,
            "infra_env": infra_env,
            "count": str(count) if count is not None else "",
            "server_names": ",".join(names),
        }
        try:
            result = await self._workflows.start(request)
        except AmbiguousStartError:
            logger.warning(
                "servers add start unconfirmed: %s",
                _fields(event),
                extra={"event": "servers_add_unconfirmed", **event},
            )
            raise
        ids = ",".join(result.workflow_ids)
        logger.info(
            "servers add started: %s",
            _fields({**event, "workflow_ids": ids}),
            extra={"event": "servers_add_started", **event, "workflow_ids": ids},
        )
        return result

    async def _offered(self, names: Sequence[str], infra_env: str) -> tuple[str, ...]:
        """server-scan's own spelling of each named server; any not offered is a 422."""
        rows = await self._inventory.rows()
        if problems := named_refusals(names, rows, infra_env):
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

    async def _named_by_files(self) -> dict[str, list[str]]:
        """Each MCE's InfraEnvs, as its day1 cluster files name them (``infraEnvName``)."""
        named: dict[str, set[str]] = {}
        for found in await self._clusters.clusters():
            pools = found.values.nodepools if found.values is not None else ()
            names = {pool.infra_env_name for pool in pools if pool.infra_env_name}
            named.setdefault(found.ref.mce, set()).update(names)
        return {mce: sorted(names) for mce, names in named.items()}

    async def _infra_envs(self, mce: str) -> tuple[list[str], str | None]:
        """``mce``'s InfraEnvs, or why they are unknown."""
        if self._hub is None:
            return [], NO_HUB
        try:
            return await self._hub.infra_envs(mce, namespace=self._namespace), None
        except HubError as exc:
            return [], f"{type(exc).__name__.removesuffix('Error')}: {exc}"


def _fields(event: Mapping[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in event.items() if value)
