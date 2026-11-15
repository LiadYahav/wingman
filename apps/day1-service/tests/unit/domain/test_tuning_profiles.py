"""The tuning-profile catalogue and the names a nodepool gives (ADR-0061)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from wingman_day1.domain.tuning_profiles import (
    MAX_TUNING_FILES,
    TuningCatalog,
    TuningKind,
    edit_problems,
    edit_text_problems,
    file_names,
    file_value,
    input_problems,
    tuning_names,
)

FIXTURES = Path(__file__).parents[5] / "dev/gitlab-fixtures/gitops-day1/platform-config"


def tuned(name: str, data: str = "[main]\nsummary=Something\n") -> str:
    indented = "".join(f"      {line}\n" for line in data.splitlines())
    return (
        f"apiVersion: tuned.openshift.io/v1\nkind: Tuned\nmetadata:\n  name: {name}\n"
        f"spec:\n  profile:\n  - name: {name}\n    data: |\n{indented}"
    )


def performance(name: str) -> str:
    return (
        f"apiVersion: performance.openshift.io/v2\nkind: PerformanceProfile\n"
        f"metadata:\n  name: {name}\nspec:\n  cpu:\n    reserved: 0-1\n"
    )


def catalog(files: dict[str, str]) -> TuningCatalog:
    return TuningCatalog.from_files(files)


def fixture_catalog() -> TuningCatalog:
    files = {
        str(p.relative_to(FIXTURES)): p.read_text()
        for p in sorted((FIXTURES / "tuning").rglob("*"))
        if p.is_file()
    }
    return TuningCatalog.from_files(files)


SMALL = catalog(
    {
        "tuning/tuned-a.yaml": tuned("tuned-a"),
        "tuning/tuned-b.yaml": tuned("tuned-b"),
        "tuning/perf-one.yaml": performance("perf-one"),
        "tuning/perf-two.yaml": performance("perf-two"),
        "tuning/prod-x-site1/tuned-local.yaml": tuned("tuned-local"),
        "tuning/prod-x-site1/perf-local.yaml": performance("perf-local"),
    }
)


# ── The catalogue ────────────────────────────────────────────────────────────


def test_the_fixture_catalogue() -> None:
    found = fixture_catalog()
    assert [(p.name, p.kind, p.requires_performance_profile) for p in found.profiles()] == [
        ("performance-pinned", TuningKind.PERFORMANCE_PROFILE, None),
        ("tuned-network-latency", TuningKind.TUNED, None),
        ("tuned-pinned-irq", TuningKind.TUNED, "performance-pinned"),
        ("tuned-sysctl-baseline", TuningKind.TUNED, None),
    ]
    assert found.shared["tuned-network-latency"].summary == "Lower network latency on worker nodes"
    assert found.shared["performance-pinned"].summary is None
    assert found.clusters_with_variant("tuned-network-latency") == ["prod-lark-site1"]
    assert [(p.path, p.detail) for p in found.problems] == [
        (
            "tuning/tuned-misnamed.yaml",
            "metadata.name is tuned-renamed; it must be the file's name, tuned-misnamed",
        )
    ]


@pytest.mark.parametrize(
    ("path", "content", "detail"),
    [
        ("tuning/a/b/tuned-x.yaml", tuned("tuned-x"), "nothing deeper"),
        ("tuning/tuned-x.yml", tuned("tuned-x"), "not a .yaml file"),
        ("tuning/Tuned_X.yaml", tuned("Tuned_X"), "is not a DNS-1123 label"),
        ("tuning/" + "t" * 64 + ".yaml", tuned("t" * 64), "longer than 63 characters"),
        ("tuning/tuned-x.yaml", tuned("tuned-x") + "---\n" + tuned("tuned-y"), "2 documents"),
        ("tuning/tuned-x.yaml", "- a list\n", "exactly one YAML mapping"),
        ("tuning/tuned-x.yaml", "a: [\n", "not valid YAML"),
        (
            "tuning/tuned-x.yaml",
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: tuned-x\n",
            "apiVersion 'v1' kind 'ConfigMap'; it must be Tuned (tuned.openshift.io/v1) or "
            "PerformanceProfile (performance.openshift.io/v2)",
        ),
        ("tuning/tuned-x.yaml", tuned("tuned-y"), "metadata.name is tuned-y"),
        ("tuning/tuned-x.yaml", "apiVersion: tuned.openshift.io/v1\nkind: Tuned\n", "is None"),
    ],
)
def test_a_file_that_breaks_a_rule_is_a_problem_and_never_offered(
    path: str, content: str, detail: str
) -> None:
    found = catalog({path: content})
    assert found.shared == {} and found.variants == {}
    ((problem_path, problem),) = [(p.path, p.detail) for p in found.problems]
    assert problem_path == path
    assert detail in problem


def test_hidden_files_are_skipped_and_a_readme_is_a_problem_as_the_ci_reads_them() -> None:
    found = catalog(
        {"tuning/README.md": "# notes\n", "tuning/.gitkeep": "", "tuning/.x/tuned-a.yaml": ""}
    )
    assert found.shared == {}
    assert [(p.path, p.detail) for p in found.problems] == [
        ("tuning/README.md", "not a .yaml file")
    ]


def test_duplicate_keys_are_refused() -> None:
    found = catalog({"tuning/tuned-x.yaml": tuned("tuned-x") + "kind: Tuned\n"})
    ((problem,),) = [[p.detail for p in found.problems]]
    assert problem.startswith("not valid YAML: ")
    assert "duplicate key 'kind'" in problem


def test_too_many_files_is_a_problem() -> None:
    found = TuningCatalog.from_files({}, listed=MAX_TUNING_FILES + 1)
    assert [p.detail for p in found.problems] == [
        f"{MAX_TUNING_FILES + 1} files; only the first {MAX_TUNING_FILES} are read"
    ]


def test_the_summary_and_the_performance_include_come_from_main() -> None:
    data = (
        "[main]\nsummary=Pinned and quiet\ninclude=openshift-node, "
        "openshift-node-performance-perf-one\n[sysctl]\nsummary=not this one\n"
    )
    found = catalog({"tuning/tuned-x.yaml": tuned("tuned-x", data)}).shared["tuned-x"]
    assert (found.summary, found.requires_performance_profile) == ("Pinned and quiet", "perf-one")
    bare = catalog({"tuning/tuned-y.yaml": tuned("tuned-y", "[sysctl]\na=1\n")}).shared["tuned-y"]
    assert (bare.summary, bare.requires_performance_profile) == (None, None)


# ── Names ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "names"),
    [
        (None, []),
        ("", []),
        ([], []),
        ("tuned-a", ["tuned-a"]),
        (["tuned-a", "tuned-b"], ["tuned-a", "tuned-b"]),
        (["tuned-a", ""], None),
        ([1], None),
        (3, None),
        ({"name": "tuned-a"}, None),
    ],
)
def test_tuning_names_read_a_string_or_a_list(value: object, names: list[str] | None) -> None:
    assert tuning_names(value) == names


def test_the_file_writes_one_name_as_a_string_and_several_as_a_list() -> None:
    assert file_value(["tuned-a"]) == "tuned-a"
    assert file_value(["tuned-a", "tuned-b"]) == ["tuned-a", "tuned-b"]


def test_file_names_are_first_seen_and_once() -> None:
    values = {
        "nodepool": [
            {"tuningConfig": ["tuned-b", "tuned-a"]},
            {"tuningConfig": "tuned-a"},
            {},
            "not a pool",
        ]
    }
    assert file_names(values) == ["tuned-b", "tuned-a"]


# ── Flavor save and create ───────────────────────────────────────────────────


def pools(*tuning: object) -> dict[str, Any]:
    return {"nodepools": [{"tuning_config": t} for t in tuning]}


def test_shared_profiles_are_accepted_in_any_form() -> None:
    assert input_problems(pools(["tuned-a", "perf-one"], "tuned-b", [], None), SMALL) == []
    assert input_problems({"nodepools": [{"replicas": 2}]}, SMALL) == []


def test_each_broken_name_is_one_problem_at_its_path() -> None:
    assert input_problems(
        pools(["tuned-aa", "tuned-local", "tuned-a", "tuned-a"], {"x": 1}), SMALL
    ) == [
        "nodepools[0].tuning_config[0]: tuned-aa is not a tuning profile in tuning/ "
        "(did you mean tuned-a?)",
        "nodepools[0].tuning_config[1]: tuned-local is a variant for cluster prod-x-site1 only; "
        "a flavor or a new cluster names shared profiles from tuning/",
        "nodepools[0].tuning_config[3]: tuned-a is listed twice",
        "nodepools[1].tuning_config: must be a list of tuning profile names",
    ]


def test_a_nodepool_takes_at_most_one_performance_profile() -> None:
    assert input_problems(pools(["perf-one", "tuned-a", "perf-two"]), SMALL) == [
        "nodepools[0].tuning_config: at most one PerformanceProfile per nodepool (HyperShift); "
        "it names perf-one, perf-two"
    ]


def test_more_than_sixteen_profiles_is_refused() -> None:
    names = [f"tuned-{i}" for i in range(17)]
    many = catalog({f"tuning/{n}.yaml": tuned(n) for n in names})
    assert input_problems(pools(names), many) == [
        "nodepools[0].tuning_config: 17 profiles; the limit is 16"
    ]


def test_without_a_tuning_folder_every_name_says_so() -> None:
    assert input_problems(pools("tuned-a"), TuningCatalog(found=False)) == [
        "nodepools[0].tuning_config[0]: tuned-a is not a tuning profile in tuning/; the day1 "
        "repo has no tuning/ folder"
    ]


# ── Edit ─────────────────────────────────────────────────────────────────────

CLUSTER = "prod-x-site1"


def cluster_file(*tuning: object, configmap: list[dict[str, str]] | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "nodepool": [{"infraEnvName": f"pool{i}", "tuningConfig": t} for i, t in enumerate(tuning)]
    }
    if configmap is not None:
        values["tuningConfigmap"] = configmap
    return values


def test_an_edit_may_add_a_shared_profile_a_variant_or_a_configmap_entry() -> None:
    old = cluster_file("tuned-a", configmap=[{"name": "tuned-handmade", "tuning": tuned("x")}])
    new = cluster_file(["tuned-a", "tuned-b"], ["tuned-local", "tuned-handmade"])
    assert edit_problems(old, new, SMALL, cluster_name=CLUSTER) == []


def test_an_edit_adding_an_unknown_name_is_refused_but_old_names_are_not_rechecked() -> None:
    old = cluster_file("tuned-gone")
    new = cluster_file("tuned-gone", ["tuned-gone", "tuned-new"], 7)
    assert edit_problems(old, new, SMALL, cluster_name=CLUSTER) == [
        "nodepool[1].tuningConfig: tuned-new is not in tuning/, in tuning/prod-x-site1/ or in "
        "this file's tuningConfigmap",
        "nodepool[2].tuningConfig: must be a tuning profile name or a list of names",
    ]
    assert edit_problems(cluster_file(7), cluster_file(7), SMALL, cluster_name=CLUSTER) == []


def test_another_cluster_s_variant_is_not_this_one_s() -> None:
    problems = edit_problems(
        cluster_file(None), cluster_file("tuned-local"), SMALL, cluster_name="prod-y-site1"
    )
    assert problems == [
        "nodepool[0].tuningConfig: tuned-local is not in tuning/, in tuning/prod-y-site1/ or in "
        "this file's tuningConfigmap"
    ]


def test_an_edit_giving_a_pool_two_performance_profiles_is_refused() -> None:
    old = cluster_file(
        "tuned-a",
        ["perf-one", "perf-handmade"],
        configmap=[{"name": "perf-handmade", "tuning": performance("perf-handmade")}],
    )
    # The second pool already had two (by its configmap entry's kind): not this edit's doing.
    new = cluster_file(["tuned-a", "perf-one", "perf-local"], ["perf-one", "perf-handmade"])
    assert edit_problems(old, new, SMALL, cluster_name=CLUSTER) == [
        "nodepool[0].tuningConfig: at most one PerformanceProfile per nodepool (HyperShift); it "
        "names perf-one, perf-local"
    ]


def test_an_edit_text_that_does_not_parse_is_left_to_the_file_rules() -> None:
    assert edit_text_problems("a: 1\n", "a: [\n", SMALL, cluster_name=CLUSTER) == []
    new = "nodepool:\n- tuningConfig: tuned-new\n"
    assert edit_text_problems("a: [\n", new, SMALL, cluster_name=CLUSTER) == [
        "nodepool[0].tuningConfig: tuned-new is not in tuning/, in tuning/prod-x-site1/ or in "
        "this file's tuningConfigmap"
    ]
