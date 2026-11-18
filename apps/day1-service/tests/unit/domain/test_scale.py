"""The update-nodepool workflow's types and the page's own reading of a cluster file (ADR-0062)."""

from __future__ import annotations

import yaml

from wingman_day1.domain.input_paths import InputPath
from wingman_day1.domain.locks import MISSING, Lock
from wingman_day1.domain.scale import (
    FileNodePool,
    HeldReplicas,
    ScaleRun,
    error_type,
    file_nodepools,
    held_back,
    replicas_locks,
    restore_lines,
    scale_down_policy,
    scale_name,
    scale_workflow_id,
)
from wingman_day1.domain.value_drift import NodepoolRef, ValueDrift

FILE = """\
nodepool:
- infraEnvName: cisco-m6-bat-yam-64c-512gb-zone-a
  replicas: 3
- infraEnvName: cisco-m6-bat-yam-64c-512gb-zone-b
  replicas: 2
- name: big
  infraEnvName: dell-r760-128c
- agentLabelSelector:
    nodeLabelValue: hp-gen11
  replicas: two
- labels: {}
"""


def pools(
    text: str = FILE, *, locked: dict[int, int] | None = None, flavor: str | None = None
) -> tuple[FileNodePool, ...]:
    return file_nodepools(
        yaml.safe_load(text), cluster_name="prod-alpha", locked=locked, flavor=flavor
    )


def test_the_run_id_is_the_file_stem_with_the_workflows_prefix() -> None:
    assert scale_workflow_id("ocp4-prod-alpha") == "update-nodepool-ocp4-prod-alpha"
    assert ScaleRun("update-nodepool-ocp4-prod-alpha", "running").cluster == "ocp4-prod-alpha"


def test_a_nodepool_is_named_as_the_chart_names_it_or_not_at_all() -> None:
    assert scale_name({"name": "big", "infraEnvName": "x"}, cluster_name="c") == "big"
    assert scale_name({"infraEnvName": "x"}, cluster_name="c") == "c-x"
    assert scale_name({"agentLabelSelector": {"nodeLabelValue": "y"}}, cluster_name="c") == "c-y"
    assert scale_name({"replicas": 2}, cluster_name="c") is None


def test_the_files_nodepools_carry_their_infraenv_replicas_and_lock() -> None:
    found = pools(locked={0: 3}, flavor="agent-sized")
    assert [(p.name, p.infra_env, p.replicas) for p in found] == [
        ("prod-alpha-cisco-m6-bat-yam-64c-512gb-zone-a", "cisco-m6-bat-yam-64c-512gb-zone-a", 3),
        ("prod-alpha-cisco-m6-bat-yam-64c-512gb-zone-b", "cisco-m6-bat-yam-64c-512gb-zone-b", 2),
        ("big", "dell-r760-128c", 1),
        ("prod-alpha-hp-gen11", "hp-gen11", None),
        (None, None, 1),
    ]
    assert (found[0].locked_replicas, found[0].locked_by) == (3, "agent-sized")
    assert (found[1].locked_replicas, found[1].locked_by) == (None, None)
    assert found[4].label == "nodepool[4]"
    assert found[4].unnamed is not None and "cannot be named" in found[4].unnamed
    assert found[0].unnamed is None


def test_a_nodepools_scale_down_policy_is_its_entrys_annotation_as_written() -> None:
    text = """\
nodepool:
- infraEnvName: dell-r660-zone-a
  annotations:
    redbull.io/scale-down-policy: fewest-pods
- infraEnvName: dell-r660-zone-b
  annotations:
    redbull.io/scale-down-policy: newest-first
    example.com/other: x
- infraEnvName: dell-r660-zone-c
  labels:
    redbull.io/scale-down-policy: least-utilized
"""
    assert [p.scale_down_policy for p in pools(text)] == ["fewest-pods", "newest-first", None]
    requested = {"annotations": {"redbull.io/scale-down-policy": "least-requested"}}
    assert scale_down_policy(requested) == "least-requested"
    assert scale_down_policy({"annotations": None}) is None
    assert scale_down_policy({"annotations": ["redbull.io/scale-down-policy"]}) is None
    assert scale_down_policy({"annotations": {"redbull.io/scale-down-policy": None}}) is None
    assert scale_down_policy({}) is None
    assert [p.scale_down_policy for p in pools()] == [None] * 5


def test_the_flavors_locked_replicas_by_position() -> None:
    locks = [
        Lock(InputPath.parse("nodepools[0].replicas"), 5),
        Lock(InputPath.parse("nodepools[2].replicas"), 1),
        Lock(InputPath.parse("nodepools[*].configs"), [{"name": "nm-conf"}]),
        Lock(InputPath.parse("owner_anaf"), "56"),
    ]
    assert replicas_locks(locks) == {0: 5, 2: 1}


def test_the_error_type_is_read_from_the_words_when_they_name_one() -> None:
    child = (
        "scale-down-nodepool-ocp4-prod-alpha failed — ArgoSyncRefusedError: something else is "
        "out of sync. Its history has the detail"
    )
    assert error_type(child) == "ArgoSyncRefusedError"
    assert error_type("the cluster has no NodePool x, on the MCE or in day1") is None
    assert error_type(None) is None


def _drift(index: int, key: str, cluster: object, flavor: object) -> ValueDrift:
    path = InputPath.parse(f"nodepool[{index}].{key}")
    lock = InputPath.parse(f"nodepools[{index}].{key}")
    return ValueDrift(lock, path, flavor, cluster, NodepoolRef(index, f"np{index}"))


def test_a_sync_holds_back_the_replicas_of_nodepools_on_main_and_keeps_the_rest() -> None:
    main = yaml.safe_load(FILE)
    replicas = _drift(0, "replicas", 3, 5)
    absent = _drift(2, "replicas", MISSING, 4)
    configs = _drift(1, "configs", [], [{"name": "a"}])
    written = yaml.safe_load(
        FILE.replace("replicas: 3", "replicas: 5").replace(
            "  infraEnvName: dell-r760-128c\n", "  infraEnvName: dell-r760-128c\n  replicas: 4\n"
        )
    )
    kept, held = held_back(main, written, [replicas, configs, absent], cluster_name="prod-alpha")
    assert kept == (configs,)
    assert held == (
        HeldReplicas(0, "prod-alpha-cisco-m6-bat-yam-64c-512gb-zone-a", 3, 5),
        HeldReplicas(2, "big", 1, 4),
    )
    assert restore_lines(held[:1]) == [
        "nodepool `prod-alpha-cisco-m6-bat-yam-64c-512gb-zone-a` replicas 3 → 5: restore it "
        "with update-nodepool (Scale, Nodes tab)"
    ]


def test_nothing_is_held_when_the_sync_moves_no_replicas() -> None:
    main = yaml.safe_load(FILE)
    configs = _drift(1, "configs", [], [{"name": "a"}])
    assert held_back(main, main, [configs], cluster_name="prod-alpha") == ((configs,), ())
