"""A flavor's nodepool ratio: the save rules and the create check (ADR-0040)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.sizing import ratio_problems, show_ratio, sizing_problems


def pools(*replicas: object) -> dict[str, object]:
    return {"nodepools": [{"replicas": r} for r in replicas]}


def test_no_ratio_is_no_rule() -> None:
    assert ratio_problems([], nodepools=3, locked_paths=["nodepools[0].replicas"]) == []
    assert sizing_problems(pools(1, 7), (), flavor="f") == []


def test_one_whole_number_per_nodepool() -> None:
    assert ratio_problems([1, 2, 1], nodepools=3, locked_paths=[]) == []
    assert ratio_problems([1, 2], nodepools=3, locked_paths=[]) == [
        "nodepool_ratio: 2 entries for 3 nodepools; give one per nodepool"
    ]
    assert ratio_problems([1, 0, 1], nodepools=3, locked_paths=[]) == [
        "nodepool_ratio: each entry must be a whole number from 1 to 100"
    ]
    (too_big,) = ratio_problems([1, 101], nodepools=2, locked_paths=[])
    assert too_big.startswith("nodepool_ratio: each entry")


def test_a_sized_nodepools_replicas_cannot_be_locked() -> None:
    assert ratio_problems([1, 2], nodepools=2, locked_paths=["nodepools[1].replicas"]) == [
        "nodepool_ratio: nodepools[1].replicas is locked; a ratio sizes it, "
        "so it cannot be locked too"
    ]


@pytest.mark.parametrize("replicas", [(1, 2, 1), (2, 4, 2), (5, 10, 5), ("2", "4", "2")])
def test_replicas_of_one_size_follow_the_ratio(replicas: tuple[object, ...]) -> None:
    assert sizing_problems(pools(*replicas), (1, 2, 1), flavor="zones") == []


def test_nodepools_after_the_sized_ones_are_free() -> None:
    assert sizing_problems(pools(2, 4, 2, 9), (1, 2, 1), flavor="zones") == []


def test_replicas_off_the_ratio_are_refused_at_the_first_wrong_one() -> None:
    assert sizing_problems(pools(2, 3, 2), (1, 2, 1), flavor="zones") == [
        "nodepools[1].replicas: the flavor zones sizes its nodepools 1:2:1, so the replicas "
        "must be 1, 2 and 1 times one size (e.g. 2, 4, 2); got 2, 3, 2"
    ]
    (zero,) = sizing_problems(pools(0, 0, 0), (1, 2, 1), flavor="zones")
    assert zero.startswith("nodepools[0].replicas:")
    (missing,) = sizing_problems({"nodepools": [{}, {}, {}]}, (1, 2, 1), flavor="zones")
    assert missing.endswith("got none, none, none")


def test_fewer_nodepools_than_the_ratio_sizes_is_refused() -> None:
    assert sizing_problems(pools(2, 4), (1, 2, 1), flavor="zones") == [
        "nodepools: the flavor zones sizes 3 nodepools 1:2:1; the cluster has 2"
    ]


def test_the_ratio_is_shown_with_colons() -> None:
    assert show_ratio([1, 2, 1]) == "1:2:1"
