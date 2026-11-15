"""The tuning rule ``nodepools[*].tuning_config`` (ADR-0061): save, create, drift, render."""

from __future__ import annotations

from typing import Any, cast

from wingman_day1.domain.locks import (
    MISSING,
    TUNING_RULE,
    InputPath,
    Lock,
    apply_locks,
    cluster_file_key,
    enforced_locks,
    lock_conflicts,
    lock_problems,
)
from wingman_day1.domain.machine_configs import MachineConfigCatalog
from wingman_day1.domain.sync_effects import rebooting, removals
from wingman_day1.domain.tuning_rule import compare, render_inputs, rendered_problems
from wingman_day1.domain.value_drift import ValueDrift, value_drift

RULE = "nodepools[*].tuning_config"


def flavor(*tuning: object) -> dict[str, Any]:
    return {"nodepools": [{"tuning_config": t} for t in tuning]}


# ── Save ─────────────────────────────────────────────────────────────────────


def test_the_rule_is_lockable_and_written_to_every_nodepool_s_tuning_config() -> None:
    assert str(TUNING_RULE) == RULE
    assert str(cluster_file_key(TUNING_RULE)) == "nodepool[*].tuningConfig"
    assert cluster_file_key(InputPath.parse("nodepools[0].tuning_config")) is None


def test_the_rule_saves_when_every_nodepool_names_the_same_set() -> None:
    values = flavor(["tuned-a", "perf-one"], ["perf-one", "tuned-a"], "tuned-a")
    assert lock_problems([RULE], flavor(["tuned-a", "perf-one"], ["perf-one", "tuned-a"])) == []
    (lock,) = enforced_locks([RULE], flavor(["tuned-a", "perf-one", "tuned-a"]))
    assert lock == Lock(TUNING_RULE, ["tuned-a", "perf-one"])
    assert lock_problems([RULE], values) == [
        "locked_paths: nodepools[*].tuning_config locks every nodepool to the same tuning "
        "profiles, but nodepools[2].tuning_config names other profiles than "
        "nodepools[0].tuning_config"
    ]


def test_the_rule_needs_nodepools_that_each_name_a_profile() -> None:
    assert lock_problems([RULE], {}) == [
        "locked_paths: nodepools[*].tuning_config is locked but spec.day1.values sets no "
        "nodepools for it"
    ]
    assert lock_problems([RULE], flavor("tuned-a", [])) == [
        "locked_paths: nodepools[*].tuning_config locks every nodepool's tuning profiles, but "
        "spec.day1.values.nodepools[1] sets none"
    ]
    assert enforced_locks([RULE], flavor([])) == ()
    assert lock_problems(["nodepools[0].tuning_config"], flavor("tuned-a"))[0].startswith(
        "locked_paths: nodepools[0].tuning_config cannot be locked; lockable inputs are "
    )


def test_the_tuning_rule_and_the_configs_rule_lock_together() -> None:
    values = {
        "nodepools": [
            {"configs": [{"name": "nm-conf", "hardware": "dell"}], "tuning_config": ["tuned-a"]}
        ]
    }
    locks = enforced_locks(["nodepools[*].configs", RULE], values)
    assert [str(lock.path) for lock in locks] == ["nodepools[*].configs", RULE]


# ── Create ───────────────────────────────────────────────────────────────────

LOCK = Lock(TUNING_RULE, ["tuned-a", "perf-one"])


def test_a_create_that_sends_the_same_set_in_any_order_or_none_passes() -> None:
    sent = {"nodepools": [{"tuning_config": ["perf-one", "tuned-a"]}, {"replicas": 2}]}
    assert lock_conflicts(sent, [LOCK], flavor="agent-tuned") == []
    filled, missing = apply_locks(sent, [LOCK])
    assert missing == []
    pools = cast("list[dict[str, object]]", filled["nodepools"])
    assert [p.get("tuning_config") for p in pools] == [
        ["perf-one", "tuned-a"],
        ["tuned-a", "perf-one"],
    ]


def test_a_create_that_sends_other_profiles_is_refused_naming_the_nodepool() -> None:
    sent = {
        "nodepools": [{"tuning_config": "tuned-a"}, {"tuning_config": []}, {"tuning_config": 3}]
    }
    assert lock_conflicts(sent, [LOCK], flavor="agent-tuned") == [
        'nodepools[0].tuning_config: locked by flavor agent-tuned: every nodepool has ["tuned-a", '
        '"perf-one"], in any order; the request sends ["tuned-a"]',
        'nodepools[1].tuning_config: locked by flavor agent-tuned: every nodepool has ["tuned-a", '
        '"perf-one"], in any order; the request sends []',
        'nodepools[2].tuning_config: locked by flavor agent-tuned: every nodepool has ["tuned-a", '
        '"perf-one"], in any order; the request sends 3',
    ]


