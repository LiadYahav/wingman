"""Scaling NodePools' part of the composition root (ADR-0062).

The update-nodepool workflow's adapter (real, none, or the fake fleet's) and
the use case, both only while Scale is on (``Day1Settings.scale_nodepools``:
``DAY1_SCALE_NODEPOOLS``, true by default, and an orchestrator): off, the scale
routes answer 501 and nothing here is built. A cluster's run is read
uncached, as a cluster's upgrade run is: the page polls it while it runs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.scale import ScaleService
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.scale import file_nodepools
from wingman_day1.infrastructure.scale_workflow import HttpScaleWorkflow
from wingman_day1.ports import ScaleWorkflow
from wingman_day1.settings import Day1Settings

Close = Callable[[], Awaitable[None]]


def scale_workflow(
    settings: Day1Settings, *, metrics: WingmanMetrics, clock: Clock, closers: list[Close]
) -> ScaleWorkflow | None:
    """The update-nodepool workflow while scaling is on; or, with the fake fleet, its fake."""
    if not settings.scale_nodepools:
        return None
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_scale import FakeScaleWorkflow

        return FakeScaleWorkflow(clock=clock)
    workflow = HttpScaleWorkflow(
        base_url=settings.workflows_api_url,
        verify=settings.workflows_tls_verify,
        timeout_seconds=settings.workflows_timeout_seconds,
        metrics=metrics,
    )
    closers.append(workflow.aclose)
    return workflow


def scale_service(
    settings: Day1Settings,
    workflow: ScaleWorkflow | None,
    clusters: ClusterService,
    specs: SpecCatalog,
) -> ScaleService | None:
    """The scale use case while Scale is on; else ``None`` (the routes' 501).

    The fake fleet's workflow reads each cluster's NodePools and policies from its day1 file.
    """
    if not settings.scale_nodepools or workflow is None:
        return None
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_scale import FakePool, FakeScaleWorkflow

        if isinstance(workflow, FakeScaleWorkflow):

            async def pools(cluster: str) -> list[FakePool]:
                found = await clusters.get(await clusters.locate(cluster))
                return [
                    FakePool(p.name, p.infra_env, p.replicas or 0, p.scale_down_policy)
                    for p in file_nodepools(
                        load_values(found.content), cluster_name=found.hosted_cluster.cluster_name
                    )
                    if p.name is not None
                ]

            workflow.read_pools_with(pools)
    return ScaleService(workflow, clusters, specs)
