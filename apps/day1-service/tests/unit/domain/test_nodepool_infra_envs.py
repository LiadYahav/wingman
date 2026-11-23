"""A nodepool that draws Agents from several InfraEnvs (ADR-0064): inputs, the template, edits."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_day1.domain.cluster_file import (
    NO_WORKFLOW_KEYS,
    WorkflowKeys,
    edit_problems,
    load_values,
    read_values,
)
from wingman_day1.domain.nodepool_infra_envs import (
    FILE_KEY,
    INPUT,
    MAX_ADDITIONAL,
    SETTING,
    infra_envs_of,
    input_problems,
    names_in,
    rendered_problems,
    selected,
    template_problems,
    without_input,
)
from wingman_day1.domain.template import FieldType, TemplateField

ON = WorkflowKeys(infra_envs=True)
DELL, DELL7, HP = "dell-r660", "dell-r760", "hp-gen11"
OFF_PROBLEM = (
    f"nodepools[0].{INPUT}: a nodepool draws from its own InfraEnv only in this deployment "
    f"({SETTING} is off)"
)


def pool(first: str = DELL, *more: str, **keys: object) -> dict[str, object]:
    return {"infra_env": first, "replicas": 2, **({INPUT: list(more)} if more else {}), **keys}


def file(*pools: str) -> str:
    """A cluster file whose nodepools are the given YAML entries."""
    body = "\n".join(pools)
    return f'owner: {{merkaz: "1", anaf: "2", mador: "3"}}\nmastertag: 4.18.22\nnodepool:\n{body}\n'


def entry(first: str, *more: str, **keys: object) -> str:
    lines = [f"- infraEnvName: {first}"]
    if more:
        lines.append(f"  {FILE_KEY}: [{', '.join(more)}]")
    lines += [f"  {key}: {value}" for key, value in keys.items()]
    lines.append("  replicas: 2")
    return "\n".join(lines)


# ── Reading ──────────────────────────────────────────────────────────────────


def test_a_file_without_the_key_reads_as_it_always_did() -> None:
    (read,) = read_values(load_values(file(entry(DELL)))).nodepools
    assert (read.additional_infra_env_names, read.infra_envs) == ((), (DELL,))


def test_the_extra_infraenvs_are_read_and_kept_in_order_after_the_first() -> None:
    (read,) = read_values(load_values(file(entry(DELL, HP, DELL7, HP)))).nodepools
    assert read.additional_infra_env_names == (HP, DELL7, HP)
    assert read.infra_envs == (DELL, HP, DELL7)


def test_a_value_that_is_not_a_list_reads_as_none() -> None:
    (read,) = read_values(load_values(file(entry(DELL, **{FILE_KEY: HP})))).nodepools
    assert read.additional_infra_env_names == ()


def test_the_chart_selects_them_sorted_and_once() -> None:
    assert selected({"infraEnvName": HP, FILE_KEY: [DELL7, DELL, HP]}) == (DELL, DELL7, HP)
    assert selected({"infraEnvName": HP}) == (HP,)
    assert infra_envs_of(None, [DELL]) == (DELL,)


@pytest.mark.parametrize(
    ("value", "names"),
    [
        (None, []),
        ("", []),
        ([], []),
        ([DELL], [DELL]),
        ((DELL,), [DELL]),
        (DELL, None),
        ([1], None),
    ],
)
def test_names_in(value: object, names: list[str] | None) -> None:
    assert names_in(value) == names


# ── Create and flavor save ───────────────────────────────────────────────────


def test_off_a_nodepool_may_not_set_any() -> None:
    assert input_problems({"nodepools": [pool(DELL, HP)]}, enabled=False) == [OFF_PROBLEM]
    assert input_problems({"nodepools": [pool(DELL), pool(HP, **{INPUT: []})]}, enabled=False) == []


def test_on_each_is_an_infraenv_name_given_once_and_not_the_pools_own() -> None:
    inputs = {"nodepools": [pool(DELL, HP, HP, DELL, "Not_A_Label")]}
    problems = input_problems(inputs, enabled=True)
    assert problems[0] == f"nodepools[0].{INPUT}[1]: {HP} is listed twice"
    assert problems[1] == f"nodepools[0].{INPUT}[2]: {DELL} is the nodepool's own InfraEnv already"
    assert all(
        p.startswith(f"nodepools[0].{INPUT}[3]: InfraEnv 'Not_A_Label'") for p in problems[2:]
    )


def test_on_a_value_that_is_not_a_list_kubevirt_and_too_many_are_refused() -> None:
    assert input_problems({"nodepools": [{INPUT: HP}]}, enabled=True) == [
        f"nodepools[0].{INPUT}: must be a list of InfraEnv names"
    ]
    kubevirt = {"platform": "kubevirt", "nodepools": [pool(DELL, HP)]}
    assert input_problems(kubevirt, enabled=True) == [
        f"nodepools[0].{INPUT}: a KubeVirt nodepool draws from no InfraEnv"
    ]
    many = [f"pool-{i}" for i in range(MAX_ADDITIONAL + 1)]
    assert input_problems({"nodepools": [pool(DELL, *many)]}, enabled=True) == [
        f"nodepools[0].{INPUT}: {MAX_ADDITIONAL + 1} InfraEnvs; the limit is {MAX_ADDITIONAL}"
    ]


def test_the_form_schema_leaves_the_input_out_when_off() -> None:
    nodepools = TemplateField(
        "nodepools",
        FieldType.LIST,
        required=True,
        fields=(
            TemplateField("infra_env", FieldType.STRING, required=True),
            TemplateField(INPUT, FieldType.LIST, required=False),
        ),
    )
    owner = TemplateField("owner", FieldType.STRING, required=True)
    (kept, pools) = without_input([owner, nodepools])
    assert kept is owner
    assert [f.name for f in pools.fields] == ["infra_env"]


# ── The template writes what was chosen ──────────────────────────────────────


def test_a_template_that_writes_what_was_chosen_passes() -> None:
    inputs = {"nodepools": [pool(DELL, HP), pool(DELL7)]}
    rendered = {"nodepool": [{"infraEnvName": DELL, FILE_KEY: [HP]}, {"infraEnvName": DELL7}]}
    assert rendered_problems(inputs, rendered) == []


def test_a_template_that_does_not_render_the_input_is_refused() -> None:
    inputs = {"nodepools": [pool(DELL, HP)]}
    (problem,) = rendered_problems(inputs, {"nodepool": [{"infraEnvName": DELL}]})
    assert problem.startswith(f"nodepool[0].{FILE_KEY}: the template wrote None for ['hp-gen11']")
    assert "cluster-template.j2 must render additional_infra_envs as given" in problem


def test_a_template_that_writes_the_key_unasked_is_refused() -> None:
    inputs = {"nodepools": [pool(DELL)]}
    assert rendered_problems(inputs, {"nodepool": [{"infraEnvName": DELL, FILE_KEY: []}]})
    assert rendered_problems(inputs, {"nodepool": [{"infraEnvName": DELL, FILE_KEY: [HP]}]})


def test_a_flavor_that_gives_them_needs_a_template_that_reads_them() -> None:
    values = {"nodepools": [pool(DELL), pool(DELL, HP)]}
    reads = "{% for np in nodepools %}{{ np.infra_env }}{{ np.additional_infra_envs }}{% endfor %}"
    assert template_problems(values, reads) == []
    (problem,) = template_problems(
        values, "{% for np in nodepools %}{{ np.infra_env }}{% endfor %}"
    )
    assert problem.startswith(
        f"nodepools[1].{INPUT}: the specs project's cluster-template.j2 does not read this input"
    )
    assert template_problems({"nodepools": [pool(DELL)]}, "{{ x }}") == [], "nothing given"
    assert template_problems(values, "") == [], "no template: left to the create"
    assert template_problems(values, "{% for %}") == [], "not Jinja: left to the create"


# ── Edits ────────────────────────────────────────────────────────────────────


def edit(old: str, new: str, owned: WorkflowKeys = ON) -> list[str]:
    return edit_problems(file(old), file(new), owned=owned)


def test_off_an_edit_keeps_the_key_as_it_is_and_may_change_the_rest() -> None:
    assert (
        edit(
            entry(DELL, HP), entry(DELL, HP).replace("replicas: 2", "replicas: 3"), NO_WORKFLOW_KEYS
        )
        == []
    )
    (problem,) = edit(entry(DELL), entry(DELL, HP), NO_WORKFLOW_KEYS)
    assert problem == (
        f"nodepool[0]: {FILE_KEY} is not written in this deployment ({SETTING} is off); "
        "an edit must leave it as it is"
    )
    assert edit(entry(DELL, HP), entry(DELL), NO_WORKFLOW_KEYS)
    assert edit(entry(DELL), f"{entry(DELL)}\n{entry(HP, DELL7)}", NO_WORKFLOW_KEYS)


def test_on_an_edit_adds_and_removes_infraenvs_of_an_in_place_nodepool() -> None:
    assert edit(entry(DELL), entry(DELL, HP, DELL7)) == []
    assert edit(entry(DELL, HP, DELL7), entry(DELL, DELL7)) == []
    assert edit(entry(DELL, HP), entry(DELL)) == []
    assert edit(entry(DELL), f"{entry(DELL)}\n{entry(HP, DELL7)}") == [], "a new nodepool"


def test_on_the_new_names_are_checked_as_the_chart_checks_them() -> None:
    (problem,) = edit(entry(DELL), entry(DELL, HP, HP))
    assert problem == f"nodepool[0].{FILE_KEY}[1]: {HP} is listed twice"
    selector = "{nodeLabelKey: infraenvs.agent-install.openshift.io, nodeLabelValue: dell-r660}"
    (combined,) = edit(entry(DELL), entry(DELL, HP, agentLabelSelector=selector))
    assert (
        combined
        == f"nodepool[0]: {FILE_KEY} cannot be combined with agentLabelSelector; set infraEnvName"
    )


def test_making_another_infraenv_first_would_replace_the_nodepool_and_is_refused() -> None:
    (problem,) = edit(entry(DELL, HP, DELL7), entry(HP, DELL7))
    assert problem.startswith(
        f"nodepool[0]: its first InfraEnv is {HP}, but the NodePool it replaces is named after "
        f"{DELL}"
    )
    assert f"Keep {DELL} as infraEnvName" in problem
    assert edit(entry(DELL, HP), entry(HP, DELL)), "a swap is a new name too"
    assert edit(entry(DELL), entry(HP, DELL)), "a single InfraEnv put second"


def test_an_explicit_name_keeps_the_nodepool_whatever_comes_first() -> None:
    named = entry(DELL, HP, name="lark-workers")
    assert edit(named, entry(HP, DELL, name="lark-workers")) == []


def test_replacing_a_single_infraenv_nodepool_by_another_is_still_a_person_s_choice() -> None:
    assert edit(entry(DELL), entry(HP)) == [], "no other InfraEnv: today's edit, a new NodePool"
    assert edit(f"{entry(DELL)}\n{entry(HP)}", entry(HP, DELL)) == [], "the old HP pool kept"


def test_a_replace_nodepool_keeps_the_infraenvs_it_draws_from() -> None:
    replace_ = {"upgradeType": "Replace"}
    (problem,) = edit(entry(DELL, **replace_), entry(DELL, HP, **replace_))
    assert problem == (
        f"nodepool[0]: NodePool {DELL} is upgradeType Replace, so a change to the InfraEnvs it "
        "draws from would replace every node; leave them as they are"
    )
    assert edit(entry(DELL, HP, **replace_), entry(DELL, **replace_))
    assert edit(entry(DELL, HP), entry(DELL, HP, DELL7, **replace_)), "asked to become Replace"
    kept = entry(DELL, HP, **replace_)
    assert edit(kept, kept.replace("replicas: 2", "replicas: 4")) == []


def test_a_sync_or_any_edit_that_leaves_the_infraenvs_is_untouched_by_the_rule() -> None:
    old = f"{entry(DELL, HP)}\n{entry(DELL7, upgradeType='Replace')}"
    assert edit(old, old.replace("replicas: 2", "replicas: 5")) == []
    assert edit(old, old, NO_WORKFLOW_KEYS) == []


@pytest.mark.parametrize("enabled", [True, False])
def test_rules_hold_with_the_setting_off_too(enabled: bool) -> None:
    owned: Any = ON if enabled else NO_WORKFLOW_KEYS
    assert edit(entry(DELL, HP), entry(HP), owned), "a rename is refused either way"
