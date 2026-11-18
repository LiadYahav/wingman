"""A flavor's image mirrors (ADR-0063): the inputs, the template, the chart's view, drift, edits."""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.cluster_text import SetValue, edit_values
from wingman_day1.domain.image_mirrors import (
    DROP_MCE_MIRRORS,
    IMAGE_MIRRORS,
    MIRRORS_FILE_KEY,
    drops_mce_mirrors,
    given_mirror_inputs,
    merged,
    mirror_lock_problem,
    mirror_problems,
    mirror_template_problems,
    mirrors_held,
    show_mirrors,
    unrendered_mirrors,
)
from wingman_day1.domain.input_paths import MISSING, InputPath
from wingman_day1.domain.locks import Lock, enforced_locks, lock_problems
from wingman_day1.domain.machine_configs import MachineConfigCatalog
from wingman_day1.domain.specs import ClusterSpec, rule_problems, validate_spec, with_template
from wingman_day1.domain.template import render_cluster_file
from wingman_day1.domain.value_drift import show_value, value_drift

TEMPLATE = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
OLD_TEMPLATE = re.sub(
    r"\{% if image_content_sources.*?\{% endif %\}\n\{% if disable_idms_merge.*?\{% endif %\}\n",
    "",
    TEMPLATE,
    flags=re.DOTALL,
)
"""The fixture template as a specs project has it before ADR-0063: no mirror lines."""

RELEASE = "registry.example.com/ocp4/openshift-release-dev"
OPERATORS = "registry.example.com/operators"
MIRRORS = [
    {"source": RELEASE, "mirrors": ["mirror.example.com/ocp4/openshift-release-dev"]},
    {"source": OPERATORS, "mirrors": ["mirror.example.com/operators", "backup.example.com/ops"]},
]
CATALOG = MachineConfigCatalog.from_files([RepoPath("mc-files/worker-chrony.yaml")])


def inputs(**extra: Any) -> dict[str, Any]:
    return {
        "cluster_name": "ocp4-prod-falcon-site1",
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "openshift_release_version": "4.18.56-x86_64",
        "owner_merkaz": "1234",
        "owner_anaf": "56",
        "owner_mador": "7",
        "nodepools": [{"infra_env": "dell-r660-site1-128c-1024gb-5tb"}],
        **extra,
    }


def spec(values: dict[str, Any], *, template: str = TEMPLATE) -> ClusterSpec:
    document = {
        "metadata": {"name": "agent-mirrors"},
        "spec": {"day1": {"values": values}},
    }
    return with_template(validate_spec(document), template)


# ── The inputs ───────────────────────────────────────────────────────────────


def test_absent_inputs_and_usable_ones_have_no_problems() -> None:
    assert mirror_problems({}) == []
    assert mirror_problems({IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True}) == []
    assert mirror_problems({IMAGE_MIRRORS: [], DROP_MCE_MIRRORS: False}) == []
    assert (
        mirror_problems({IMAGE_MIRRORS: [{"source": "*.example.com", "mirrors": ["m.io"]}]}) == []
    )


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ("registry.example.com", "image_content_sources: give a list of entries"),
        (["registry.example.com"], "image_content_sources[0]: an entry is a source and its"),
        (
            [{"source": "a.io", "mirrors": ["m.io"], "path": "x"}],
            "image_content_sources[0]: path is not a key of an entry",
        ),
        ([{"mirrors": ["m.io"]}], "image_content_sources[0].source: give the registry"),
        ([{"source": "", "mirrors": ["m.io"]}], "image_content_sources[0].source: give the"),
        (
            [{"source": "a .io", "mirrors": ["m.io"]}],
            "image_content_sources[0].source: 'a .io' has a space",
        ),
        ([{"source": "https://a.io", "mirrors": ["m.io"]}], "source: 'https://a.io' is a URL"),
        ([{"source": "-a.io", "mirrors": ["m.io"]}], "source: '-a.io' starts with '-'"),
        ([{"source": "a.io"}], "image_content_sources[0].mirrors: give at least one mirror"),
        ([{"source": "a.io", "mirrors": []}], "image_content_sources[0].mirrors: give at least"),
        (
            [{"source": "a.io", "mirrors": "m.io"}],
            "image_content_sources[0].mirrors: give at least",
        ),
        (
            [{"source": "a.io", "mirrors": ["m.io", 3]}],
            "image_content_sources[0].mirrors[1]: give a",
        ),
        ([{"source": "a.io", "mirrors": ["m.io", "m.io"]}], "mirrors[1]: m.io is listed twice"),
    ],
)
def test_an_entry_that_is_not_a_source_and_its_mirrors_is_refused(value: Any, problem: str) -> None:
    (found,) = mirror_problems({IMAGE_MIRRORS: value})
    assert problem in found


