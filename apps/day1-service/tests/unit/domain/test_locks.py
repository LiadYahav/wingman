"""Flavor locks: the path syntax, the lockable inputs and their file keys, and enforcement."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.locks import (
    CONFIGS_RULE,
    EVERY,
    LOCKABLE,
    MISSING,
    InputPath,
    InvalidPathError,
    Lock,
    apply_locks,
    assigned,
    cluster_file_key,
    enforced_locks,
    entry_key,
    lock_conflicts,
    lock_problems,
    lookup,
    rule_entries,
    same_configs,
    same_value,
)

CONFIGS = [{"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}]
VALUES: dict[str, Any] = {
    "owner_merkaz": "1234",
    "platform": "kubevirt",
    "nodepools": [{"replicas": 3, "configs": CONFIGS}, {"node_labels": {"zone": "a"}}],
}


# ── Paths ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "segments"),
    [
        ("owner_merkaz", ("owner_merkaz",)),
        ("nodepools[0].configs", ("nodepools", 0, "configs")),
        ("nodepools[12].node_labels", ("nodepools", 12, "node_labels")),
        ("a[0][1].b.c", ("a", 0, 1, "b", "c")),
        ("_x", ("_x",)),
        ("nodepool[999].nodeLabels", ("nodepool", 999, "nodeLabels")),
        ("nodepools[*].configs", ("nodepools", EVERY, "configs")),
        ("a[*][0]", ("a", EVERY, 0)),
    ],
)
def test_a_path_parses_and_prints_as_written(text: str, segments: tuple[object, ...]) -> None:
    path = InputPath.parse(text)
    assert path.segments == segments
    assert str(path) == text


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "must start with an input name"),
        ("0abc", "must start with an input name"),
        ("[0]", "must start with an input name"),
        ("a..b", "unexpected '.' at character 2"),
        ("a.", "unexpected '.' at character 2"),
        ("a[01]", "unexpected '[' at character 2"),
        ("a[1000]", "unexpected '['"),
        ("a[-1]", "unexpected '['"),
        ("a[]", "unexpected '['"),
        ("a b", "unexpected ' '"),
        ("a[0]x", "unexpected 'x' at character 5"),
        ("a.b-c", "unexpected '-'"),
        ("nodepools.0.configs", "unexpected '.' at character 10"),
        ("a[**]", "unexpected '['"),
        ("a[*", "unexpected '['"),
        ("a.*", "unexpected '.'"),
        ("a" * 254, "longer than 253 characters"),
    ],
)
def test_anything_else_is_not_a_path(text: str, reason: str) -> None:
    with pytest.raises(InvalidPathError) as caught:
        InputPath.parse(text)
    assert reason in str(caught.value)


@given(
    st.lists(
        st.one_of(
            st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,8}", fullmatch=True),
            st.integers(min_value=0, max_value=999),
            st.just(EVERY),
        ),
        max_size=6,
    ),
    st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,8}", fullmatch=True),
)
def test_every_path_prints_to_text_that_parses_back(rest: list[Any], head: str) -> None:
    path = InputPath((head, *rest))
    assert InputPath.parse(str(path)) == path


def test_lookup_follows_names_and_positions() -> None:
    assert lookup(VALUES, InputPath.parse("nodepools[0].configs")) == CONFIGS
    assert lookup(VALUES, InputPath.parse("nodepools[1].node_labels.zone")) == "a"
    for missing in (
        "nodepools[2].replicas",
        "nodepools[1].replicas",
        "owner_anaf",
        "owner_merkaz[0]",
    ):
        assert lookup(VALUES, InputPath.parse(missing)) is MISSING
    assert lookup(VALUES, InputPath.parse("platform.x")) is MISSING
    assert lookup(VALUES, CONFIGS_RULE) is MISSING  # a rule names every position, not one
    assert InputPath.parse("nodepools[*].configs").is_rule
    assert not InputPath.parse("nodepools[0].configs").is_rule


def test_assigned_copies_along_the_path_and_needs_the_parent() -> None:
    path = InputPath.parse("nodepools[1].replicas")
    changed = assigned(VALUES, path, 5)
    assert changed is not None
    assert lookup(changed, path) == 5
    assert "replicas" not in VALUES["nodepools"][1]
    assert changed["nodepools"][0] is VALUES["nodepools"][0]  # ty: ignore[not-subscriptable]
    assert assigned(VALUES, InputPath.parse("owner_anaf"), "5") == {**VALUES, "owner_anaf": "5"}
    for no_parent in ("nodepools[2].replicas", "platform.x", "owner_merkaz[0]", "nope.x"):
        assert assigned(VALUES, InputPath.parse(no_parent), 1) is None
    assert assigned({"a": [1, 2]}, InputPath.parse("a[1]"), 9) == {"a": [1, 9]}
    assert assigned({"a": [1]}, InputPath.parse("a[1]"), 9) is None
    assert assigned(VALUES, CONFIGS_RULE, []) is None


# ── What can be locked, and where it is in the file ─────────────────────────


@pytest.mark.parametrize(
    ("input_path", "file_key"),
    [
        ("owner_merkaz", "owner.merkaz"),
        ("owner_anaf", "owner.anaf"),
        ("owner_mador", "owner.mador"),
        ("platform", "platform"),
        ("nodepools[0].replicas", "nodepool[0].replicas"),
        ("nodepools[3].configs", "nodepool[3].configs"),
        ("nodepools[1].node_labels", "nodepool[1].nodeLabels"),
        ("nodepools[*].configs", "nodepool[*].configs"),
    ],
)
def test_each_lockable_input_maps_to_its_cluster_file_key(input_path: str, file_key: str) -> None:
    assert str(cluster_file_key(InputPath.parse(input_path))) == file_key


@pytest.mark.parametrize(
    "path",
    [
        "nodepools",
        "nodepools[0]",
        "nodepools[0].infra_env",
        "nodepools[0].configs[0]",
        "nodepools[0].node_labels.zone",
        "owner",
        "owner_merkaz.x",
        "cluster_name",
        "openshift_release_version",
        "nodepools[*].replicas",
        "nodepools[*].node_labels",
        "nodepools[*]",
    ],
)
def test_nothing_else_has_a_file_key(path: str) -> None:
    assert cluster_file_key(InputPath.parse(path)) is None


def test_the_lockable_table_reads_as_the_docs_write_it() -> None:
    assert [str(shape) for shape in LOCKABLE] == [
        "owner_merkaz",
        "owner_anaf",
        "owner_mador",
        "platform",
        "nodepools[<i>].replicas",
        "nodepools[<i>].configs",
        "nodepools[<i>].node_labels",
        "nodepools[*].configs",
    ]


def test_every_lockable_input_is_one_the_fixture_template_writes_to_its_file_key() -> None:
    template = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
    for written in (
        "merkaz:",
        "anaf:",
        "mador:",
        "platform:",
        "replicas:",
        "configs:",
        "nodeLabels:",
    ):
        assert written in template
    for read in ("owner_merkaz", "owner_anaf", "owner_mador", "platform", "np.replicas"):
        assert read in template
    assert "np.configs" in template
    assert "np.node_labels" in template


# ── At flavor save ──────────────────────────────────────────────────────────


def test_lockable_paths_with_a_value_can_be_saved() -> None:
    paths = ["owner_merkaz", "platform", "nodepools[0].replicas", "nodepools[0].configs"]
    assert lock_problems([*paths, "nodepools[1].node_labels"], VALUES) == []
    assert lock_problems([], {}) == []


@pytest.mark.parametrize(
    ("path", "problem"),
    [
        ("nodepools.0.configs", "is not a template-input path like owner_merkaz"),
        ("cluster_name", "is set for each cluster at create"),
        ("openshift_release_version", "is set for each cluster at create"),
        ("site_name", "is set for each cluster at create"),
        ("mce", "is set for each cluster at create"),
        (
            "nodepools[0].infra_env",
            "cannot be locked; lockable inputs are owner_merkaz, owner_anaf",
        ),
        ("nodepools", "cannot be locked"),
        ("nodepools[0].configs[1]", "cannot be locked"),
        ("owner_anaf", "is locked but spec.day1.values sets no value for it"),
        ("nodepools[1].replicas", "is locked but spec.day1.values sets no value for it"),
        ("nodepools[2].configs", "is locked but spec.day1.values sets no value for it"),
    ],
)
def test_a_lock_that_fixes_no_lockable_value_is_refused(path: str, problem: str) -> None:
    problems = lock_problems([path], VALUES)
    assert len(problems) == 1
    assert problems[0].startswith("locked_paths: ")
    assert problem in problems[0]


def test_a_lock_listed_twice_and_too_many_locks_are_refused() -> None:
    assert lock_problems(["platform", "platform"], VALUES) == [
        "locked_paths: platform is listed twice"
    ]
    problems = lock_problems(["platform"] * 101, VALUES)
    assert problems[0] == "locked_paths: 101 paths; the limit is 100"


def test_only_valid_lockable_valued_paths_are_enforced() -> None:
    # Every path below has a value; only the lockable ones are enforced, each once.
    values = {
        **VALUES,
        "cluster_name": "x",
        "openshift_release_version": "4.18.22",
        "nodepools": [{**VALUES["nodepools"][0], "infra_env": "pool-a"}],
    }
    paths = ["platform", "platform", "cluster_name", "openshift_release_version"]
    paths += ["nodepools[0].infra_env", "nodepools", "owner_anaf", "x y"]
    assert enforced_locks([*paths, "nodepools[0].configs"], values) == (
        Lock(InputPath.parse("platform"), "kubevirt"),
        Lock(InputPath.parse("nodepools[0].configs"), CONFIGS),
    )


# ── At create ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        (3, 3, True),
        (3, "3", True),
        ("3", 3, True),
        (3, 3.0, True),
        (3, "03", False),
        (True, 1, False),
        (True, "true", False),
        (True, True, True),
        (None, None, True),
        (None, "", False),
        ("a", "a", True),
        ({"a": [1, {"b": "2"}]}, {"a": ["1", {"b": 2}]}, True),
        ({"a": 1}, {"a": 1, "b": None}, False),
        ([1, 2], [2, 1], False),
        ([1], (1,), True),
        ([1], [1, 1], False),
        (CONFIGS, [{"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}], True),
        (CONFIGS, [{"name": "nic-ring-buffer"}, {"name": "nm-conf", "hardware": "dell"}], False),
    ],
)
def test_values_are_compared_as_json(a: object, b: object, same: bool) -> None:
    assert same_value(a, b) is same
    assert same_value(b, a) is same


def test_a_request_that_sends_another_value_for_a_lock_conflicts() -> None:
    locks = enforced_locks(["platform", "nodepools[0].configs", "nodepools[0].replicas"], VALUES)
    sent = {"platform": "", "nodepools": [{"replicas": "3", "configs": [{"name": "x"}]}]}
    assert lock_conflicts(sent, locks, flavor="agent-dell") == [
        'platform: locked by flavor agent-dell to "kubevirt"; the request sends ""',
        'nodepools[0].configs: locked by flavor agent-dell to [{"name": "nm-conf", "hardware": '
        '"dell"}, {"name": "nic-ring-buffer"}]; the request sends [{"name": "x"}]',
    ]
    assert lock_conflicts({}, locks, flavor="agent-dell") == []


def test_a_long_value_is_cut_in_the_message() -> None:
    locks = (Lock(InputPath.parse("platform"), "k" * 200),)
    (problem,) = lock_conflicts({"platform": "x"}, locks, flavor="f")
    assert '"kkk' in problem
    assert '...; the request sends "x"' in problem
    assert len(problem) < 200


def test_locked_values_are_put_back_where_a_request_left_them_out() -> None:
    locks = enforced_locks(["platform", "nodepools[0].configs", "nodepools[0].replicas"], VALUES)
    sent = {"nodepools": [{"infra_env": "pool-a"}, {"infra_env": "pool-b"}]}
    inputs, problems = apply_locks(sent, locks)
    assert problems == []
    assert inputs == {
        "platform": "kubevirt",
        "nodepools": [
            {"infra_env": "pool-a", "configs": CONFIGS, "replicas": 3},
            {"infra_env": "pool-b"},
        ],
    }
    assert sent == {"nodepools": [{"infra_env": "pool-a"}, {"infra_env": "pool-b"}]}


def test_a_lock_on_a_nodepool_the_request_does_not_have_is_a_problem() -> None:
    locks = enforced_locks(["nodepools[1].node_labels"], VALUES)
    inputs, problems = apply_locks({"nodepools": [{"infra_env": "a"}]}, locks)
    assert problems == [
        'nodepools[1].node_labels: the flavor locks it to {"zone": "a"}, but the cluster has no '
        "nodepools[1]"
    ]
    assert inputs == {"nodepools": [{"infra_env": "a"}]}


# ── The configs rule: every nodepool has exactly these configs ──────────────

TEAM = [{"name": "nm-conf", "hardware": "dell"}, {"name": "chrony"}, {"name": "nic-ring-buffer"}]
RULE_VALUES: dict[str, Any] = {
    "nodepools": [
        {"replicas": 2, "configs": TEAM},
        # Another order and another hardware: the same configs by the rule.
        {
            "configs": [
                {"name": "nic-ring-buffer"},
                {"name": "nm-conf", "hardware": "cisco"},
                {"name": "chrony"},
            ]
        },
    ]
}
RULE = [{"name": "nm-conf"}, {"name": "chrony"}, {"name": "nic-ring-buffer"}]


def test_a_config_entry_compares_by_its_name_whatever_its_hardware() -> None:
    assert entry_key({"name": "nm-conf", "hardware": "dell"}) == "nm-conf"
    assert entry_key({"name": "chrony"}) == "chrony"
    assert entry_key("chrony") == '"chrony"'
    assert entry_key({"name": ""}) == '{"name": ""}'
    assert rule_entries(TEAM) == RULE
    assert same_configs(TEAM, list(reversed(RULE)))
    assert not same_configs(TEAM, RULE[:2])
    assert not same_configs(RULE, [*RULE, {"name": "chrony"}])  # each as often


def test_the_rule_can_be_saved_when_the_flavors_nodepools_agree() -> None:
    assert lock_problems(["nodepools[*].configs", "nodepools[0].replicas"], RULE_VALUES) == []
    assert enforced_locks(["nodepools[*].configs"], RULE_VALUES) == (Lock(CONFIGS_RULE, RULE),)


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({}, "is locked but spec.day1.values sets no nodepools[0].configs for it"),
        ({"nodepools": []}, "sets no nodepools[0].configs for it"),
        (
            {"nodepools": [{"configs": TEAM}, {"replicas": 1}]},
            "locks every nodepool's configs, but spec.day1.values.nodepools[1] sets none",
        ),
        (
            {"nodepools": ["x"]},
            "locks every nodepool's configs, but spec.day1.values.nodepools[0] sets none",
        ),
        (
            {"nodepools": [{"configs": TEAM}, {"configs": TEAM[:2]}]},
            "nodepools[1].configs names other configs than nodepools[0].configs",
        ),
        (
            {"nodepools": [{"configs": [{"name": "chrony"}]}]},
            "must list nm-conf exactly once: every nodepool needs its own network config",
        ),
        (
            {"nodepools": [{"configs": [*TEAM, {"name": "nm-conf", "hardware": "cisco"}]}]},
            "must list nm-conf exactly once",
        ),
    ],
)
def test_a_rule_without_one_agreed_value_is_refused(values: dict[str, Any], problem: str) -> None:
    (found,) = lock_problems(["nodepools[*].configs"], values)
    assert found.startswith("locked_paths: nodepools[*].configs ")
    assert problem in found
    assert enforced_locks(["nodepools[*].configs"], values) == ()


def test_a_position_cannot_lock_configs_beside_the_rule() -> None:
    paths = ["nodepools[*].configs", "nodepools[0].configs", "nodepools[0].replicas"]
    assert lock_problems(paths, RULE_VALUES) == [
        "locked_paths: nodepools[0].configs is covered by nodepools[*].configs, which locks "
        "every nodepool's configs; lock one or the other"
    ]
    # A stored spec that has both enforces the rule, not the position.
    assert enforced_locks(paths, RULE_VALUES) == (
        Lock(CONFIGS_RULE, RULE),
        Lock(InputPath.parse("nodepools[0].replicas"), 2),
    )


def test_a_create_whose_nodepools_break_the_rule_conflicts() -> None:
    locks = enforced_locks(["nodepools[*].configs"], RULE_VALUES)
    sent = {
        "nodepools": [
            {"configs": [{"name": "chrony"}, {"name": "nic-ring-buffer"}, {"name": "nm-conf"}]},
            {"configs": [{"name": "chrony"}]},
            {"infra_env": "no-configs-sent"},
            "not-a-pool",
            {"configs": "not-a-list"},
        ]
    }
    assert lock_conflicts(sent, locks, flavor="agent-baseline") == [
        'nodepools[1].configs: locked by flavor agent-baseline: every nodepool has [{"name": '
        '"nm-conf"}, {"name": "chrony"}, {"name": "nic-ring-buffer"}] (nm-conf for the '
        'nodepool\'s own hardware), in any order; the request sends [{"name": "chrony"}]'
    ]
    assert lock_conflicts({"nodepools": "x"}, locks, flavor="f") == []


def test_the_rule_fills_every_nodepool_that_sends_no_configs() -> None:
    locks = enforced_locks(["nodepools[*].configs"], RULE_VALUES)
    sent = {"nodepools": [{"infra_env": "a"}, {"infra_env": "b", "configs": TEAM}, "x"]}
    inputs, problems = apply_locks(sent, locks)
    assert problems == []
    assert inputs["nodepools"] == [
        {"infra_env": "a", "configs": RULE},
        {"infra_env": "b", "configs": TEAM},
        "x",
    ]
    filled = inputs["nodepools"][0]["configs"]  # ty: ignore[not-subscriptable]
    assert filled is not RULE
    assert filled[0] is not RULE[0]  # copies, never the flavor's own
    assert apply_locks({"platform": "x"}, locks) == ({"platform": "x"}, [])
