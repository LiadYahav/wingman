"""Agent labels every NodePool excludes (ADR-0065): keys, a create, the guard, edits, the plan."""

from __future__ import annotations

import pytest

from wingman_day1.domain.excluded_agent_labels import (
    GUIDE,
    edit_problems,
    flavor_problems,
    input_problems,
    label_key_problems,
    labels_for,
    parse,
    plan,
    rendered_problems,
    setting_problems,
    summary,
    with_labels,
)

USED = "redbull.io/used"


def pool(name: str, **more: object) -> dict[str, object]:
    return {"infraEnvName": name, "replicas": 2, **more}


@pytest.mark.parametrize("key", [USED, "used", "a.b/c_d-e.f", "agent-install.openshift.io/bmh"])
def test_a_label_key_is_an_optional_dns_prefix_and_a_name(key: str) -> None:
    assert label_key_problems(key) == []


@pytest.mark.parametrize(
    "key", ["", "not a key", "Redbull.IO/used", "a/", "-used", "x" * 64, "a/b/c"]
)
def test_anything_else_is_not_a_label_key(key: str) -> None:
    assert label_key_problems(key) != []


def test_the_setting_is_comma_separated_trimmed_and_each_key_once() -> None:
    assert parse("") == ()
    assert parse(f" {USED}, used ,,{USED} ") == (USED, "used")
    assert setting_problems(parse(f"{USED},used")) == []
    assert setting_problems(parse("not a key")) != []
    assert setting_problems([f"k{n}" for n in range(17)]) == ["17 keys; the limit is 16"]


def test_a_create_gets_the_deployments_keys_and_kubevirt_none() -> None:
    assert labels_for(None, (USED,)) == [USED]
    assert labels_for("kubevirt", (USED,)) == []
    assert with_labels({"platform": ""}, (USED,))["excluded_agent_labels"] == [USED]
    assert with_labels({}, ())["excluded_agent_labels"] == []


def test_a_request_or_a_flavor_never_sets_another_list() -> None:
    assert input_problems({}, (USED,)) == []
    assert input_problems({"excluded_agent_labels": [USED]}, (USED,)) == []
    (problem,) = input_problems({"excluded_agent_labels": ["other"]}, (USED,))
    assert problem.startswith("excluded_agent_labels: set by this deployment")
    assert flavor_problems({"nodepools": []}) == []
    assert flavor_problems({"excluded_agent_labels": []}) == [problem]


def test_every_rendered_nodepool_holds_the_list_and_none_holds_one_unasked() -> None:
    asked = {"excluded_agent_labels": [USED]}
    good = {
        "nodepool": [pool("a", excludeAgentLabels=[USED]), pool("b", excludeAgentLabels=[USED])]
    }
    assert rendered_problems(asked, good) == []
    (stale,) = rendered_problems(
        asked, {"nodepool": [pool("a", excludeAgentLabels=[USED]), pool("b")]}
    )
    assert stale.startswith("nodepool[1].excludeAgentLabels: the template wrote None for")
    assert GUIDE in stale
    (unasked,) = rendered_problems(
        {"excluded_agent_labels": []}, {"nodepool": [pool("a", excludeAgentLabels=[])]}
    )
    assert unasked.startswith("nodepool[0].excludeAgentLabels")
    assert rendered_problems({}, {"nodepool": [pool("a")]}) == []


def test_an_edit_may_add_the_list_but_never_change_an_existing_replace_nodepools() -> None:
    before = {"nodepool": [pool("a"), pool("r", upgradeType="Replace")]}
    added = {"nodepool": [pool("a", excludeAgentLabels=[USED]), pool("r", upgradeType="Replace")]}
    assert edit_problems(before, added) == []
    replaced = {
        "nodepool": [pool("a"), pool("r", upgradeType="Replace", excludeAgentLabels=[USED])]
    }
    (problem,) = edit_problems(before, replaced)
    assert problem.startswith("nodepool[1].excludeAgentLabels: NodePool r is upgradeType Replace")
    new_replace = {
        "nodepool": [
            *before["nodepool"],
            pool("n", upgradeType="Replace", excludeAgentLabels=[USED]),
        ]
    }
    assert edit_problems(before, new_replace) == [], "nothing runs on a new NodePool yet"
    kept = {"nodepool": [pool("a", excludeAgentLabels=[USED], replicas=3)]}
    assert edit_problems({"nodepool": [pool("a", excludeAgentLabels=[USED])]}, kept) == []


def test_an_edits_list_must_be_label_keys() -> None:
    assert edit_problems({}, {"nodepool": [pool("a", excludeAgentLabels=USED)]}) == [
        "nodepool[0].excludeAgentLabels: must be a list of Agent label keys"
    ]
    (problem,) = edit_problems({}, {"nodepool": [pool("a", excludeAgentLabels=["Not A Key"])]})
    assert problem.startswith("nodepool[0].excludeAgentLabels: 'Not A Key'")


def test_the_plan_writes_the_keys_where_they_are_missing_and_says_why_not_elsewhere() -> None:
    values = {
        "nodepool": [
            pool("a"),
            pool("b", excludeAgentLabels=[USED]),
            pool("c", excludeAgentLabels=["old"]),
            {**pool("r", upgradeType="Replace"), "name": "prod-x-site1-replaced"},
        ]
    }
    pools = plan(values, (USED,), cluster_name="prod-x-site1")
    assert [(p.name, p.have, p.change) for p in pools] == [
        ("prod-x-site1-a", (), True),
        ("prod-x-site1-b", (USED,), False),
        ("prod-x-site1-c", ("old",), True),
        ("prod-x-site1-replaced", (), False),
    ]
    assert pools[3].reason == "upgradeType Replace: the change would replace every node"
    kubevirt = plan(
        {"platform": "kubevirt", "nodepool": [{"replicas": 1}]}, (USED,), cluster_name="x"
    )
    assert [(p.name, p.change, p.reason) for p in kubevirt] == [
        ("nodepool[0]", False, "KubeVirt: takes no Agents")
    ]


def test_the_merge_requests_text_names_the_nodepools_it_changes_and_each_it_leaves_out() -> None:
    values = {
        "nodepool": [
            pool("hp"),
            {**pool("dell", upgradeType="Replace"), "name": "prod-x-site1-dell-b"},
            pool("done", excludeAgentLabels=[USED]),
        ]
    }
    text = summary("ocp4-prod-x-site1", (USED,), plan(values, (USED,), cluster_name="prod-x-site1"))
    first, blank, *left = text.splitlines()
    assert first.startswith(
        f"Exclude Agents labelled {USED} from NodePools prod-x-site1-hp of **ocp4-prod-x-site1**"
    )
    assert (blank, left) == (
        "",
        [
            "Left out:",
            "- prod-x-site1-dell-b (upgradeType Replace: the change would replace every node)",
            "- prod-x-site1-done (excludes them already)",
        ],
    )
    only = summary("c", (USED,), plan({"nodepool": [pool("a")]}, (USED,), cluster_name="c"))
    assert "Left out" not in only
