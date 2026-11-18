"""A NodePool's scale-down policy: the input, the template guard, the lock and edits (ADR-0062)."""

from __future__ import annotations

import pytest

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.scale_down_policy import (
    GUIDE,
    edit_problems,
    given,
    input_problems,
    lock_problem,
    rendered_problems,
    template_problems,
)

TEMPLATE = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
OLD_TEMPLATE = (
    TEMPLATE[: TEMPLATE.index("{% if np.scale_down_policy")]
    + TEMPLATE[TEMPLATE.index("{% endif %}", TEMPLATE.index("{% if np.scale_down_policy")) + 12 :]
)
KEY = "redbull.io/scale-down-policy"


def pools(*policies: object) -> dict[str, object]:
    """Template inputs: one nodepool per policy, ``None`` leaving it out."""
    return {
        "nodepools": [
            {"infra_env": f"hw-{i}", **({} if p is None else {"scale_down_policy": p})}
            for i, p in enumerate(policies)
        ]
    }


def entry(policy: object = None, name: str = "a", **more: object) -> dict[str, object]:
    """A cluster file's ``nodepool[]`` entry with that annotation."""
    annotations = {} if policy is None else {"annotations": {KEY: policy}}
    return {"infraEnvName": name, "replicas": 2, **annotations, **more}


def test_a_nodepool_may_give_a_policy_the_workflow_knows_or_none() -> None:
    assert input_problems(pools("fewest-pods", None, "", "least-utilized")) == []
    assert given(pools("fewest-pods", None, "", "least-requested")) == [0, 3]
    assert input_problems(pools("random", 3)) == [
        "nodepools[0].scale_down_policy: 'random' is not a scale-down policy update-nodepool "
        "knows; use fewest-pods, least-requested or least-utilized, or none for the platform "
        "default",
        "nodepools[1].scale_down_policy: 3 (not text) is not a scale-down policy update-nodepool "
        "knows; "
        "use fewest-pods, least-requested or least-utilized, or none for the platform default",
    ]


def test_a_flavor_that_gives_a_policy_needs_a_template_that_reads_it() -> None:
    assert template_problems(pools("fewest-pods"), TEMPLATE) == []
    assert template_problems(pools(None), OLD_TEMPLATE) == []
    assert template_problems(pools("fewest-pods"), "") == [], "left to the create"
    assert template_problems(pools("fewest-pods"), "{% if %}") == [], "left to the create"
    (problem,) = template_problems(pools(None, "fewest-pods"), OLD_TEMPLATE)
    assert problem.startswith(
        "nodepools[1].scale_down_policy: the specs project's cluster-template.j2 does not read "
        "this input, so a cluster created from this flavor would scale down at random"
    )
    assert GUIDE in problem


def test_a_rendered_file_holds_the_policy_as_given_and_none_where_none_was() -> None:
    asked = pools("fewest-pods", None)
    assert rendered_problems(asked, {"nodepool": [entry("fewest-pods"), entry()]}) == []
    missing, unasked = rendered_problems(asked, {"nodepool": [entry(), entry("least-requested")]})
    assert missing.startswith(
        f"nodepool[0].annotations: the template wrote {KEY} None for 'fewest-pods'"
    )
    assert unasked.startswith(
        f"nodepool[1].annotations: the template wrote {KEY} 'least-requested'"
    )
    other = {"nodepool": [entry() | {"annotations": {"team.io/x": "y"}}]}
    assert rendered_problems(pools(None), other) == [], "only the policy's key is the template's"


def test_a_lock_fixes_a_policy_never_none() -> None:
    assert lock_problem("nodepools[0].scale_down_policy", pools("fewest-pods")) is None
    assert lock_problem("nodepools[0].replicas", pools(None)) is None
    for values in (pools(None), pools(""), {}):
        problem = lock_problem("nodepools[0].scale_down_policy", values)
        assert problem is not None
        assert problem.startswith("locked_paths: nodepools[0].scale_down_policy is locked to no")


@pytest.mark.parametrize(
    ("old", "new", "refused"),
    [
        ([entry()], [entry("fewest-pods")], False),
        ([entry("fewest-pods")], [entry("least-utilized")], False),
        ([entry("fewest-pods")], [entry()], False),
        ([entry()], [entry("random")], True),
        ([entry("random")], [entry("random", replicas=3)], False),
        ([entry("random", name="a")], [entry("random", name="b")], True),
        ([], [entry("random")], True),
    ],
)
def test_an_edit_may_set_only_a_policy_the_workflow_knows(
    old: list[dict[str, object]], new: list[dict[str, object]], refused: bool
) -> None:
    problems = edit_problems({"nodepool": old}, {"nodepool": new})
    assert bool(problems) is refused
    if refused:
        assert problems == [
            f"nodepool[0].annotations.{KEY}: 'random' is not a scale-down policy update-nodepool "
            "knows; use fewest-pods, least-requested or least-utilized, or remove the annotation"
        ]
