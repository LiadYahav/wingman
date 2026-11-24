"""A KV cluster's workers and its zone check, from its file (ADR-0067's amendment)."""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.cluster_file import NodePoolValues
from wingman_day1.domain.kv_clusters import ZONE_LABEL, kv_workers, kv_zone_problems


def pool(
    infra_env: str = "r760-mtl-az1",
    *,
    replicas: int | None = 2,
    labels: Mapping[str, object] | None = None,
) -> NodePoolValues:
    return NodePoolValues(
        name=None,
        infra_env_name=infra_env,
        replicas=replicas,
        allow_deletion=False,
        configs=(),
        node_labels={ZONE_LABEL: "az1"} if labels is None else labels,
        tuning_config=None,
    )


def test_its_workers_are_every_nodepools_replicas() -> None:
    assert kv_workers([pool(replicas=2), pool("c200-mtl-az1", replicas=3)]) == 5
    assert kv_workers([pool(replicas=None)]) == 0
    assert kv_workers([]) == 0


def test_nodepools_that_name_the_zone_in_the_name_pass() -> None:
    assert kv_zone_problems("az1", [pool(), pool("c200-mtl-az1")]) == []


def test_a_nodepool_without_the_zone_or_with_another_is_flagged() -> None:
    problems = kv_zone_problems("az1", [pool(labels={}), pool(labels={ZONE_LABEL: "az2"})])
    assert problems == [
        f"nodepool[0] (r760-mtl-az1) names no zone: its nodeLabels have no {ZONE_LABEL}",
        "nodepool[1] (r760-mtl-az1) names zone 'az2', not 'az1' as the cluster's name does",
    ]


def test_no_nodepool_names_no_zone() -> None:
    assert kv_zone_problems("az1", []) == ["it has no NodePool, so it names no zone"]


def test_a_name_without_a_zone_needs_its_nodepools_to_agree_on_one() -> None:
    assert kv_zone_problems(None, [pool(), pool()]) == []
    two = [pool(), pool(labels={ZONE_LABEL: "az2"})]
    assert kv_zone_problems(None, two) == ["its NodePools name several zones (az1, az2): one only"]
    assert "names no zone" in kv_zone_problems(None, [pool(labels={})])[0]
