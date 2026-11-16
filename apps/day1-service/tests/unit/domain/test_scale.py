"""The update-nodepool workflow's types and the page's own reading of a cluster file (ADR-0062)."""

from __future__ import annotations

import pytest
import yaml

from wingman_day1.domain.input_paths import InputPath
from wingman_day1.domain.locks import MISSING, Lock
from wingman_day1.domain.scale import (
    FileNodePool,
    HeldReplicas,
    ScaleRun,
    belongs_to_kind,
    error_type,
    file_nodepools,
    held_back,
    kind_choices,
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


@pytest.mark.parametrize(
    ("infra_env", "selected"),
    [
        ("cisco-m6-bat-yam-64c-512gb", True),
        ("cisco-m6-bat-yam-64c-512gb-zone-a", True),
        ("cisco-m6-bat-yam-64c-512gb-b2", True),
        ("cisco-m6-bat-yam-64c-512gbx", False),
        (None, False),
    ],
)
def test_a_kind_selects_its_infraenv_and_what_follows_a_dash(
    infra_env: str | None, selected: bool
) -> None:
    assert belongs_to_kind(infra_env, "cisco-m6-bat-yam-64c-512gb") is selected


def test_the_kinds_are_the_infraenvs_and_the_common_start_of_siblings() -> None:
    choices = {c.kind: c for c in kind_choices(pools(locked={1: 2}, flavor="f"))}
    assert sorted(choices) == [
        "cisco-m6-bat-yam-64c-512gb-zone",
        "cisco-m6-bat-yam-64c-512gb-zone-a",
        "cisco-m6-bat-yam-64c-512gb-zone-b",
        "dell-r760-128c",
        "hp-gen11",
    ]
    zones = choices["cisco-m6-bat-yam-64c-512gb-zone"]
    assert [p.index for p in zones.nodepools] == [0, 1]
    assert zones.total == 5
    assert [p.index for p in zones.locked] == [1]
    assert choices["hp-gen11"].total is None
    assert choices["dell-r760-128c"].locked == ()


def test_different_hardware_is_never_one_kind() -> None:
    text = "nodepool:\n- infraEnvName: dell-r660-site1-128c\n- infraEnvName: dell-r760-site1-64c\n"
    assert [c.kind for c in kind_choices(pools(text))] == [
        "dell-r660-site1-128c",
        "dell-r760-site1-64c",
    ]


def test_a_shorter_infraenv_is_a_kind_that_selects_the_longer_one() -> None:
    text = "nodepool:\n- infraEnvName: hp-64c\n- infraEnvName: hp-64c-b2\n"
    choices = {c.kind: [p.index for p in c.nodepools] for c in kind_choices(pools(text))}
    assert choices == {"hp-64c": [0, 1], "hp-64c-b2": [1]}


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
    assert error_type("the NodePools of kind x are more than one replica apart") is None
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
