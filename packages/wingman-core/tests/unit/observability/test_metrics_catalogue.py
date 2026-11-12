"""The metric catalogue is pinned: code, docs and label rules agree."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from wingman_core.domain.errors import (
    AmbiguousWriteError,
    NotFoundError,
    PermissionDeniedError,
)
from wingman_core.domain.git import RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.observability.instrumented_gitlab import InstrumentedGitLab
from wingman_core.observability.metrics import (
    OTHER,
    Outcome,
    PlacementDecision,
    WingmanMetrics,
    method_label,
    outcome_of,
    status_class,
)
from wingman_core.web.metrics import install_metrics

DOCS = Path(__file__).resolve().parents[5] / "docs" / "ops" / "metrics.md"

EXPECTED = {
    "wingman_build_info": ("gauge", {"component", "version", "commit"}),
    "wingman_http_requests": ("counter", {"method", "route", "status_class"}),
    "wingman_http_request_duration_seconds": ("histogram", {"method", "route"}),
    "wingman_dependency_requests": ("counter", {"dependency", "operation", "outcome"}),
    "wingman_dependency_request_duration_seconds": ("histogram", {"dependency", "operation"}),
    "wingman_placement_decisions": ("counter", {"decision"}),
}


def make_metrics() -> WingmanMetrics:
    return WingmanMetrics(CollectorRegistry(), component="day1", version="1.2.3", commit="abc1234")


def sample(metrics: WingmanMetrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels)


def test_catalogue_is_exactly_the_documented_one() -> None:
    metrics = make_metrics()
    families = {
        family.name: (family.type, {label for s in family.samples for label in s.labels} - {"le"})
        for family in metrics.registry.collect()
    }
    for name, (kind, labels) in EXPECTED.items():
        assert families[name][0] == kind
        if labels and families[name][1]:
            assert families[name][1] == labels
    assert set(families) == set(EXPECTED)


def test_docs_table_lists_exactly_the_registered_metrics() -> None:
    documented = set(
        re.findall(r"^\| `(wingman_[a-z_]+)` \|", DOCS.read_text(encoding="utf-8"), re.MULTILINE)
    )
    registered = {
        name if name.endswith(("_info", "_seconds")) else f"{name}_total" for name in EXPECTED
    }
    assert documented == registered


def test_alerted_outcomes_exist_at_zero_before_any_call() -> None:
    metrics = make_metrics()
    for outcome in ("ok", "denied", "unavailable", "ambiguous"):
        labels = {"dependency": "gitlab", "operation": "commit", "outcome": outcome}
        assert sample(metrics, "wingman_dependency_requests_total", **labels) == 0.0
    assert (
        sample(metrics, "wingman_build_info", component="day1", version="1.2.3", commit="abc1234")
        == 1.0
    )


def test_placement_decisions_are_a_fixed_set() -> None:
    metrics = make_metrics()
    for decision in (*PlacementDecision, "picked", "maybe"):
        metrics.observe_placement(decision)
    name = "wingman_placement_decisions_total"
    assert sample(metrics, name, decision="picked") == 2.0
    assert sample(metrics, name, decision="override") == 1.0
    assert sample(metrics, name, decision="refused") == 1.0
    assert sample(metrics, name, decision=OTHER) == 1.0


@pytest.mark.parametrize(
    ("method", "label"), [("get", "GET"), ("PROPFIND", OTHER), ("Delete", "DELETE")]
)
def test_unknown_methods_become_other(method: str, label: str) -> None:
    assert method_label(method) == label


@pytest.mark.parametrize(
    ("status", "label"), [(200, "2xx"), (404, "4xx"), (503, "5xx"), (99, OTHER), (600, OTHER)]
)
def test_status_classes(status: int, label: str) -> None:
    assert status_class(status) == label


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (None, Outcome.OK),
        (NotFoundError("x"), Outcome.NOT_FOUND),
        (PermissionDeniedError("x"), Outcome.DENIED),
        (AmbiguousWriteError("x"), Outcome.AMBIGUOUS),
        (RuntimeError("x"), Outcome.ERROR),
    ],
)
def test_outcome_of(error: Exception | None, outcome: Outcome) -> None:
    assert outcome_of(error) is outcome


async def test_instrumented_gitlab_counts_successes_and_failures() -> None:
    metrics = make_metrics()
    fake = InMemoryGitLab()
    project = fake.create_project("g/p", {"a.yaml": "a: 1\n"})
    ticks = iter([0.0, 0.5, 1.0, 1.25])
    gitlab = InstrumentedGitLab(fake, metrics, timer=lambda: next(ticks))
    await gitlab.read_file(project.id, RepoPath("a.yaml"), "main")
    with pytest.raises(NotFoundError):
        await gitlab.read_file(project.id, RepoPath("missing.yaml"), "main")
    base = {"dependency": "gitlab", "operation": "read_file"}
    assert sample(metrics, "wingman_dependency_requests_total", **base, outcome="ok") == 1.0
    assert sample(metrics, "wingman_dependency_requests_total", **base, outcome="not_found") == 1.0
    assert sample(metrics, "wingman_dependency_request_duration_seconds_sum", **base) == 0.75


async def test_metrics_endpoint_and_route_templates() -> None:
    metrics = make_metrics()
    app = FastAPI()
    install_metrics(app, metrics)

    @app.get("/api/day1/clusters/{name}")
    async def cluster(name: str) -> dict[str, str]:
        return {"name": name}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        for name in ("a", "b"):
            assert (await client.get(f"/api/day1/clusters/{name}")).status_code == 200
        assert (await client.get("/nowhere")).status_code == 404
        scrape = await client.get("/metrics")
    assert scrape.status_code == 200
    labels = {"method": "GET", "route": "/api/day1/clusters/{name}", "status_class": "2xx"}
    assert sample(metrics, "wingman_http_requests_total", **labels) == 2.0
    unmatched = {"method": "GET", "route": "<unmatched>", "status_class": "4xx"}
    assert sample(metrics, "wingman_http_requests_total", **unmatched) == 1.0
    assert "wingman_build_info" in scrape.text
    assert "/metrics" not in app.openapi()["paths"]
