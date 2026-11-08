"""Live status from the MCE hubs: which HostedCluster is read, and failures in ``error``."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.status import StatusService
from wingman_day1.domain.errors import HubNotConfiguredError, HubUnavailableError
from wingman_day1.domain.status import Condition, HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi

MCE = "ocp4-prod-mce-site1-a"
HERZI = "ocp4-prod-herzi-site1"
HERZI_PATH = f"sites/site1/mces/{MCE}/hostedClusters/{HERZI}.yaml"
HEALTHY = (Condition("Available", "True"),)


def hub_with(
    name: str, namespace: str, *, pools: tuple[NodePoolObservation, ...] = ()
) -> FakeHubApi:
    return FakeHubApi(
        hosted_clusters={
            MCE: [HostedClusterObservation(name, namespace, None, "4.16.27", HEALTHY)]
        },
        node_pools={(MCE, namespace): list(pools)},
    )


def status_of(app: Any) -> StatusService:
    context: Day1Context = app.state.day1
    assert context.status is not None
    return context.status


async def test_production_reads_the_hosted_cluster_the_chart_names_after_the_file(
    context: Day1Context,
) -> None:
    # The chart names the HostedCluster ocp4-<clusterName> (the file stem) in
    # hcp-<clusterName>. 3.0.1 asked for openshift-<clusterName>, so every
    # status read was a 404 on every MCE.
    assert context.status is not None
    status = await context.status.status(HERZI, MCE)
    assert (status.hosted_cluster, status.namespace) == (
        "ocp4-prod-herzi-site1",
        "hcp-prod-herzi-site1",
    )
    assert status.error is None
    assert status.hc_problems == ()
    assert status.ocp_version == "4.16.27"
    assert [p.name for p in status.node_pools] == ["prod-herzi-site1-dell"]


async def test_the_sandbox_keeps_the_whole_file_stem(
    support: Any, gitlab: InMemoryGitLab, identity: Any, clock: Any
) -> None:
    hub = hub_with("ocp4-ocp4-prod-herzi-site1", "hcp-ocp4-prod-herzi-site1")
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=FakeDay2Addons(),
        clock=clock,
        DAY1_CLUSTER_NAME_STRIP_PREFIX="",
    )
    status = await status_of(app).status(HERZI, MCE)
    assert status.error is None
    assert status.namespace == "hcp-ocp4-prod-herzi-site1"


async def test_a_clustername_key_in_the_file_wins(
    support: Any, gitlab: InMemoryGitLab, identity: Any, clock: Any
) -> None:
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=HERZI_PATH,
        content="clusterName: herzi-special\nmastertag: 4.16.27-x86_64\n",
    )
    app = support.build_app(
        gitlab=gitlab,
        hub=hub_with("ocp4-herzi-special", "hcp-herzi-special"),
        identity=identity,
        day2=FakeDay2Addons(),
        clock=clock,
    )
    status = await status_of(app).status(HERZI, MCE)
    assert (status.hosted_cluster, status.error) == ("ocp4-herzi-special", None)


async def test_a_cluster_not_merged_yet_derives_its_name(context: Day1Context) -> None:
    assert context.status is not None
    target = await context.status.hosted_cluster_of("ocp4-prod-new-site1", MCE)
    assert (target.name, target.namespace) == ("ocp4-prod-new-site1", "hcp-prod-new-site1")


@pytest.mark.parametrize(
    ("hub", "kind"),
    [
        (FakeHubApi(mces=()), "HubNotConfigured"),
        (FakeHubApi(unavailable=[MCE]), "HubUnavailable"),
        (FakeHubApi(mces=[MCE]), "HubObjectNotFound"),
    ],
)
async def test_a_hub_failure_is_reported_in_the_status(
    support: Any, gitlab: InMemoryGitLab, identity: Any, clock: Any, hub: FakeHubApi, kind: str
) -> None:
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=FakeDay2Addons(), clock=clock
    )
    status = await status_of(app).status(HERZI, MCE)
    assert status.error is not None
    assert status.error.startswith(f"{kind}:")
    assert status.hosted_cluster == "ocp4-prod-herzi-site1"


class _NodePoolsDown(FakeHubApi):
    async def node_pools(self, mce: str, *, namespace: str) -> list[NodePoolObservation]:
        raise HubUnavailableError("NodePool list timed out")


async def test_a_node_pool_failure_is_a_hosted_cluster_problem(
    support: Any, gitlab: InMemoryGitLab, identity: Any, clock: Any
) -> None:
    hub = _NodePoolsDown(
        hosted_clusters={
            MCE: [
                HostedClusterObservation(
                    "ocp4-prod-herzi-site1", "hcp-prod-herzi-site1", None, None, HEALTHY
                )
            ]
        }
    )
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=FakeDay2Addons(), clock=clock
    )
    status = await status_of(app).status(HERZI, MCE)
    assert status.error is None
    assert status.hc_problems == ("NodePool fetch failed: NodePool list timed out",)


async def test_unhealthy_conditions_become_problems(
    support: Any, gitlab: InMemoryGitLab, identity: Any, clock: Any
) -> None:
    pool = NodePoolObservation(
        "prod-herzi-site1-dell",
        3,
        1,
        (
            Condition("Ready", "False", "WaitingForAgents", "0/3"),
            Condition("UpdatingConfig", "True"),
        ),
    )
    hub = FakeHubApi(
        hosted_clusters={
            MCE: [
                HostedClusterObservation(
                    "ocp4-prod-herzi-site1",
                    "hcp-prod-herzi-site1",
                    None,
                    None,
                    (Condition("Available", "False", "Waiting"), Condition("Degraded", "True")),
                )
            ]
        },
        node_pools={(MCE, "hcp-prod-herzi-site1"): [pool]},
    )
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=FakeDay2Addons(), clock=clock
    )
    status = await status_of(app).status(HERZI, MCE)
    assert len(status.hc_problems) == 2
    assert status.node_pools[0].ready_replicas == 1
    assert len(status.node_pools[0].problems) == 2


async def test_bulk_status_gives_every_cluster_an_entry(context: Day1Context) -> None:
    assert context.status is not None
    statuses = await context.status.statuses([(HERZI, MCE), ("ocp4-prod-hawk-site1", MCE)])
    assert set(statuses) == {HERZI, "ocp4-prod-hawk-site1"}
    assert statuses[HERZI].error is None
    assert statuses["ocp4-prod-hawk-site1"].error is not None


async def test_infraenvs_come_from_the_hub_and_an_unconfigured_mce_raises(
    context: Day1Context,
) -> None:
    assert context.status is not None
    assert await context.status.infra_envs(MCE) == ["dell-r660-site1-128c-1024gb-5tb"]
    with pytest.raises(HubNotConfiguredError):
        await context.status.infra_envs("ocp4-prep-mce-site1-a")


async def test_watch_yields_a_status_then_waits_the_interval(context: Day1Context) -> None:
    assert context.status is not None
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    stream = context.status.watch(HERZI, MCE, interval=7.0, sleep=sleep)
    assert isinstance(stream, AsyncGenerator)
    first = await anext(stream)
    second = await anext(stream)
    await stream.aclose()
    assert first.cluster_name == second.cluster_name == HERZI
    assert waits == [7.0]
