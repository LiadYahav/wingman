"""Value drift: a flavor's locked values against a cluster file (ADR-0036)."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.domain.git import RepoPath
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.locks import MISSING, InputPath, Lock, enforced_locks
from wingman_day1.domain.machine_configs import MachineConfigCatalog
from wingman_day1.domain.value_drift import (
    NodepoolRef,
    ValueDrift,
    compare_names,
    config_names,
    nodepool_name,
    value_drift,
)

FIXTURES = default_fixture_root()
MC_FILES = FIXTURES / "gitops-day1" / "platform-config" / "mc-files"
CLUSTERS = FIXTURES / "gitops-day1/platform-config/sites/site1/mces/ocp4-prod-mce-site1-a"
CATALOG = MachineConfigCatalog.from_files(
    RepoPath(f"mc-files/{p.relative_to(MC_FILES).as_posix()}")
    for p in MC_FILES.rglob("*")
    if p.is_file()
)
RULE = Lock(
    InputPath.parse("nodepools[*].configs"),
    [{"name": "nm-conf"}, {"name": "workers-chrony-configuration"}, {"name": "nic-ring-buffer"}],
)


def fixture(name: str) -> dict[str, object]:
    return load_values((CLUSTERS / "hostedClusters" / f"{name}.yaml").read_text())


def lock(path: str, value: object) -> Lock:
    return Lock(InputPath.parse(path), value)


def drift(locks: list[Lock], values: dict[str, Any], **kwargs: Any) -> tuple[ValueDrift, ...]:
    return value_drift(locks, values, cluster_name="prod-x-site1", catalog=CATALOG, **kwargs)


def pool(*names: str, **keys: Any) -> dict[str, Any]:
    return {"infraEnvName": "dell-a", "configs": [{"name": n} for n in names], **keys}


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("expected", "have", "added", "removed"),
    [
        (["a", "b"], ["b", "a"], [], []),
        (["a", "b"], ["a"], ["b"], []),
        (["a"], ["a", "c"], [], ["c"]),
        (["a"], ["a", "a"], [], ["a"]),
        (["a", "b", "c"], ["c", "x", "b", "y"], ["a"], ["x", "y"]),
        ([], [], [], []),
    ],
)
def test_names_compare_as_a_multiset_in_any_order(
    expected: list[str], have: list[str], added: list[str], removed: list[str]
) -> None:
    assert compare_names(expected, have) == (added, removed)


def test_a_nodepool_is_named_as_the_chart_names_it() -> None:
    assert nodepool_name({"name": "zone-a"}, 0, cluster_name="c") == "zone-a"
    assert nodepool_name({"infraEnvName": "dell"}, 0, cluster_name="c") == "c-dell"
    assert nodepool_name({}, 2, cluster_name="c") == "nodepool[2]"
    assert nodepool_name("x", 1, cluster_name="c") == "nodepool[1]"
    assert config_names([{"name": "a"}, "b"]) == ["a", '"b"']
    assert config_names("a") == []


# ── Owners, platform, replicas, labels ───────────────────────────────────────


def test_a_file_that_holds_every_locked_value_has_no_drift() -> None:
    locks = [
        lock("owner_merkaz", "1234"),
        lock("platform", "agent"),
        lock("nodepools[0].replicas", "3"),
        lock("nodepools[0].node_labels", {"zone": "a"}),
    ]
    values = {
        "owner": {"merkaz": 1234},  # a number in the file is its digits
        "nodepool": [pool(replicas=3, nodeLabels={"zone": "a"})],
    }
    assert drift(locks, values) == ()


def test_an_owner_the_file_holds_differently_or_not_at_all_drifts() -> None:
    locks = [lock("owner_merkaz", "0042"), lock("owner_anaf", "56"), lock("owner_mador", "7")]
    found = drift(locks, {"owner": {"merkaz": 42, "anaf": "56"}})
    assert found == (
        ValueDrift(InputPath.parse("owner_merkaz"), InputPath.parse("owner.merkaz"), "0042", 42),
        ValueDrift(InputPath.parse("owner_mador"), InputPath.parse("owner.mador"), "7", MISSING),
    )
    assert drift([lock("owner_anaf", "56")], {"owner": "x"})[0].cluster_value is MISSING


@pytest.mark.parametrize(
    ("locked", "file", "drifts"),
    [
        ("kubevirt", {"platform": "kubevirt"}, False),
        ("kubevirt", {}, True),
        ("kubevirt", {"platform": "agent"}, True),
        ("agent", {}, False),
        ("agent", {"platform": "agent"}, False),
        ("agent", {"platform": "kubevirt"}, True),
        ("anything-else", {}, False),  # the template writes the key only for kubevirt
    ],
)
def test_platform_is_kubevirt_or_the_agent_default(
    locked: str, file: dict[str, Any], drifts: bool
) -> None:
    found = drift([lock("platform", locked)], file)
    assert bool(found) is drifts
    if drifts:
        assert found[0].flavor_value == ("kubevirt" if locked == "kubevirt" else "agent")
        assert found[0].cluster_value == file.get("platform", MISSING)


def test_replicas_and_labels_drift_per_nodepool_with_its_name() -> None:
    locks = [lock("nodepools[1].replicas", 3), lock("nodepools[1].node_labels", {"zone": "b"})]
    values = {"nodepool": [pool(), pool(name="zone-b", replicas=2, nodeLabels={"zone": "c"})]}
    replicas, labels = drift(locks, values)
    assert (replicas.file_key, replicas.flavor_value, replicas.cluster_value) == (
        InputPath.parse("nodepool[1].replicas"),
        3,
        2,
    )
    assert replicas.nodepool == NodepoolRef(1, "zone-b")
    assert not replicas.is_configs
    assert (str(labels.file_key), labels.cluster_value) == ("nodepool[1].nodeLabels", {"zone": "c"})


def test_missing_replicas_drift_and_missing_empty_labels_do_not() -> None:
    values = {"nodepool": [{"infraEnvName": "dell-a"}]}
    (found,) = drift(
        [lock("nodepools[0].replicas", 2), lock("nodepools[0].node_labels", {})], values
    )
    assert found.cluster_value is MISSING
    assert str(found.file_key) == "nodepool[0].replicas"
    assert drift([lock("nodepools[0].node_labels", {"a": "b"})], values)[0].cluster_value is MISSING


@pytest.mark.parametrize(
    ("values", "decision"),
    [
        ({}, "the cluster has no nodepool[1]; sync does not add nodepools"),
        ({"nodepool": "x"}, "the cluster has no nodepool[1]; sync does not add nodepools"),
        ({"nodepool": [pool()]}, "the cluster has no nodepool[1]; sync does not add nodepools"),
        ({"nodepool": [pool(), "x"]}, "nodepool[1] is not a mapping"),
    ],
)
def test_a_position_the_file_does_not_have_needs_a_person(
    values: dict[str, Any], decision: str
) -> None:
    for path in ("nodepools[1].replicas", "nodepools[1].configs"):
        (found,) = drift([lock(path, 2)], values)
        assert found.needs_decision == decision
        assert not found.needs_hardware  # no hardware choice can fix it
        assert found.cluster_value is MISSING


# ── Configs by position ──────────────────────────────────────────────────────


def test_a_positional_configs_lock_compares_names_in_any_order_with_nm_conf_expanded() -> None:
    entries = [{"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}]
    held = {"nodepool": [pool("nic-ring-buffer", "nm-conf-prod-x-site1-dell")]}
    assert drift([lock("nodepools[0].configs", entries)], held) == ()
    other = {"nodepool": [pool("nm-conf-prod-x-site1-cisco", "nic-ring-buffer", "extra")]}
    (found,) = drift([lock("nodepools[0].configs", entries)], other)
    assert found.added == ("nm-conf-prod-x-site1-dell",)
    assert found.removed == ("nm-conf-prod-x-site1-cisco", "extra")
    assert found.flavor_value == [
        {"name": "nm-conf-prod-x-site1-dell"},
        {"name": "nic-ring-buffer"},
    ]
    assert found.cluster_value == other["nodepool"][0]["configs"]
    assert found.is_configs
    assert found.needs_decision is None


def test_no_configs_in_the_file_is_every_locked_config_missing() -> None:
    (found,) = drift(
        [lock("nodepools[0].configs", [{"name": "nic-ring-buffer"}])],
        {"nodepool": [{"infraEnvName": "a"}]},
    )
    assert (found.added, found.removed, found.cluster_value) == (
        ("nic-ring-buffer",),
        (),
        MISSING,
    )
    assert drift([lock("nodepools[0].configs", [])], {"nodepool": [{"infraEnvName": "a"}]}) == ()


# ── The configs rule ─────────────────────────────────────────────────────────


def test_the_rule_reads_each_nodepools_hardware_from_its_own_network_config() -> None:
    values = {
        "nodepool": [
            pool("nm-conf-prod-x-site1-dell", "workers-chrony-configuration", "nic-ring-buffer"),
            pool(
                "nic-ring-buffer", "nm-conf-prod-x-site1-dell-data", "workers-chrony-configuration"
            ),
        ]
    }
    assert drift([RULE], values) == ()


def test_the_rule_is_exact_extra_configs_are_removed_and_missing_ones_added() -> None:
    lark = value_drift(
        [RULE], fixture("ocp4-prod-lark-site1"), cluster_name="prod-lark-site1", catalog=CATALOG
    )
    first, second = lark
    assert first.nodepool == NodepoolRef(0, "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb")
    assert (first.added, first.removed) == ((), ("worker-kubeletconfig-reserved",))
    assert first.flavor_value == [
        {"name": "nm-conf-prod-lark-site1-dell"},
        {"name": "workers-chrony-configuration"},
        {"name": "nic-ring-buffer"},
    ]
    assert str(first.lock) == "nodepools[*].configs"
    assert str(first.file_key) == "nodepool[0].configs"
    assert (second.added, second.removed) == (("nic-ring-buffer",), ("restored-example-config",))
    assert second.flavor_value[0] == {"name": "nm-conf-prod-lark-site1-dell-data"}  # ty: ignore[not-subscriptable]
    assert first.needs_decision is None and second.needs_decision is None


def test_a_nodepool_without_or_with_several_network_configs_needs_a_person() -> None:
    heron = value_drift(
        [RULE], fixture("ocp4-prod-heron-site1"), cluster_name="prod-heron-site1", catalog=CATALOG
    )
    none, several = heron
    assert none.needs_decision == (
        "nodepool[0] has no network config (nm-conf-prod-heron-site1-<hardware>); choose its "
        "hardware type"
    )
    # The rest of the nodepool is still compared; the network part waits.
    assert (none.added, none.removed) == (("nic-ring-buffer",), ("worker-kubeletconfig-reserved",))
    assert none.flavor_value[0] == {"name": "nm-conf"}  # ty: ignore[not-subscriptable]
    assert none.needs_hardware and several.needs_hardware
    assert several.needs_decision == (
        "nodepool[1] has 2 network configs (nm-conf-prod-heron-site1-dell, "
        "nm-conf-prod-heron-site1-cisco); choose the hardware type it keeps"
    )
    assert (several.added, several.removed) == ((), ())
    assert several.nodepool == NodepoolRef(1, "prod-heron-site1-dell-b")


def test_a_persons_hardware_choice_decides_the_network_config() -> None:
    heron = value_drift(
        [RULE],
        fixture("ocp4-prod-heron-site1"),
        cluster_name="prod-heron-site1",
        catalog=CATALOG,
        hardware={0: "cisco", 1: "dell"},
    )
    none, several = heron
    assert none.needs_decision is None
    assert none.added == ("nm-conf-prod-heron-site1-cisco", "nic-ring-buffer")
    assert several.removed == ("nm-conf-prod-heron-site1-cisco",)
    assert several.added == ()


def test_another_clusters_network_config_is_replaced_by_this_ones() -> None:
    values = {
        "nodepool": [
            pool("nm-conf-prod-other-site1-dell", "workers-chrony-configuration", "nic-ring-buffer")
        ]
    }
    (found,) = drift([RULE], values)
    assert (found.added, found.removed) == (
        ("nm-conf-prod-x-site1-dell",),
        ("nm-conf-prod-other-site1-dell",),
    )


def test_the_rule_covers_nodepools_only_the_file_has() -> None:
    assert drift([RULE], {}) == ()
    (found,) = drift([RULE], {"nodepool": ["x"]})
    assert found.needs_decision == "nodepool[0] is not a mapping"
    assert str(found.file_key) == "nodepool[0].configs"


def test_a_positional_lock_without_hardware_reads_the_nodepools_own() -> None:
    values = {"nodepool": [pool("nm-conf-prod-x-site1-cisco")]}
    assert drift([lock("nodepools[0].configs", [{"name": "nm-conf"}])], values) == ()


def test_drift_is_in_lock_order_and_skips_what_is_not_lockable() -> None:
    locks = [
        lock("platform", "kubevirt"),
        lock("nodepools[0].infra_env", "x"),
        lock("owner_anaf", "1"),
    ]
    assert [str(d.lock) for d in drift(locks, {})] == ["platform", "owner_anaf"]


def test_the_rule_drift_compares_is_the_one_agent_baseline_enforces() -> None:
    spec_values = {
        "nodepools": [
            {
                "configs": [
                    {"name": "nm-conf", "hardware": "dell"},
                    {"name": "workers-chrony-configuration"},
                    {"name": "nic-ring-buffer"},
                ]
            }
        ]
    }
    (rule,) = enforced_locks(["nodepools[*].configs"], spec_values)
    assert rule == RULE
