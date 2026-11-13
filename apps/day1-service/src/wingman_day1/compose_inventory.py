"""Inventory Management's part of the composition root (ADR-0057).

The add-server-to-mce workflow's adapter (real, none, or the fake fleet's),
and the page's use case: it reads server-scan through the one cached
``ServerInventory`` the Nodes tab and placement share (``main.py`` builds it),
each MCE's InfraEnvs through the hub cache the create form uses (else from
its day1 cluster files), and the add-server runs through their own short cache.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.inventory import InventoryService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.infrastructure.add_server_workflow import HttpAddServerWorkflow
from wingman_day1.infrastructure.cached_workflows import CachedAddServerWorkflow
from wingman_day1.ports import AddServerWorkflow, HubApi, ServerInventory
from wingman_day1.settings import Day1Settings

RUNS_TTL_SECONDS: Final = 10.0
"""The longest an add-server run's phase is kept: the page re-reads the runs every 10 s."""

Close = Callable[[], Awaitable[None]]


def inventory_service(
    settings: Day1Settings,
    sites: SiteCatalog,
    clusters: ClusterService,
    *,
    inventory: ServerInventory | None,
    infra_envs: HubApi | None,
    workflows: AddServerWorkflow | None,
    cache: TtlCache,
) -> InventoryService | None:
    """The page over the shared caches; ``None`` without server-scan (its routes answer 501)."""
    if inventory is None:
        return None
    return InventoryService(
        sites,
        inventory,
        clusters=clusters,
        hub=infra_envs,
        workflows=(
            CachedAddServerWorkflow(
                workflows, cache, ttl=min(settings.day1_cache_ttl_seconds, RUNS_TTL_SECONDS)
            )
            if workflows is not None
            else None
        ),
        add_servers=settings.day1_add_servers,
        namespace=settings.mce_infraenv_namespace or None,
    )


def add_server_workflow(
    settings: Day1Settings,
    *,
    inventory: ServerInventory | None,
    metrics: WingmanMetrics,
    clock: Clock,
    closers: list[Close],
) -> AddServerWorkflow | None:
    """add-server-to-mce wherever the orchestrator is (its runs are read even when adding is off).

    With the fake fleet, its fake acts on the fake server-scan ``inventory``
    and adds the demo's servers to it (``dev/fleet-fixtures/inventory.yaml``).
    """
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
        from wingman_day1.infrastructure.fake_inventory_demo import fake_add_server

        if not isinstance(inventory, FakeServerInventory):
            raise TypeError("the fake fleet's add-server workflow needs its fake server-scan")
        return fake_add_server(inventory, clock=clock)
    if not settings.workflows_api_url:
        return None
    workflow = HttpAddServerWorkflow(
        base_url=settings.workflows_api_url,
        verify=settings.workflows_tls_verify,
        timeout_seconds=settings.workflows_timeout_seconds,
        metrics=metrics,
    )
    closers.append(workflow.aclose)
    return workflow
