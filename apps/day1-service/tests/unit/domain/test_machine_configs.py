"""The machine-config catalogue and the nodepool-entry rules (ADR-0027)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_core.domain.git import RepoPath
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.errors import InvalidNodepoolDefaultsError
from wingman_day1.domain.machine_configs import (
    ConfigEntry,
    MachineConfigCatalog,
    NodepoolDefaults,
    cluster_config_problems,
    defaults_problems,
    expand_network_configs,
    flavor_config_problems,
    network_config_name,
    parse_nodepool_defaults,
)

FIXTURES = default_fixture_root()
MC_FILES = FIXTURES / "gitops-day1" / "platform-config" / "mc-files"


def fixture_catalog() -> MachineConfigCatalog:
    return MachineConfigCatalog.from_files(
        RepoPath(f"mc-files/{p.relative_to(MC_FILES).as_posix()}")
        for p in MC_FILES.rglob("*")
        if p.is_file()
    )


def catalog(*files: str) -> MachineConfigCatalog:
    return MachineConfigCatalog.from_files(RepoPath(f"mc-files/{f}") for f in files)


def pools(*configs: list[Any]) -> dict[str, object]:
    return {"nodepools": [{"infra_env": f"pool{i}", "configs": c} for i, c in enumerate(configs)]}


CATALOG = fixture_catalog()


# ── The catalogue ────────────────────────────────────────────────────────────


def test_the_fixture_tree_offers_its_static_configs_and_hardware_types() -> None:
    assert [(c.folder, c.name) for c in CATALOG.static_configs()] == [
        ("", "nic-ring-buffer"),
        ("", "worker-kubeletconfig-reserved"),
        ("", "workers-chrony-configuration"),
        ("kubevirt", "kubevirt-worker-tuning"),
    ]
    assert [h.name for h in CATALOG.hardware_types()] == ["cisco", "dell", "dell-data"]
    assert str(CATALOG.hardware["dell"].template) == ("mc-files/templates/nm-conf-template-dell.bu")
    assert str(CATALOG.static["nic-ring-buffer"].path) == "mc-files/nic-ring-buffer.bu"
    assert str(CATALOG.static["worker-kubeletconfig-reserved"].path) == (
        "mc-files/worker-kubeletconfig-reserved"
    )
    assert CATALOG.legacy == {"restored-example-config"}
    assert CATALOG.problems == ()


def test_a_butane_file_beats_a_plain_one_and_the_root_beats_subfolders() -> None:
    found = catalog("a/x", "b/x.bu", "x", "c/y", "b/y")
    assert str(found.static["x"].path) == "mc-files/b/x.bu"
    assert str(found.static["y"].path) == "mc-files/b/y"
    assert found.static["y"].folder == "b"
    assert "x: also in mc-files/x, mc-files/a/x; the CI uses mc-files/b/x.bu" in found.problems
    rooted = catalog("a/z.bu", "z.bu")
    assert str(rooted.static["z"].path) == "mc-files/z.bu"


def test_subfolders_are_ordered_by_path_parts_like_the_ci() -> None:
    # As Path objects sort: "a" < "a-b", although "a-b/" < "a/" as strings.
    found = catalog("a-b/x.bu", "a/x.bu")
    assert str(found.static["x"].path) == "mc-files/a/x.bu"


def test_legacy_names_are_not_offered_and_a_legacy_win_is_reported() -> None:
    found = catalog("legacy/old.bu", "legacy/shared.bu", "virt/shared.bu", "kept.bu")
    assert set(found.static) == {"kept"}
    assert found.legacy == {"old", "shared"}
    assert any(
        p.startswith("shared: the CI uses mc-files/legacy/shared.bu") for p in found.problems
    )
    nested = catalog("virt/legacy/x.bu")  # only a top-level legacy/ is special
    assert set(nested.static) == {"x"}


def test_a_static_name_a_template_captures_is_not_offered() -> None:
    found = catalog("templates/nm-conf-template-dell.bu", "tuning-dell.bu", "dell.bu")
    assert set(found.static) == {"dell"}
    assert any("tuning-dell.bu: the name ends in -dell" in p for p in found.problems)


def test_templates_must_follow_the_hardware_naming_and_are_never_static() -> None:
    found = catalog(
        "templates/nm-conf-template-dell.bu",
        "templates/nm-conf-template.bu",
        "templates/other.bu",
        "templates/deeper/nm-conf-template-cisco.bu",
        "templates/nm-conf-template-Bad_Name.bu",
    )
    assert set(found.hardware) == {"dell"}
    assert found.static == {}
    assert len(found.problems) == 4
    assert all("is no hardware type" in p for p in found.problems)


def test_the_hardware_type_is_what_the_ci_strips_nm_conf_template_from() -> None:
    """The CI maps ``nm-conf-template-<hw>.bu`` to the suffix ``-<hw>``; 3.3.0 wanted ``-hw-<hw>``.

    With 3.3.0's prefix every production template was refused, and so was every
    nodepool naming a network config. A ``-hw-`` file is ``hw-<x>`` to the CI too.
    """
    found = catalog(
        "templates/nm-conf-template-dell.bu",
        "templates/nm-conf-template-dell-data.bu",
        "templates/nm-conf-template-hw-cisco.bu",
    )
    assert set(found.hardware) == {"dell", "dell-data", "hw-cisco"}
    assert found.problems == ()
    assert (
        found.template_for(network_config_name("prod-rcs-five-a", "dell")) == found.hardware["dell"]
    )


def test_docs_dot_files_and_paths_outside_mc_files_are_ignored() -> None:
    files = [RepoPath("mc-files/README.md"), RepoPath("mc-files/.gitkeep")]
    files += [RepoPath("mc-files/.hidden/x.bu"), RepoPath("sites/x.bu"), RepoPath("mc-files")]
    assert MachineConfigCatalog.from_files(files) == MachineConfigCatalog()


def test_a_file_whose_name_is_not_a_usable_config_name_is_reported() -> None:
    found = catalog("Upper.bu", "has space", "ok.yaml")
    assert set(found.static) == {"ok.yaml"}
    assert len(found.problems) == 2


@pytest.mark.parametrize(
    ("name", "hardware"),
    [
        ("nm-conf-prod-x-site1-dell", "dell"),
        ("nm-conf-prod-x-site1-dell-data", "dell-data"),
        ("nm-conf-prod-x-site1-cisco", "cisco"),
        ("nm-conf-prod-x-site1-data", None),
        ("dell", None),
        ("nm-conf", None),
    ],
)
def test_the_longest_hardware_suffix_wins(name: str, hardware: str | None) -> None:
    found = CATALOG.template_for(name)
    assert (found.name if found else None) == hardware


# ── Entries in a flavor ─────────────────────────────────────────────────────


def test_a_flavor_may_use_static_configs_and_the_network_config_with_hardware() -> None:
    values = pools(
        [{"name": "nm-conf", "hardware": "dell"}, {"name": "workers-chrony-configuration"}],
        [{"name": "kubevirt-worker-tuning"}, {"name": "nic-ring-buffer", "hardware": None}],
    )
    assert flavor_config_problems(values, CATALOG) == []
    assert flavor_config_problems({}, CATALOG) == []
    assert flavor_config_problems({"nodepools": [{"replicas": 3}]}, CATALOG) == []


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({"name": "nm-conf"}, "nm-conf needs a hardware type, one of cisco, dell, dell-data"),
        ({"name": "nm-conf", "hardware": ""}, "nm-conf needs a hardware type"),
        ({"name": "nm-conf", "hardware": "hp"}, "no hardware type 'hp', one of cisco"),
        ({"name": "nic-ring-buffer", "hardware": "dell"}, "hardware applies only to nm-conf"),
        (
            {"name": "nm-conf-prod-x-site1-dell"},
            "'nm-conf-prod-x-site1-dell' is one cluster's network config name; write "
            "{name: nm-conf, hardware: dell} instead",
        ),
        (
            {"name": "worker-chrony-configuration"},
            "no machine config 'worker-chrony-configuration' in mc-files/ "
            "(did you mean 'workers-chrony-configuration'?)",
        ),
        ({"name": "nope"}, "no machine config 'nope' in mc-files/"),
        ({"name": "nic-ring-buffer.bu"}, "write 'nic-ring-buffer' without .bu"),
        ({"name": "restored-example-config"}, "is only in mc-files/legacy/"),
        ("nic-ring-buffer", "must be {name: <config>} or {name: nm-conf, hardware: <type>}"),
        ({"name": "nic-ring-buffer", "ref": "x"}, "unknown keys ref"),
        ({"hardware": "dell"}, "name is required"),
        ({"name": ""}, "name is required"),
        ({"name": "nm-conf", "hardware": 3}, "hardware must be a string"),
    ],
)
def test_each_bad_entry_is_one_problem_at_its_path(entry: object, problem: str) -> None:
    problems = flavor_config_problems(pools([{"name": "nic-ring-buffer"}], [entry]), CATALOG)
    assert len(problems) == 1, problems
    assert problems[0].startswith("nodepools[1].configs[0]: ")
    assert problem in problems[0]


def test_every_bad_entry_is_listed() -> None:
    values = pools([{"name": "nope"}, {"name": "nm-conf"}], [{"name": "also-nope"}])
    assert [p.split(":")[0] for p in flavor_config_problems(values, CATALOG)] == [
        "nodepools[0].configs[0]",
        "nodepools[0].configs[1]",
        "nodepools[1].configs[0]",
    ]


def test_an_entry_listed_twice_in_one_nodepool_is_refused() -> None:
    values = pools(
        [
            {"name": "nic-ring-buffer"},
            {"name": "nm-conf", "hardware": "dell"},
            {"name": "nic-ring-buffer"},
            {"name": "nm-conf", "hardware": "cisco"},
        ],
        [{"name": "nic-ring-buffer"}],
    )
    assert flavor_config_problems(values, CATALOG) == [
        "nodepools[0].configs[2]: the same entry as nodepools[0].configs[0]"
    ]


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"nodepools": "two"}, "nodepools: must be a list"),
        ({"nodepools": ["x"]}, "nodepools[0]: must be a mapping"),
        ({"nodepools": [{"configs": "nic-ring-buffer"}]}, "nodepools[0].configs: must be a list"),
    ],
)
def test_a_wrong_shape_around_the_entries_is_a_problem(
    values: dict[str, object], problem: str
) -> None:
    problems = flavor_config_problems(values, CATALOG)
    assert len(problems) == 1
    assert problems[0].startswith(problem)


def test_an_empty_catalogue_resolves_nothing() -> None:
    problems = flavor_config_problems(
        pools([{"name": "nm-conf", "hardware": "dell"}, {"name": "x"}]), MachineConfigCatalog()
    )
    assert "mc-files/templates/ has no nm-conf-template-<hardware>.bu" in problems[0]
    assert problems[1] == "nodepools[0].configs[1]: no machine config 'x' in mc-files/"


# ── Entries at create ───────────────────────────────────────────────────────


def test_at_create_the_network_config_is_expanded_for_the_cluster() -> None:
    inputs: dict[str, Any] = {
        "owner_merkaz": "1",
        **pools(
            [{"name": "nm-conf", "hardware": "dell-data"}, {"name": "nic-ring-buffer"}],
            [{"name": "nm-conf", "hardware": "cisco"}],
        ),
    }
    assert cluster_config_problems(inputs, CATALOG, cluster_name="prod-x-site1") == []
    expanded = expand_network_configs(inputs, cluster_name="prod-x-site1")
    pools_out: Any = expanded["nodepools"]
    assert pools_out[0]["configs"] == [
        {"name": "nm-conf-prod-x-site1-dell-data"},
        {"name": "nic-ring-buffer"},
    ]
    assert pools_out[1] == {
        "infra_env": "pool1",
        "configs": [{"name": "nm-conf-prod-x-site1-cisco"}],
    }
    assert expanded["owner_merkaz"] == "1"
    assert inputs["nodepools"][0]["configs"][0] == {"name": "nm-conf", "hardware": "dell-data"}


def test_expanding_leaves_other_shapes_alone() -> None:
    assert expand_network_configs({"x": 1}, cluster_name="c") == {"x": 1}
    odd = {"nodepools": ["x", {"replicas": 1}, {"configs": [3]}]}
    assert expand_network_configs(odd, cluster_name="c") == odd


def test_at_create_the_clusters_own_network_name_may_be_written_out() -> None:
    own = pools([{"name": "nm-conf-prod-x-site1-dell"}])
    assert cluster_config_problems(own, CATALOG, cluster_name="prod-x-site1") == []
    other = pools([{"name": "nm-conf-prod-y-site1-dell"}])
    assert cluster_config_problems(other, CATALOG, cluster_name="prod-x-site1") == [
        "nodepools[0].configs[0]: 'nm-conf-prod-y-site1-dell' is another cluster's network "
        "config name; write {name: nm-conf, hardware: dell} instead"
    ]


def test_a_network_name_the_ci_would_read_as_other_hardware_is_refused() -> None:
    found = catalog("templates/nm-conf-template-l4.bu", "templates/nm-conf-template-cisco-l4.bu")
    entry = pools([{"name": "nm-conf", "hardware": "l4"}])
    assert cluster_config_problems(entry, found, cluster_name="prod-a-site1") == []
    assert cluster_config_problems(entry, found, cluster_name="prod-cisco") == [
        "nodepools[0].configs[0]: the l4 network config would be named "
        "'nm-conf-prod-cisco-l4', which the CI reads as hardware 'cisco-l4'"
    ]


def test_a_network_name_too_long_for_the_ci_is_refused() -> None:
    entry = pools([{"name": "nm-conf", "hardware": "dell"}])
    problems = cluster_config_problems(entry, CATALOG, cluster_name="c" * 250)
    assert problems == [
        f"nodepools[0].configs[0]: 'nm-conf-{'c' * 250}-dell' is longer than 253 characters"
    ]


@given(
    hardware=st.lists(
        st.from_regex(r"[a-z0-9]{1,3}(-[a-z0-9]{1,3}){0,2}", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    cluster=st.from_regex(r"[a-z0-9]{1,4}(-[a-z0-9]{1,4}){0,3}", fullmatch=True),
    pick=st.integers(min_value=0),
)
def test_an_accepted_network_entry_is_one_the_ci_renders_from_its_template(
    hardware: list[str], cluster: str, pick: int
) -> None:
    found = catalog(*(f"templates/nm-conf-template-{h}.bu" for h in hardware))
    chosen = hardware[pick % len(hardware)]
    entry = pools([{"name": "nm-conf", "hardware": chosen}])
    if cluster_config_problems(entry, found, cluster_name=cluster):
        return
    name = network_config_name(cluster, chosen)
    template = found.template_for(name)
    assert template is not None
    assert template.name == chosen
    expanded: Any = expand_network_configs(entry, cluster_name=cluster)
    assert expanded["nodepools"][0]["configs"] == [{"name": name}]


# ── Nodepool defaults ────────────────────────────────────────────────────────


def test_the_fixture_defaults_are_the_teams_three_configs() -> None:
    content = (FIXTURES / "wingman" / "cluster-specs" / "nodepool-defaults.yaml").read_text()
    defaults = parse_nodepool_defaults(content)
    assert defaults.configs == (
        ConfigEntry("nm-conf"),
        ConfigEntry("workers-chrony-configuration"),
        ConfigEntry("nic-ring-buffer"),
    )
    assert defaults_problems(defaults, CATALOG) == []
    assert defaults.configs[0].to_input() == {"name": "nm-conf"}


def test_defaults_may_preset_a_hardware_type_and_are_checked_like_a_flavor() -> None:
    defaults = parse_nodepool_defaults(
        "configs:\n"
        "  - {name: nm-conf, hardware: dell}\n"
        "  - {name: nope}\n"
        "  - {name: nm-conf, hardware: hp}\n"
    )
    assert defaults.configs[0].to_input() == {"name": "nm-conf", "hardware": "dell"}
    assert defaults_problems(defaults, CATALOG) == [
        "configs[1]: no machine config 'nope' in mc-files/",
        "configs[2]: no hardware type 'hp', one of cisco, dell, dell-data",
    ]


@pytest.mark.parametrize("content", ["", "# nothing yet\n", "configs: []\n"])
def test_an_empty_defaults_file_is_no_defaults(content: str) -> None:
    assert parse_nodepool_defaults(content) == NodepoolDefaults()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("configs: [\n", "not valid YAML"),
        ("- name: nm-conf\n", "not a YAML mapping"),
        ("config:\n  - name: nm-conf\n", "not a valid defaults document"),
        ("configs:\n  - {name: nm-conf, ref: x}\n", "not a valid defaults document"),
        ("configs:\n  - {name: ''}\n", "not a valid defaults document"),
        ("configs:\n" + "  - {name: x}\n" * 51, "not a valid defaults document"),
    ],
)
def test_a_broken_defaults_file_is_an_error_with_its_problems(content: str, message: str) -> None:
    with pytest.raises(InvalidNodepoolDefaultsError) as caught:
        parse_nodepool_defaults(content)
    assert message in str(caught.value)
    assert caught.value.problems or "mapping" in message
