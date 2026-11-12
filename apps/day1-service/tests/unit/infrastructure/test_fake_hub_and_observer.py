"""FakeHubApi raises what HttpHubApi raises; the Observer maps errors to bounded outcomes."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import Dependency, Outcome, WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    Day2UnavailableError,
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    IdentityError,
    InvalidInputError,
    SegmentsManagerUnavailableError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.cached_hub import CachedHubApi
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.observed import (
    ArgoCdOperation,
    Day2Operation,
    HubOperation,
    LinkCheckOperation,
    OAuthOperation,
    Observer,
    SegmentsManagerOperation,
    ServerScanOperation,
    WorkflowsOperation,
    outcome_of,
)

MCE = "ocp4-prod-mce-site1-a"
HC = HostedClusterObservation("ocp4-x", "hcp-x", None, "4.16.27")
METRICS_DOC = Path(__file__).resolve().parents[5] / "docs/ops/metrics.md"


def fake() -> FakeHubApi:
    return FakeHubApi(
        hosted_clusters={MCE: [HC]},
        node_pools={
            (MCE, "hcp-x"): [NodePoolObservation("b", 2, 2), NodePoolObservation("a", 1, 0)]
        },
        infra_envs={"ocp4-prep-mce-site1-a": {"inventory": ["z", "y"], "other": ["x"]}},
        mces=["ocp4-test-mce-site1-a"],
        unavailable=["ocp4-prod-mce-site2-a"],
    )


async def test_fake_hub_serves_what_was_seeded() -> None:
    hub = fake()
    assert await hub.hosted_cluster(MCE, namespace="hcp-x", name="ocp4-x") == HC
    assert [p.name for p in await hub.node_pools(MCE, namespace="hcp-x")] == ["a", "b"]
    assert await hub.node_pools(MCE, namespace="hcp-empty") == []
    prep = "ocp4-prep-mce-site1-a"
    assert await hub.infra_envs(prep, namespace="inventory") == ["y", "z"]
    assert await hub.infra_envs(prep, namespace=None) == ["x", "y", "z"]
    assert await hub.infra_envs("ocp4-test-mce-site1-a", namespace="inventory") == []


async def test_fake_hub_raises_the_adapters_errors() -> None:
    hub = fake()
    with pytest.raises(HubObjectNotFoundError):
        await hub.hosted_cluster(MCE, namespace="hcp-x", name="openshift-missing")
    with pytest.raises(HubNotConfiguredError, match="ocp4-prod-mce-site2-a"):
        await hub.node_pools("ocp4-unknown", namespace="hcp-x")
    with pytest.raises(HubUnavailableError):
        await hub.infra_envs("ocp4-prod-mce-site2-a", namespace=None)
    with pytest.raises(HubNotConfiguredError, match=r"\(none\)"):
        await FakeHubApi().infra_envs(MCE, namespace=None)


async def test_fake_hub_serves_each_hubs_nodes_and_pods() -> None:
    worker = NodeObservation("w1", True, False, False, 250)
    hub = FakeHubApi(
        nodes={MCE: [worker, NodeObservation("m0", True, False, True, 250)]},
        pods={MCE: {"w1": 3}},
        denied=["ocp4-prod-mce-site1-b"],
    )
    assert [n.name for n in await hub.nodes(MCE)] == ["m0", "w1"]
    assert await hub.pods_per_node(MCE) == {"w1": 3}
    with pytest.raises(HubDeniedError, match="403"):
        await hub.nodes("ocp4-prod-mce-site1-b")
    with pytest.raises(HubNotConfiguredError):
        await hub.pods_per_node("ocp4-unknown")


async def test_the_cached_hub_shares_one_read_of_nodes_and_pods_and_keeps_no_failure() -> None:
    class Counting(FakeHubApi):
        calls = 0

        async def pods_per_node(self, mce: str) -> dict[str, int]:
            Counting.calls += 1
            await asyncio.sleep(0)
            return await super().pods_per_node(mce)

    inner = Counting(pods={MCE: {"w1": 3}}, unavailable=["ocp4-prod-mce-site2-a"])
    hub = CachedHubApi(inner, TtlCache(), ttl=5.0)
    first, second = await asyncio.gather(hub.pods_per_node(MCE), hub.pods_per_node(MCE))
    assert first == second == {"w1": 3}
    first["w1"] = 99
    assert await hub.pods_per_node(MCE) == {"w1": 3}, "a caller's copy is its own"
    assert Counting.calls == 1
    for _ in range(2):
        with pytest.raises(HubUnavailableError):
            await hub.nodes("ocp4-prod-mce-site2-a")


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (None, Outcome.OK),
        (HubObjectNotFoundError("x"), Outcome.NOT_FOUND),
        (HubDeniedError("x"), Outcome.DENIED),
        (HubUnavailableError("x"), Outcome.UNAVAILABLE),
        (Day2UnavailableError("x"), Outcome.UNAVAILABLE),
        (HubNotConfiguredError("x"), Outcome.REJECTED),
        (IdentityError("x"), Outcome.DENIED),
        (ServerNotFoundError("x"), Outcome.NOT_FOUND),
        (ServerScanDeniedError("x"), Outcome.DENIED),
        (ServerScanUnavailableError("x"), Outcome.UNAVAILABLE),
        (UninstallAlreadyRunningError("x"), Outcome.CONFLICT),
        (AmbiguousStartError("x"), Outcome.AMBIGUOUS),
        (WorkflowRefusedError("x"), Outcome.REJECTED),
        (WorkflowsUnavailableError("x"), Outcome.UNAVAILABLE),
        (SegmentsManagerUnavailableError("x"), Outcome.UNAVAILABLE),
        (InvalidInputError("x"), Outcome.ERROR),
        (RuntimeError("x"), Outcome.ERROR),
    ],
)
def test_outcomes_come_from_a_fixed_set(error: BaseException | None, outcome: Outcome) -> None:
    assert outcome_of(error) is outcome


def test_the_metrics_catalogue_lists_exactly_day1s_operations_per_dependency() -> None:
    """docs/ops/metrics.md's operations table is the contract dashboards read (ADR-0010)."""
    rows = re.findall(
        r"^\| `([a-z0-9_]+)` \| (`[a-z_]+`(?:, `[a-z_]+`)*) \|$",
        METRICS_DOC.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    documented = {
        dependency: set(re.findall(r"`([a-z_]+)`", ops))
        for dependency, ops in rows
        if dependency != "dependency"  # the header row
    }
    assert documented == {
        Dependency.KUBERNETES: set(HubOperation),
        Dependency.OPENSHIFT_OAUTH: set(OAuthOperation),
        Dependency.DAY2: set(Day2Operation),
        Dependency.SERVER_SCAN: set(ServerScanOperation),
        Dependency.WORKFLOWS: set(WorkflowsOperation),
        Dependency.SEGMENTS_MANAGER: set(SegmentsManagerOperation),
        Dependency.LINK_CHECK: set(LinkCheckOperation),
        Dependency.ARGOCD: set(ArgoCdOperation),
    }


async def test_observer_without_metrics_is_a_passthrough() -> None:
    async def answer() -> int:
        return 42

    assert (
        await Observer(Dependency.KUBERNETES, None).call(HubOperation.LIST_NODE_POOLS, answer())
        == 42
    )


async def test_observer_records_failures_and_reraises() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    observer = Observer(Dependency.KUBERNETES, metrics, timer=iter([10.0, 12.5]).__next__)

    async def boom() -> None:
        raise HubDeniedError("no")

    with pytest.raises(HubDeniedError):
        await observer.call(HubOperation.LIST_INFRA_ENVS, boom())
    labels = {"dependency": "kubernetes", "operation": "list_infra_envs"}
    registry = metrics.registry
    assert (
        registry.get_sample_value(
            "wingman_dependency_requests_total", {**labels, "outcome": "denied"}
        )
        == 1
    )
    assert (
        registry.get_sample_value("wingman_dependency_request_duration_seconds_sum", labels) == 2.5
    )
