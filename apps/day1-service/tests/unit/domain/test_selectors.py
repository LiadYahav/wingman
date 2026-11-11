"""Label selectors with Kubernetes' rules, as the Agent provider applies a NodePool's."""

from __future__ import annotations

import pytest

from wingman_day1.domain.selectors import LabelRequirement, LabelSelector, Operator, selects

INFRA_ENV = "infraenvs.agent-install.openshift.io"
AGENT = {INFRA_ENV: "dell-r660-site1", "zone": "a"}


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        (LabelSelector(match_labels=((INFRA_ENV, "dell-r660-site1"),)), True),
        (LabelSelector(match_labels=((INFRA_ENV, "dell-r760-site1"),)), False),
        (LabelSelector(match_labels=((INFRA_ENV, "dell-r660-site1"), ("zone", "b"))), False),
        (LabelSelector(match_labels=(("missing", "x"),)), False),
    ],
)
def test_every_match_label_must_hold(selector: LabelSelector, expected: bool) -> None:
    assert selector.matches(AGENT) is expected


@pytest.mark.parametrize(
    ("operator", "values", "labels", "expected"),
    [
        (Operator.IN, ("a", "b"), {"zone": "a"}, True),
        (Operator.IN, ("b",), {"zone": "a"}, False),
        (Operator.IN, ("a",), {}, False),
        (Operator.NOT_IN, ("b",), {"zone": "a"}, True),
        (Operator.NOT_IN, ("a",), {"zone": "a"}, False),
        (Operator.NOT_IN, ("a",), {}, True),
        (Operator.EXISTS, (), {"zone": ""}, True),
        (Operator.EXISTS, (), {}, False),
        (Operator.DOES_NOT_EXIST, (), {}, True),
        (Operator.DOES_NOT_EXIST, (), {"zone": "a"}, False),
    ],
)
def test_expressions_follow_kubernetes(
    operator: Operator, values: tuple[str, ...], labels: dict[str, str], expected: bool
) -> None:
    requirement = LabelRequirement("zone", operator, values)
    assert requirement.matches(labels) is expected
    assert LabelSelector(match_expressions=(requirement,)).matches(labels) is expected


def test_labels_and_expressions_must_all_hold() -> None:
    selector = LabelSelector(
        match_labels=((INFRA_ENV, "dell-r660-site1"),),
        match_expressions=(LabelRequirement("zone", Operator.IN, ("a",)),),
    )
    assert selector.matches(AGENT)
    assert not selector.matches({**AGENT, "zone": "b"})


def test_an_empty_selector_and_no_selector_select_every_agent() -> None:
    assert LabelSelector().matches({})
    assert selects(None, AGENT)
    assert LabelSelector().describe() is None


def test_a_selector_is_described_as_kubectl_writes_it() -> None:
    selector = LabelSelector(
        match_labels=(("zone", "a"), (INFRA_ENV, "dell-r660-site1")),
        match_expressions=(
            LabelRequirement("rack", Operator.IN, ("r1", "r2")),
            LabelRequirement("gpu", Operator.NOT_IN, ("none",)),
            LabelRequirement("ssd", Operator.EXISTS),
            LabelRequirement("retired", Operator.DOES_NOT_EXIST),
        ),
    )
    assert selector.describe() == (
        f"{INFRA_ENV}=dell-r660-site1, zone=a, rack in (r1, r2), gpu notin (none), ssd, !retired"
    )
