"""The cluster template: input analysis, sandboxed rendering, input checks and assembly."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.errors import RenderError
from wingman_day1.domain.template import (
    LEGACY_IDENTITY_ALIASES,
    MAX_DEPTH,
    MAX_LEAVES,
    MAX_VALUE_LENGTH,
    RESERVED_INPUTS,
    FieldType,
    TemplateField,
    analyze_template,
    build_inputs,
    check_inputs,
    render_cluster_file,
)

FIXTURE_TEMPLATE = default_fixture_root() / "wingman" / "cluster-specs" / "cluster-template.j2"


def fixture_template() -> str:
    return Path(FIXTURE_TEMPLATE).read_text(encoding="utf-8")


def schema(text: str, *, include_reserved: bool = False) -> list[dict[str, object]]:
    return [f.to_dict() for f in analyze_template(text, include_reserved=include_reserved)]


def base_inputs(**overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "owner_merkaz": "1234",
        "owner_anaf": "56",
        "owner_mador": "7",
        "openshift_release_version": "4.18.22-x86_64",
        "cluster_name": "ocp4-prod-hawk-site1",
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "nodepools": [{"infra_env": "dell-r660-site1-128c-1024gb-5tb"}],
    }
    inputs.update(overrides)
    return inputs


# ── Analysis: the legacy analyzer's behaviours ──────────────────────────────


def test_a_plain_input_is_a_required_string() -> None:
    assert schema("name: {{ cluster_label }}") == [
        {"name": "cluster_label", "type": "string", "required": True}
    ]


def test_a_default_makes_an_input_optional_and_the_first_literal_default_wins() -> None:
    text = (
        "{{ replicas | default(3) | default(4) }} {{ replicas | default(5) }} "
        "{{ flag | default(false) }}"
    )
    assert schema(text) == [
        {"name": "replicas", "type": "string", "required": False, "default": 3},
        {"name": "flag", "type": "string", "required": False, "default": False},
    ]


def test_empty_list_and_object_defaults_set_the_type() -> None:
    assert schema("{{ a | default([]) }}{{ b | default({}) }}") == [
        {"name": "a", "type": "list", "required": False, "default": []},
        {"name": "b", "type": "object", "required": False, "default": {}},
    ]


def test_a_non_literal_default_is_optional_without_a_default() -> None:
    # Deliberate change: the legacy analyzer reported the string "__default__".
    assert schema("{{ a | default(b) }}") == [
        {"name": "a", "type": "string", "required": False},
        {"name": "b", "type": "string", "required": True},
    ]


def test_a_literal_list_default_is_reported_as_a_list() -> None:
    # Deliberate change: the legacy analyzer leaked Jinja AST nodes here.
    assert schema("{{ zones | default(['a', 'b']) }}") == [
        {"name": "zones", "type": "list", "required": False, "default": ["a", "b"]}
    ]


def test_a_none_default_is_optional_with_no_default() -> None:
    assert schema("{{ a | default(none) }}") == [{"name": "a", "type": "string", "required": False}]


def test_a_for_loop_makes_a_list_of_objects_with_the_fields_it_reads() -> None:
    text = (
        "{% for np in pools %}{{ np.infra }} {{ np.size | default('small') }}"
        "{% for label in np.labels | default([]) %}{{ label.key }}{% endfor %}{% endfor %}"
    )
    assert schema(text) == [
        {
            "name": "pools",
            "type": "list",
            "required": True,
            "fields": [
                {"name": "infra", "type": "string", "required": True},
                {"name": "size", "type": "string", "required": False, "default": "small"},
                {
                    "name": "labels",
                    "type": "list",
                    "required": False,
                    "default": [],
                    "fields": [{"name": "key", "type": "string", "required": True}],
                },
            ],
        }
    ]


def test_an_optional_list_loop_and_filters_on_loop_fields() -> None:
    text = (
        "{% for np in pools | default([]) %}{{ np.labels | default({}) | tojson }}"
        "{% if np.name | default('') %}{{ np.name }}{% endif %}{% endfor %}"
    )
    (pools,) = analyze_template(text)
    assert (pools.required, pools.type, pools.default) == (False, FieldType.LIST, [])
    assert [f.to_dict() for f in pools.fields] == [
        {"name": "labels", "type": "object", "required": False, "default": {}},
        {"name": "name", "type": "string", "required": False, "default": ""},
    ]


def test_assignments_builtins_and_private_names_are_not_inputs() -> None:
    text = (
        "{% set total = count | default(1) %}{{ total }}{{ loop }}{{ _hidden }}"
        "{% for i in range(3) %}{{ i }}{% endfor %}"
    )
    assert [f["name"] for f in schema(text)] == ["count"]


def test_iterating_an_assigned_or_loop_variable_walks_the_body() -> None:
    text = (
        "{% set xs = [1] %}{% for x in xs %}{{ x }}{{ other }}{% endfor %}"
        "{% for k, v in mapping.items() %}{{ k }}{{ v }}{{ third }}{% endfor %}"
        "{% for y in obj.attr %}{{ y.z }}{% endfor %}"
    )
    assert [f["name"] for f in schema(text)] == ["other", "mapping", "third", "obj"]


def test_expressions_of_every_kind_are_walked() -> None:
    text = (
        "{{ a + b }}{{ c ~ d }}{{ [e, f] }}{{ g(h) }}{{ i[0] }}{{ j == k }}"
        "{{ l if m else n }}{{ o.attr }}{{ p | join(q) }}{{ (r | default('x')).s }}"
        "{% if t %}{% elif u %}{{ v }}{% else %}{{ w }}{% endif %}"
        "{% call x(y) %}{{ z }}{% endcall %}{% block blk %}{{ aa }}{% endblock %}"
    )
    expected = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "m", "l", "n", "o", "p"]
    expected += ["q", "r", "t", "u", "v", "w", "x", "y", "z", "aa"]
    assert [f["name"] for f in schema(text)] == expected


def test_examples_come_from_yaml_and_jinja_comments_and_reach_nested_fields() -> None:
    text = (
        "# Example: 4.16.27\nversion: {{ ocp }}\n"
        "{# Example: dell-r660 #}\n{% for np in pools %}\n  - {{ np.infra }}\n{% endfor %}\n"
        "# Example: never used\nplain: text\n"
        "# Example: not an input\nconst: {{ 1 }}\n"
        "# Example: nothing follows\n"
    )
    fields = schema(text)
    assert fields[0]["example"] == "4.16.27"
    assert fields[1]["fields"] == [
        {"name": "infra", "type": "string", "required": True, "example": "dell-r660"}
    ]
    assert len(fields) == 2


def test_filters_without_a_literal_default_and_on_loop_variables() -> None:
    text = (
        "{{ bare | default }}{{ (a + b) | string }}{{ obj.attr | default('') }}{{ loop | length }}"
        "{% for np in pools %}{{ np.x | upper }}{{ (np | default({})).y }}{{ np | tojson }}"
        "{% endfor %}{{ c if d }}"
        "{% set e, f = 1, 2 %}{{ e }}{{ f }}{% macro m() %}{{ unseen }}{% endmacro %}"
        "{% filter indent(width) %}{{ inside }}{% endfilter %}"
    )
    fields = {f.name: f for f in analyze_template(text)}
    assert list(fields) == ["bare", "a", "b", "obj", "pools", "d", "c", "width", "inside"]
    assert (fields["bare"].required, fields["bare"].has_default) == (False, False)
    assert fields["obj"].required is True
    assert [(f.name, f.required) for f in fields["pools"].fields] == [("x", True), ("y", False)]


def test_reserved_inputs_and_legacy_aliases_are_left_out_unless_asked_for() -> None:
    text = "{{ cluster_name }}{{ site }}{{ site_name }}{{ mce }}{{ mce_name }}"
    text += "{{ openshift_release_version }}{{ owner }}"
    assert [f["name"] for f in schema(text)] == ["owner"]
    with_reserved = {f["name"] for f in schema(text, include_reserved=True)}
    assert with_reserved == RESERVED_INPUTS | LEGACY_IDENTITY_ALIASES | {"owner"}


def test_a_template_with_a_syntax_error_is_a_render_error_with_its_line() -> None:
    with pytest.raises(RenderError) as caught:
        analyze_template("a: 1\nb: {{ oops\n")
    assert caught.value.problems[0].startswith("line 2:")


def test_template_field_defaults_serialise_like_the_legacy_api() -> None:
    field = TemplateField("x", FieldType.INTEGER, required=True)
    assert field.to_dict() == {"name": "x", "type": "integer", "required": True}


# ── Analysis: the real fixture template ─────────────────────────────────────


def test_the_fixture_template_asks_for_exactly_the_values_file_inputs() -> None:
    assert schema(fixture_template()) == [
        {"name": "owner_merkaz", "type": "string", "required": True, "example": "1234"},
        {"name": "owner_anaf", "type": "string", "required": True, "example": "56"},
        {"name": "owner_mador", "type": "string", "required": True, "example": "7"},
        {"name": "platform", "type": "string", "required": False, "default": ""},
        {
            "name": "nodepools",
            "type": "list",
            "required": True,
            "fields": [
                {
                    "name": "infra_env",
                    "type": "string",
                    "required": True,
                    "example": "dell-r660-site1-128c-1024gb-5tb",
                },
                {"name": "nodepool_name", "type": "string", "required": False, "default": ""},
                {"name": "replicas", "type": "string", "required": False, "default": 2},
                {
                    "name": "configs",
                    "type": "list",
                    "required": False,
                    "default": [],
                    "fields": [
                        {
                            "name": "name",
                            "type": "string",
                            "required": True,
                            "example": "worker-kubeletconfig-reserved",
                        }
                    ],
                },
                {"name": "node_labels", "type": "object", "required": False, "default": {}},
                {"name": "tuning_config", "type": "string", "required": False, "default": ""},
            ],
        },
    ]
    reserved = [f.name for f in analyze_template(fixture_template(), include_reserved=True)]
    assert reserved == [
        "owner_merkaz",
        "owner_anaf",
        "owner_mador",
        "openshift_release_version",
        "platform",
        "nodepools",
    ]


# ── Rendering ───────────────────────────────────────────────────────────────


def test_the_fixture_template_renders_the_values_file_contract() -> None:
    inputs = base_inputs(
        nodepools=[
            {
                "infra_env": "dell-r660-site1-128c-1024gb-5tb",
                "replicas": 3,
                "configs": [{"name": "worker-kubeletconfig-reserved"}, {"name": "nic-ring-buffer"}],
                "node_labels": {"topology.kubernetes.io/zone": "a"},
            },
            {
                "infra_env": "dell-r660-site1-128c-1024gb-5tb",
                "nodepool_name": "prod-hawk-site1-zone-b",
                "replicas": "0",
                "tuning_config": "tuned-workers",
            },
        ]
    )
    rendered = render_cluster_file(fixture_template(), inputs)
    assert yaml.safe_load(rendered) == {
        "owner": {"merkaz": "1234", "anaf": "56", "mador": "7"},
        "mastertag": "4.18.22-x86_64",
        "nodepool": [
            {
                "infraEnvName": "dell-r660-site1-128c-1024gb-5tb",
                "replicas": 3,
                "labels": {"allowDeletion": False},
                "configs": [{"name": "worker-kubeletconfig-reserved"}, {"name": "nic-ring-buffer"}],
                "nodeLabels": {"topology.kubernetes.io/zone": "a"},
            },
            {
                "infraEnvName": "dell-r660-site1-128c-1024gb-5tb",
                "name": "prod-hawk-site1-zone-b",
                "replicas": 0,
                "labels": {"allowDeletion": False},
                "tuningConfig": "tuned-workers",
            },
        ],
    }
    assert rendered.endswith("\n")


def test_the_kubevirt_variant_adds_only_the_platform_key() -> None:
    rendered = yaml.safe_load(
        render_cluster_file(fixture_template(), base_inputs(platform="kubevirt"))
    )
    assert rendered["platform"] == "kubevirt"
    assert rendered["nodepool"] == [
        {
            "infraEnvName": "dell-r660-site1-128c-1024gb-5tb",
            "replicas": 2,
            "labels": {"allowDeletion": False},
        }
    ]
    plain = yaml.safe_load(render_cluster_file(fixture_template(), base_inputs()))
    assert "platform" not in plain


def test_a_missing_input_is_an_error_not_an_empty_string() -> None:
    inputs = base_inputs()
    del inputs["owner_anaf"]
    with pytest.raises(RenderError, match="undefined") as caught:
        render_cluster_file(fixture_template(), inputs)
    assert "owner_anaf" in caught.value.problems[0]


def test_a_missing_loop_field_is_an_error() -> None:
    with pytest.raises(RenderError, match="undefined"):
        render_cluster_file(fixture_template(), base_inputs(nodepools=[{"replicas": 1}]))


@pytest.mark.parametrize(
    "template",
    [
        "{{ ''.__class__.__mro__ }}",
        "{{ ''.__class__ }}",
        "{{ cycler.__init__.__globals__ }}",
    ],
)
def test_the_sandbox_refuses_to_reach_python_internals(template: str) -> None:
    with pytest.raises(RenderError) as caught:
        render_cluster_file(template, {})
    assert caught.value.problems


def test_an_unsafe_attribute_is_a_sandbox_violation() -> None:
    with pytest.raises(RenderError, match="sandbox"):
        render_cluster_file("{{ ''.__class__ }}", {})


def test_a_syntax_error_reports_its_line() -> None:
    with pytest.raises(RenderError, match="not valid Jinja") as caught:
        render_cluster_file("ok: 1\n{% for x in %}\n", {})
    assert caught.value.problems[0].startswith("line 2:")


@pytest.mark.parametrize(
    ("template", "inputs"),
    [
        ("{{ 1 // zero }}", {"zero": 0}),
        ("{{ x | round(method='sideways') }}", {"x": 1.5}),
        ('{{ "{:d}".format(x) }}', {"x": "a"}),
        ("{{ x + 1 }}", {"x": "a"}),
        ("{{ x | join(1) }}", {"x": 5}),
        ("{% extends 'other.j2' %}", {}),
    ],
)
def test_a_failing_expression_is_a_render_error(template: str, inputs: dict[str, object]) -> None:
    with pytest.raises(RenderError, match="failed to render"):
        render_cluster_file(template, inputs)


def test_an_empty_render_is_an_error() -> None:
    with pytest.raises(RenderError, match="rendered nothing"):
        render_cluster_file("{% if false %}x{% endif %}\n  \n", {})


def test_numeric_strings_are_not_coerced() -> None:
    assert render_cluster_file('merkaz: "{{ v }}"', {"v": "0123"}) == 'merkaz: "0123"'


# ── Input checks ────────────────────────────────────────────────────────────


def test_ordinary_inputs_are_safe() -> None:
    assert check_inputs(base_inputs(platform="kubevirt", flag=True, ratio=1.5, nothing=None)) == []


@pytest.mark.parametrize(
    "value",
    [
        "x\nvlanId: 5",
        "x\rvlanId: 5",
        "tab\there",
        "nel\x85here",
        "line\u2028sep",
        "zero\u200bwidth",
        'a" injected: "b',
        "back\\slash",
    ],
)
def test_values_that_could_change_the_yaml_structure_are_refused(value: str) -> None:
    problems = check_inputs(base_inputs(owner_mador=value))
    assert len(problems) == 1
    assert problems[0].startswith("owner_mador: a value must be one line")


def test_nested_values_are_checked_with_their_path() -> None:
    problems = check_inputs(
        base_inputs(nodepools=[{"infra_env": "a\nb", "configs": [{"name": "c\n"}]}])
    )
    assert [p.split(":")[0] for p in problems] == [
        "nodepools[0][infra_env]",
        "nodepools[0][configs][0][name]",
    ]


def test_a_long_value_is_refused() -> None:
    (problem,) = check_inputs({"owner_mador": "x" * (MAX_VALUE_LENGTH + 1)})
    assert "longer than 253" in problem
    assert check_inputs({"owner_mador": "x" * MAX_VALUE_LENGTH}) == []


def test_input_names_must_be_identifiers_and_nested_keys_safe() -> None:
    assert check_inputs({"not-an-identifier": "x"}) == [
        "input name 'not-an-identifier' is not an identifier"
    ]
    assert check_inputs({"labels": {"topology.kubernetes.io/zone": "a"}}) == []
    (problem,) = check_inputs({"labels": {"bad key": "a"}})
    assert problem.startswith("labels: key 'bad key'")
    (problem,) = check_inputs({"labels": {1: "a"}})
    assert problem.startswith("labels: key 1")
    (problem,) = check_inputs({"labels": {"k" * (MAX_VALUE_LENGTH + 1): "a"}})
    assert "a key is longer" in problem


def test_non_json_values_are_refused() -> None:
    (problem,) = check_inputs({"when": object()})
    assert problem == "when: a object is not a JSON value"


def test_nesting_is_bounded() -> None:
    value: object = "leaf"
    for _ in range(MAX_DEPTH):
        value = [value]
    assert check_inputs({"deep": value}) == []
    (problem,) = check_inputs({"deep": [value]})
    assert "nested deeper than 6 levels" in problem
    (problem,) = check_inputs({"deep": {"k": value}})
    assert "nested deeper than 6 levels" in problem
    mapping_at_the_bottom: object = {"k": 1}
    for _ in range(MAX_DEPTH):
        mapping_at_the_bottom = [mapping_at_the_bottom]
    (problem,) = check_inputs({"deep": mapping_at_the_bottom})
    assert problem == "deep[0][0][0][0][0][0]: nested deeper than 6 levels"


def test_the_number_of_values_is_bounded() -> None:
    assert check_inputs({"many": list(range(MAX_LEAVES))}) == []
    (problem,) = check_inputs({"many": list(range(MAX_LEAVES + 1))})
    assert problem == f"{MAX_LEAVES + 1} values given; the limit is {MAX_LEAVES}"


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=MAX_VALUE_LENGTH,
    )
)
# Arbitrary text is the point, and check_inputs refuses much of it: the filtering is
# the test, so its health check (which failed about one run in three) is not.
@settings(suppress_health_check=[HealthCheck.filter_too_much])
def test_an_accepted_value_never_changes_the_documents_top_level_keys(value: str) -> None:
    inputs = base_inputs(owner_mador=value)
    assume(check_inputs(inputs) == [])
    parsed = yaml.safe_load(render_cluster_file(fixture_template(), inputs))
    assert set(parsed) == {"owner", "mastertag", "nodepool"}
    assert parsed["owner"]["mador"] == value


# ── Assembling the inputs ───────────────────────────────────────────────────


def identity(**variables: object) -> dict[str, object]:
    return build_inputs(
        variables=variables,
        cluster_name="ocp4-prod-hawk-site1",
        site="site1",
        mce="ocp4-prod-mce-site1-a",
        openshift_release_version="4.18.22-x86_64",
    )


def test_reserved_inputs_come_from_the_request_and_aliases_are_dropped() -> None:
    assert identity(
        owner_merkaz="1",
        cluster_name="ocp4-prod-hawk-site1",
        site_name="site1",
        mce_name="ocp4-prod-mce-site1-a",
    ) == {
        "owner_merkaz": "1",
        "cluster_name": "ocp4-prod-hawk-site1",
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "openshift_release_version": "4.18.22-x86_64",
    }


def test_a_reserved_input_that_disagrees_with_the_request_is_refused() -> None:
    with pytest.raises(RenderError, match="disagree") as caught:
        identity(
            cluster_name="ocp4-prod-other-site1",
            site_name="site2",
            mce="m",
            openshift_release_version="4.1.1",
        )
    assert caught.value.problems == (
        "cluster_name is 'ocp4-prod-other-site1' but the request says 'ocp4-prod-hawk-site1'",
        "site_name is 'site2' but the request says 'site1'",
        "mce is 'm' but the request says 'ocp4-prod-mce-site1-a'",
        "openshift_release_version is '4.1.1' but the request says '4.18.22-x86_64'",
    )


def test_presets_merge_under_the_users_values() -> None:
    merged = build_inputs(
        variables={
            "owner": {"anaf": "2"},
            "nodepools": [{"infra_env": "b"}],
            "platform": "kubevirt",
        },
        presets={
            "owner": {"merkaz": "1", "anaf": "9"},
            "nodepools": [{"infra_env": "a", "replicas": 3}],
            "platform": "",
            "cluster_name": "from-a-preset",
        },
        cluster_name="ocp4-prod-hawk-site1",
        site="site1",
        mce="ocp4-prod-mce-site1-a",
        openshift_release_version="4.18.22-x86_64",
    )
    assert merged["owner"] == {"merkaz": "1", "anaf": "2"}
    assert merged["nodepools"] == [{"infra_env": "b"}]
    assert merged["platform"] == "kubevirt"
    assert merged["cluster_name"] == "ocp4-prod-hawk-site1"


@pytest.mark.parametrize(
    ("argument", "variables", "presets", "expected"),
    [
        ("4.18.22-x86_64", {}, {"openshift_release_version": "4.16.27"}, "4.18.22-x86_64"),
        (None, {"openshift_release_version": "4.21.40-x86_64"}, {}, "4.21.40-x86_64"),
        (None, {}, {"openshift_release_version": "4.16.27-x86_64"}, "4.16.27-x86_64"),
    ],
)
def test_the_release_version_comes_from_the_argument_then_the_values(
    argument: str | None,
    variables: dict[str, object],
    presets: dict[str, object],
    expected: str,
) -> None:
    merged = build_inputs(
        variables=variables,
        presets=presets,
        cluster_name="c",
        site="s",
        mce="m",
        openshift_release_version=argument,
    )
    assert merged["openshift_release_version"] == expected


@pytest.mark.parametrize(
    "variables", [{}, {"openshift_release_version": "  "}, {"openshift_release_version": 4}]
)
def test_a_missing_release_version_is_refused(variables: dict[str, object]) -> None:
    with pytest.raises(RenderError, match="no OpenShift release version"):
        build_inputs(
            variables=variables, cluster_name="c", site="s", mce="m", openshift_release_version=None
        )
