"""Scaling's part of the composition root (ADR-0062): on by default wherever the orchestrator is,
real or the fake fleet's."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from prometheus_client import CollectorRegistry
from pydantic import SecretStr

from wingman_core.domain.users import Role, User
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import system_clock
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.scale import ScaleTarget
from wingman_day1.compose_scale import Close, scale_service, scale_workflow
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.fake_scale import FakeScaleWorkflow
from wingman_day1.infrastructure.scale_workflow import HttpScaleWorkflow
from wingman_day1.settings import Day1Settings

WORKFLOWS = "http://workflows-orchestrator-api.redbull-workflows.svc:8080"
SERVER_SCAN = "http://server-scan-api.inventory.svc:8000"
LARK = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-lark-site1")
STORAGE = "prod-lark-site1-dell-r760-site1-64c-512gb-20tb"


def metrics() -> WingmanMetrics:
    return WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")


def settings(**values: object) -> Day1Settings:
    base: dict[str, object] = {
        "day1_gitlab_project_id": "gitops-day1/platform-config",
        "specs_gitlab_project_id": "wingman/cluster-specs",
        "dev_auth_enabled": True,
        "dev_auth_secret": SecretStr("d" * 40),
    }
    base.update(values)
    return Day1Settings(**base)  # ty: ignore[invalid-argument-type]


def test_scaling_is_on_by_default_wherever_the_orchestrator_is() -> None:
    """Since 3.53.0 (update-nodepool in production): on with an orchestrator, off without one
    whatever DAY1_SCALE_NODEPOOLS says, so day1 starts as before and an edit may change replicas;
    false turns it off."""
    orchestrator = {"workflows_api_url": WORKFLOWS, "server_scan_url": SERVER_SCAN}
    assert settings().day1_scale_nodepools is True
    assert settings(**orchestrator).scale_nodepools is True
    assert settings(day1_fake_fleet=True).scale_nodepools is True
    assert settings().scale_nodepools is False, "no orchestrator: no Scale, and day1 starts"
    assert settings(day1_scale_nodepools=True).scale_nodepools is False
    assert settings().workflow_keys().replicas is False, "an edit may change replicas"
    assert settings(**orchestrator).workflow_keys().replicas is True
    off = settings(day1_scale_nodepools=False, **orchestrator)
    assert off.scale_nodepools is False
    assert off.workflow_keys().replicas is False
    assert settings(day1_scale_nodepools=False, day1_fake_fleet=True).scale_nodepools is False


async def test_the_orchestrators_adapter_by_default_and_none_when_turned_off() -> None:
    closers: list[Close] = []
    off = settings(
        day1_scale_nodepools=False, workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN
    )
    assert scale_workflow(off, metrics=metrics(), clock=system_clock, closers=closers) is None
    alone = settings()
    assert scale_workflow(alone, metrics=metrics(), clock=system_clock, closers=closers) is None
    on = settings(workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN)
    workflow = scale_workflow(on, metrics=metrics(), clock=system_clock, closers=closers)
    assert isinstance(workflow, HttpScaleWorkflow)
    assert len(closers) == 1
    await closers[0]()


async def test_the_fake_fleets_runs_plan_from_the_day1_files(context: Day1Context) -> None:
    now = [datetime(2026, 11, 16, 9, 0, tzinfo=UTC)]
    fleet = settings(day1_scale_nodepools=True, day1_fake_fleet=True)
    fake = scale_workflow(fleet, metrics=metrics(), clock=lambda: now[0], closers=[])
    assert isinstance(fake, FakeScaleWorkflow)
    service = scale_service(fleet, fake, context.clusters, context.specs)
    assert service is not None
    assert scale_service(settings(), fake, context.clusters, context.specs) is None
    turned_off = settings(day1_scale_nodepools=False, day1_fake_fleet=True)
    assert scale_service(turned_off, fake, context.clusters, context.specs) is None
    admin = User(username="alice", role=Role.ADMIN)
    await service.start(LARK, ScaleTarget(4, nodepool=STORAGE), user=admin)
    assert (fake.started[0].mce_cluster, fake.started[0].cluster) == (LARK.mce, LARK.name)
    now[0] += timedelta(minutes=5)
    run = await service.run(LARK)
    assert run.result is not None
    assert [(c.name, c.before, c.after) for c in run.result.nodepools] == [(STORAGE, 2, 4)]
