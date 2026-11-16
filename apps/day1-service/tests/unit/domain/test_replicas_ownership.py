"""Who changes a NodePool's replicas while scaling is on (ADR-0062).

One rule, ``replicas_changes``: each NodePool on main whose replicas a write
changes. A person's write is refused through ``edit_problems``; with the
setting off, nothing is.
"""

from __future__ import annotations

import yaml

from wingman_day1.domain.cluster_file import WorkflowKeys, edit_problems
from wingman_day1.domain.replicas_ownership import (
    REPLICAS_BY_SCALE,
    ReplicasChange,
    replicas_changes,
    replicas_problems,
)

MAIN = """\
owner:
  merkaz: "1234"
mastertag: 4.18.22-x86_64
nodepool:
- infraEnvName: dell-zone-a
  replicas: 3
- infraEnvName: dell-zone-b
  replicas: 3
- name: gpu
  infraEnvName: h200
"""
NAMELESS = MAIN + "- labels:\n    allowDeletion: false\n  replicas: 2\n"
"""An entry with neither name nor InfraEnv (the chart refuses it; matched by position)."""
SCALING = WorkflowKeys(replicas=True)


def values(text: str) -> dict[str, object]:
    return yaml.safe_load(text)


def changes(written: str, main: str = MAIN) -> tuple[ReplicasChange, ...]:
    return replicas_changes(values(main), values(written))


def test_a_nodepool_on_main_whose_replicas_change_is_named_by_its_infraenv() -> None:
    written = MAIN.replace("dell-zone-b\n  replicas: 3", "dell-zone-b\n  replicas: 5")
    assert changes(written) == (ReplicasChange("dell-zone-b", 1, 3, 5),)


def test_a_nodepool_is_named_by_its_name_first_and_its_position_last() -> None:
    written = NAMELESS.replace("  infraEnvName: h200\n", "  infraEnvName: h200\n  replicas: 4\n")
    written = written.replace("  replicas: 2\n", "  replicas: 0\n")
    expected = (ReplicasChange("gpu", 2, 1, 4), ReplicasChange("#3", 3, 2, 0))
    assert changes(written, NAMELESS) == expected


def test_an_absent_replicas_is_the_charts_one_both_ways() -> None:
    assert (
        changes(MAIN.replace("  infraEnvName: h200\n", "  infraEnvName: h200\n  replicas: 1\n"))
        == ()
    )
    removed = MAIN.replace("dell-zone-a\n  replicas: 3", "dell-zone-a")
    assert changes(removed) == (ReplicasChange("dell-zone-a", 0, 3, 1),)


def test_a_new_nodepool_with_its_first_replicas_is_not_a_change() -> None:
    written = MAIN + "- infraEnvName: hp-gen11\n  replicas: 6\n"
    assert changes(written) == ()


def test_removing_a_nodepool_is_not_a_change() -> None:
    written = MAIN.replace("- infraEnvName: dell-zone-b\n  replicas: 3\n", "")
    assert changes(written) == ()


def test_reordering_nodepools_is_not_a_change_and_their_new_position_is_named() -> None:
    reordered = MAIN.replace(
        "- infraEnvName: dell-zone-a\n  replicas: 3\n- infraEnvName: dell-zone-b\n  replicas: 3\n",
        "- infraEnvName: dell-zone-b\n  replicas: 4\n- infraEnvName: dell-zone-a\n  replicas: 3\n",
    )
    assert changes(reordered) == (ReplicasChange("dell-zone-b", 0, 3, 4),)


def test_a_new_cluster_has_nothing_on_main() -> None:
    assert replicas_changes({}, values(MAIN)) == ()


def test_the_problem_points_to_scale() -> None:
    written = MAIN.replace("dell-zone-a\n  replicas: 3", "dell-zone-a\n  replicas: 9")
    assert replicas_problems(values(MAIN), values(written)) == [
        f"nodepool dell-zone-a replicas: 3 → 9. {REPLICAS_BY_SCALE}"
    ]


def test_an_edit_that_changes_replicas_is_refused_only_while_scaling_is_on() -> None:
    written = MAIN.replace("dell-zone-a\n  replicas: 3", "dell-zone-a\n  replicas: 9")
    assert edit_problems(MAIN, written) == []
    assert edit_problems(MAIN, written, owned=SCALING) == [
        f"nodepool dell-zone-a replicas: 3 → 9. {REPLICAS_BY_SCALE}"
    ]


def test_an_edit_of_the_rest_is_not_refused_while_scaling_is_on() -> None:
    written = (
        MAIN.replace('merkaz: "1234"', 'merkaz: "4321"') + "- infraEnvName: hp\n  replicas: 2\n"
    )
    assert edit_problems(MAIN, written, owned=SCALING) == []


def test_a_review_edit_is_compared_with_main_not_with_its_branch() -> None:
    """An MR branch that already moved replicas: the reviewer's next edit must put them back."""
    branch = MAIN.replace("dell-zone-a\n  replicas: 3", "dell-zone-a\n  replicas: 7")
    edited = branch.replace('merkaz: "1234"', 'merkaz: "9"')
    assert edit_problems(branch, edited, owned=SCALING) == []
    assert edit_problems(branch, edited, owned=SCALING, main=MAIN) == [
        f"nodepool dell-zone-a replicas: 3 → 7. {REPLICAS_BY_SCALE}"
    ]
    restored = edited.replace("replicas: 7", "replicas: 3")
    assert edit_problems(branch, restored, owned=SCALING, main=MAIN) == []


def test_a_main_that_does_not_parse_has_no_nodepools_to_keep() -> None:
    written = MAIN.replace("dell-zone-a\n  replicas: 3", "dell-zone-a\n  replicas: 1")
    assert edit_problems(MAIN, written, owned=SCALING, main=": [") == []