def test_a_source_is_listed_once() -> None:
    twice = [{"source": "a.io", "mirrors": ["m.io"]}, {"source": "a.io", "mirrors": ["n.io"]}]
    assert mirror_problems({IMAGE_MIRRORS: twice}) == [
        "image_content_sources[1].source: a.io is listed twice (also image_content_sources[0]); "
        "give all its mirrors in one entry"
    ]


@pytest.mark.parametrize("entries", [MISSING, [], None])
def test_dropping_the_mce_mirrors_needs_mirrors_of_the_clusters_own(entries: object) -> None:
    values: dict[str, object] = {DROP_MCE_MIRRORS: True}
    if entries is not MISSING:
        values[IMAGE_MIRRORS] = entries
    problems = mirror_problems(values)
    assert problems[-1] == (
        "disable_idms_merge: true drops the MCE's default mirrors, and image_content_sources "
        "gives none, so the cluster would have no image mirrors at all; give the cluster's own "
        "mirrors, or keep the MCE's"
    )
    assert mirror_problems({DROP_MCE_MIRRORS: False}) == []


def test_dropping_the_mce_mirrors_is_true_or_false() -> None:
    assert mirror_problems({IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: "true"}) == [
        "disable_idms_merge: give true or false (true keeps only the cluster's own mirrors); "
        "it is 'true'"
    ]


def test_only_inputs_that_change_the_file_are_given() -> None:
    assert given_mirror_inputs({IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True}) == [
        IMAGE_MIRRORS,
        DROP_MCE_MIRRORS,
    ]
    assert given_mirror_inputs({IMAGE_MIRRORS: [], DROP_MCE_MIRRORS: False}) == []


# ── The template ─────────────────────────────────────────────────────────────


def test_the_fixture_template_reads_both_inputs() -> None:
    assert (
        mirror_template_problems({IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True}, TEMPLATE) == []
    )


def test_a_template_that_does_not_read_them_refuses_the_mirrors_a_flavor_gives() -> None:
    assert "{% if image_content_sources" not in OLD_TEMPLATE
    values = {IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True}
    assert mirror_template_problems(values, OLD_TEMPLATE) == [
        f"{name}: the specs project's cluster-template.j2 does not read this input, so a "
        "cluster created from this flavor would not get it; add the template lines in "
        "docs/upgrade/3.44-to-3.45.md (ADR-0063)"
        for name in (IMAGE_MIRRORS, DROP_MCE_MIRRORS)
    ]
    # Nothing given, nothing to read; an empty or broken template is the create's to refuse
    assert (
        mirror_template_problems({IMAGE_MIRRORS: [], DROP_MCE_MIRRORS: False}, OLD_TEMPLATE) == []
    )
    assert mirror_template_problems(values, "") == []
    assert mirror_template_problems(values, "{{ oops") == []


def test_a_stored_flavor_with_mirrors_warns_against_the_template_it_is_read_with() -> None:
    values = {IMAGE_MIRRORS: MIRRORS}
    assert rule_problems(spec(values)) == []
    (warning,) = rule_problems(spec(values, template=OLD_TEMPLATE))
    assert warning.startswith("image_content_sources: the specs project's cluster-template.j2")


def test_the_fixture_template_writes_the_mirrors_as_given() -> None:
    wildcard = [*MIRRORS, {"source": "*.example.com", "mirrors": ["mirror.example.com/any"]}]
    given = inputs(**{IMAGE_MIRRORS: wildcard, DROP_MCE_MIRRORS: True})
    rendered = load_values(render_cluster_file(TEMPLATE, given))
    assert rendered["imageContentSources"] == wildcard
    assert rendered["disableIdmsMerge"] is True
    assert unrendered_mirrors(given, rendered) == []
    assert list(rendered) == [
        "owner",
        "mastertag",
        "imageContentSources",
        "disableIdmsMerge",
        "nodepool",
    ]


@pytest.mark.parametrize("extra", [{}, {IMAGE_MIRRORS: [], DROP_MCE_MIRRORS: False}])
def test_without_mirrors_the_fixture_template_writes_what_it_wrote_before(
    extra: dict[str, Any],
) -> None:
    rendered = render_cluster_file(TEMPLATE, inputs(**extra))
    assert rendered == render_cluster_file(OLD_TEMPLATE, inputs())
    assert unrendered_mirrors(inputs(**extra), load_values(rendered)) == []