# ── Render ───────────────────────────────────────────────────────────────────


def test_render_inputs_give_one_name_as_a_string_and_drop_none() -> None:
    inputs = {
        "nodepools": [
            {"tuning_config": ["tuned-a"]},
            {"tuning_config": ["tuned-a", "perf-one"]},
            {"tuning_config": []},
            {"tuning_config": {"bad": 1}},
            {"replicas": 2},
        ]
    }
    assert render_inputs(inputs)["nodepools"] == [
        {"tuning_config": "tuned-a"},
        {"tuning_config": ["tuned-a", "perf-one"]},
        {},
        {"tuning_config": {"bad": 1}},
        {"replicas": 2},
    ]
    assert render_inputs({"owner_anaf": "1"}) == {"owner_anaf": "1"}


def test_a_template_that_writes_other_names_is_caught() -> None:
    inputs = {"nodepools": [{"tuning_config": ["tuned-a", "perf-one"]}, {}]}
    good = {"nodepool": [{"tuningConfig": ["tuned-a", "perf-one"]}, {}]}
    assert rendered_problems(inputs, good) == []
    bad = {"nodepool": [{"tuningConfig": "['tuned-a', 'perf-one']"}, {"tuningConfig": "x"}]}
    found = rendered_problems(inputs, bad)
    assert [p.split(":")[0] for p in found] == [
        "nodepool[0].tuningConfig",
        "nodepool[1].tuningConfig",
    ]
    assert "must render tuning_config as given (ADR-0061)" in found[0]


# ── Drift ────────────────────────────────────────────────────────────────────


def drift(values: dict[str, Any]) -> tuple[ValueDrift, ...]:
    return value_drift([LOCK], values, cluster_name="prod-x-site1", catalog=MachineConfigCatalog())


def test_drift_compares_each_nodepool_s_profiles_as_a_set() -> None:
    values = {
        "nodepool": [
            {"name": "a", "tuningConfig": ["perf-one", "tuned-a", "tuned-a"]},
            {"name": "b", "tuningConfig": "tuned-a"},
            {"name": "c"},
            {"name": "d", "tuningConfig": ["tuned-b", "perf-one", "tuned-a"]},
            {"name": "e", "tuningConfig": 5},
            "not a pool",
        ]
    }
    found = drift(values)
    assert [
        (str(d.file_key), d.flavor_value, d.cluster_value, d.added, d.removed) for d in found
    ] == [
        ("nodepool[1].tuningConfig", ["tuned-a", "perf-one"], "tuned-a", ("perf-one",), ()),
        (
            "nodepool[2].tuningConfig",
            ["tuned-a", "perf-one"],
            MISSING,
            ("tuned-a", "perf-one"),
            (),
        ),
        (
            "nodepool[3].tuningConfig",
            ["tuned-a", "perf-one"],
            ["tuned-b", "perf-one", "tuned-a"],
            (),
            ("tuned-b",),
        ),
        ("nodepool[4].tuningConfig", ["tuned-a", "perf-one"], 5, ("tuned-a", "perf-one"), ()),
    ]
    assert all(d.reboots and d.is_tuning and not d.is_configs for d in found)
    assert [d.nodepool.name for d in found if d.nodepool] == ["b", "c", "d", "e"]


def test_a_one_name_rule_is_written_as_a_string() -> None:
    (only,) = value_drift(
        [Lock(TUNING_RULE, ["tuned-a"])],
        {"nodepool": [{"name": "a"}]},
        cluster_name="prod-x-site1",
        catalog=MachineConfigCatalog(),
    )
    assert (only.flavor_value, only.added) == ("tuned-a", ("tuned-a",))


def test_compare_is_a_set_difference_in_order() -> None:
    assert compare(["a", "b", "a"], ["c", "b", "c"]) == (["a"], ["c"])


def test_a_pool_whose_tuning_changes_reboots_once_and_removes_no_config() -> None:
    values = {"nodepool": [{"name": "a", "replicas": 3, "tuningConfig": "tuned-b"}]}
    (tuning,) = drift(values)
    configs = ValueDrift(
        InputPath.parse("nodepools[*].configs"),
        InputPath(("nodepool", 0, "configs")),
        [],
        [],
        nodepool=tuning.nodepool,
        added=("nic-ring-buffer",),
        removed=("old-config",),
    )
    assert [
        (r.nodepool.name, r.replicas, r.configs, r.tuning) for r in rebooting(values, [tuning])
    ] == [("a", 3, False, True)]
    assert [(r.configs, r.tuning) for r in rebooting(values, [configs, tuning])] == [(True, True)]
    assert [r.name for r in removals([configs, tuning])] == ["old-config"]
