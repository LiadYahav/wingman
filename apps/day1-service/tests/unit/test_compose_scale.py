"""Scaling's part of the composition root (ADR-0062): off by default, real or the fake fleet's."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client import CollectorRegistry
from pydantic import SecretStr, ValidationError

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


def test_scaling_is_off_by_default_and_needs_an_orchestrator() -> None:
    assert settings().day1_scale_nodepools is False
    with pytest.raises(ValidationError, match="DAY1_SCALE_NODEPOOLS=true needs WORKFLOWS_API_URL"):
        settings(day1_scale_nodepools=True)
    on = settings(
        day1_scale_nodepools=True, workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN
    )
    assert on.day1_scale_nodepools is True
    assert settings(day1_scale_nodepools=True, day1_fake_fleet=True).day1_scale_nodepools is True


async def test_the_orchestrators_adapter_only_when_turned_on() -> None:
    closers: list[Close] = []
    off = settings(workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN)
    assert scale_workflow(off, metrics=metrics(), clock=system_clock, closers=closers) is None
    on = settings(
        day1_scale_nodepools=True, workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN
    )
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
    admin = User(username="alice", role=Role.ADMIN)
    await service.start(LARK, ScaleTarget(4, nodepool=STORAGE), user=admin)
    assert (fake.started[0].mce_cluster, fake.started[0].cluster) == (LARK.mce, LARK.name)
    now[0] += timedelta(minutes=5)
    run = await service.run(LARK)
    assert run.result is not None
    assert [(c.name, c.before, c.after) for c in run.result.nodepools] == [(STORAGE, 2, 4)]