def test_a_render_that_drops_the_mirrors_is_refused() -> None:
    given = inputs(**{IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True})
    rendered = load_values(render_cluster_file(OLD_TEMPLATE, given))
    hint = (
        "the specs project's cluster-template.j2 must render it as given (the lines are in "
        "docs/upgrade/3.44-to-3.45.md, ADR-0063)"
    )
    assert unrendered_mirrors(given, rendered) == [
        "imageContentSources: the template wrote (absent) for image_content_sources "
        f"{show_mirrors(MIRRORS)}; {hint}",
        f"disableIdmsMerge: the template wrote (absent) for disable_idms_merge true; {hint}",
    ]


# ── The chart's view ─────────────────────────────────────────────────────────


def test_a_list_is_its_entries_merged_by_source_and_sorted() -> None:
    split = [
        {"source": OPERATORS, "mirrors": ["mirror.example.com/operators"]},
        {"source": RELEASE, "mirrors": ["mirror.example.com/ocp4/openshift-release-dev"]},
        {
            "source": OPERATORS,
            "mirrors": ["backup.example.com/ops", "mirror.example.com/operators"],
        },
    ]
    assert merged(split) == merged(MIRRORS)
    assert merged(MISSING) == merged(None) == merged([]) == ()
    assert merged("x") is None
    assert merged([{"source": 1, "mirrors": []}]) is None
    assert merged([{"source": "a.io", "mirrors": [1]}]) is None


@pytest.mark.parametrize(
    ("value", "drops"),
    [
        (MISSING, False),
        (None, False),
        (False, False),
        (True, True),
        ("true", True),
        ("false", True),  # Go's truth: any non-empty string, as Helm reads it
        ("", False),
        (0, False),
        (1, True),
    ],
)
def test_disable_idms_merge_is_read_as_helm_reads_it(value: object, drops: bool) -> None:
    assert drops_mce_mirrors(value) is drops


def test_a_file_holds_a_locked_value_as_the_chart_reads_it() -> None:
    assert mirrors_held(MIRRORS_FILE_KEY, MIRRORS, list(reversed(MIRRORS)))
    assert mirrors_held(MIRRORS_FILE_KEY, [], MISSING)
    assert not mirrors_held(MIRRORS_FILE_KEY, MIRRORS, MIRRORS[:1])
    assert not mirrors_held(MIRRORS_FILE_KEY, "broken", MISSING)
    assert mirrors_held("disableIdmsMerge", True, "true")
    assert mirrors_held("disableIdmsMerge", False, MISSING)
    assert not mirrors_held("disableIdmsMerge", False, True)


def test_mirrors_read_source_then_mirrors() -> None:
    assert show_mirrors(MIRRORS[:1]) == f"{RELEASE} → mirror.example.com/ocp4/openshift-release-dev"
    assert show_mirrors(MISSING) == "(absent)"
    assert show_mirrors([]) == "none"
    assert show_mirrors("broken") == '"broken"'
    long = [{"source": f"registry{i}.example.com", "mirrors": ["m.example.com"]} for i in range(9)]
    assert len(show_mirrors(long)) == 120
    assert show_value(MIRRORS[:1]) == show_mirrors(MIRRORS[:1])


# ── Locks and drift ──────────────────────────────────────────────────────────


def test_both_inputs_lock_as_whole_values() -> None:
    values = {IMAGE_MIRRORS: MIRRORS, DROP_MCE_MIRRORS: True}
    locked = [IMAGE_MIRRORS, DROP_MCE_MIRRORS]
    assert lock_problems(locked, values) == []
    assert [str(lock.path) for lock in enforced_locks(locked, values)] == locked


def test_a_lock_on_a_value_that_breaks_a_rule_is_not_enforced() -> None:
    broken = {IMAGE_MIRRORS: [{"source": "a.io"}], DROP_MCE_MIRRORS: True}
    locked = [IMAGE_MIRRORS, DROP_MCE_MIRRORS]
    assert lock_problems(locked, broken) == [
        "locked_paths: image_content_sources is locked to a value that breaks a rule: "
        "image_content_sources[0].mirrors: give at least one mirror, like "
        "mirror.example.com/ocp/release",
    ]
    assert [str(lock.path) for lock in enforced_locks(locked, broken)] == [DROP_MCE_MIRRORS]
    alone = {DROP_MCE_MIRRORS: True}
    assert mirror_lock_problem(DROP_MCE_MIRRORS, alone) is not None
    assert enforced_locks([DROP_MCE_MIRRORS], alone) == ()
    assert mirror_lock_problem("owner_merkaz", alone) is None


