"""FakeHubApi raises what HttpHubApi raises; the Observer maps errors to bounded outcomes."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import Dependency, Outcome, WingmanMetrics
from wingman_day1.domain.errors import (
    Day2UnavailableError,
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    IdentityError,
    InvalidInputError,
)
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.observed import HubOperation, Observer, outcome_of

MCE = "ocp4-prod-mce-site1-a"
HC = HostedClusterObservation("ocp4-x", "hcp-x", None, "4.16.27")


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
        (InvalidInputError("x"), Outcome.ERROR),
        (RuntimeError("x"), Outcome.ERROR),
    ],
)
def test_outcomes_come_from_a_fixed_set(error: BaseException | None, outcome: Outcome) -> None:
    assert outcome_of(error) is outcome


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