def drift(locks: list[Lock], values: dict[str, Any]) -> list[tuple[str, object, object]]:
    found = value_drift(locks, values, cluster_name="prod-x-site1", catalog=CATALOG)
    return [(str(d.file_key), d.flavor_value, d.cluster_value) for d in found]


def test_the_mirrors_drift_when_the_file_gives_others() -> None:
    lock = Lock(InputPath.parse(IMAGE_MIRRORS), MIRRORS)
    assert drift([lock], {"imageContentSources": list(reversed(MIRRORS))}) == []
    assert drift([lock], {}) == [("imageContentSources", MIRRORS, MISSING)]
    other = [MIRRORS[0]]
    assert drift([lock], {"imageContentSources": other}) == [
        ("imageContentSources", MIRRORS, other)
    ]
    none = Lock(InputPath.parse(IMAGE_MIRRORS), [])
    assert drift([none], {}) == []


def test_dropping_the_mce_mirrors_drifts_by_what_the_chart_does() -> None:
    drop = Lock(InputPath.parse(DROP_MCE_MIRRORS), True)
    keep = Lock(InputPath.parse(DROP_MCE_MIRRORS), False)
    assert drift([drop], {"disableIdmsMerge": True}) == []
    assert drift([drop], {}) == [("disableIdmsMerge", True, MISSING)]
    assert drift([keep], {}) == []
    assert drift([keep], {"disableIdmsMerge": True}) == [("disableIdmsMerge", False, True)]


# ── Writing them into a cluster file ─────────────────────────────────────────

FILE = (
    '# specName: "agent-mirrors"\n'
    "owner:\n"
    '  merkaz: "1234"\n'
    "mastertag: 4.18.56-x86_64\n"
    "\n"
    "# the pools\n"
    "nodepool:\n"
    "  - infraEnvName: dell-a\n"
    "    replicas: 2\n"
)


def mirrors_edit(value: object, key: str = "imageContentSources") -> SetValue:
    return SetValue(InputPath.parse(key), value)


def test_new_mirror_keys_go_above_nodepool_as_the_template_writes_them() -> None:
    edited = edit_values(FILE, [mirrors_edit(MIRRORS[:1]), mirrors_edit(True, "disableIdmsMerge")])
    assert edited == FILE.replace(
        "\n# the pools\n",
        "\nimageContentSources:\n"
        f'  - source: "{RELEASE}"\n'
        "    mirrors:\n"
        '      - "mirror.example.com/ocp4/openshift-release-dev"\n'
        "\n"
        "disableIdmsMerge: true\n"
        "\n"
        "# the pools\n",
    )
    rendered = load_values(render_cluster_file(TEMPLATE, inputs(**{IMAGE_MIRRORS: MIRRORS[:1]})))
    assert load_values(edited)["imageContentSources"] == rendered["imageContentSources"]


def test_an_existing_list_is_replaced_and_its_line_and_comments_stay() -> None:
    before = FILE.replace(
        "\n# the pools\n",
        "\nimageContentSources:  # ours\n"
        "# the old mirror\n"
        "- source: old.example.com\n"
        "  mirrors: [m.example.com]\n"
        "disableIdmsMerge: true\n"
        "\n# the pools\n",
    )
    edited = edit_values(before, [mirrors_edit(MIRRORS), mirrors_edit(False, "disableIdmsMerge")])
    values = load_values(edited)
    assert values["imageContentSources"] == MIRRORS
    assert values["disableIdmsMerge"] is False
    assert "imageContentSources:  # ours\n" in edited
    assert "# the old mirror\n" in edited
    assert "old.example.com" not in edited
    cleared = edit_values(before, [mirrors_edit([])])
    assert load_values(cleared)["imageContentSources"] == []
    assert "imageContentSources: []  # ours\n" in cleared


def test_a_file_without_nodepool_gets_the_keys_after_its_header() -> None:
    edited = edit_values(
        '# specName: "x"\nmastertag: 4.18.56\n', [mirrors_edit(True, "disableIdmsMerge")]
    )
    assert yaml.safe_load(edited) == {"disableIdmsMerge": True, "mastertag": "4.18.56"}
    assert edited.startswith('# specName: "x"\ndisableIdmsMerge: true\n')
