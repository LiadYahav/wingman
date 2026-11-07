"""The cluster values file: strict parsing, the comment header, and who owns which key."""

from __future__ import annotations

from pathlib import Path

import pytest

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.cluster_file import (
    AUTOMATION_KEYS,
    PATH_KEYS,
    Provenance,
    describe_for_review,
    edit_problems,
    load_values,
    read_provenance,
    read_values,
    rendered_file_problems,
    require_valid,
    with_provenance,
)
from wingman_day1.domain.errors import InvalidClusterFileError

DAY1_SITES = default_fixture_root() / "gitops-day1" / "platform-config" / "sites"
FIXTURE_FILES = sorted(DAY1_SITES.glob("*/mces/*/hostedClusters/*.yaml"))

VALID = """\
owner:
  merkaz: "1234"
  anaf: "56"
  mador: "7"
mastertag: 4.18.22-x86_64
nodepool:
  - infraEnvName: dell-r660-site1-128c-1024gb-5tb
    replicas: 2
    labels:
      allowDeletion: false
    configs:
      - name: worker-kubeletconfig-reserved
"""

ALLOCATED = VALID + "vlanId: 412\ndhcp_values:\n  network: 10.20.99.0\n"


# ── load_values ──────────────────────────────────────────────────────────────


def test_an_empty_file_is_an_empty_mapping() -> None:
    assert load_values("") == {}
    assert load_values("# only a comment\n") == {}


def test_duplicate_keys_are_refused_with_their_line() -> None:
    with pytest.raises(InvalidClusterFileError) as caught:
        load_values("mastertag: 4.18.22\nowner: {}\nmastertag: 4.18.23\n")
    assert "line 3" in str(caught.value)
    assert any("duplicate key 'mastertag'" in p for p in caught.value.problems)


def test_duplicate_keys_in_nested_mappings_are_refused_too() -> None:
    with pytest.raises(InvalidClusterFileError):
        load_values("owner:\n  merkaz: '1'\n  merkaz: '2'\n")


def test_more_than_one_document_is_refused() -> None:
    with pytest.raises(InvalidClusterFileError) as caught:
        load_values("a: 1\n---\nb: 2\n")
    assert "one YAML document" in str(caught.value)


@pytest.mark.parametrize(("content", "kind"), [("- a\n- b\n", "list"), ("just text\n", "str")])
def test_a_document_that_is_not_a_mapping_is_refused(content: str, kind: str) -> None:
    with pytest.raises(InvalidClusterFileError) as caught:
        load_values(content)
    assert caught.value.problems == (f"the document is a {kind}",)


def test_a_syntax_error_names_its_line_and_column() -> None:
    with pytest.raises(InvalidClusterFileError) as caught:
        load_values("a: 1\nb: [unclosed\n")
    assert "line" in str(caught.value)
    assert "column" in str(caught.value)


def test_python_tags_are_refused_by_the_safe_loader() -> None:
    with pytest.raises(InvalidClusterFileError):
        load_values("a: !!python/object:os.system x\n")


def test_a_yaml_error_without_a_position_is_still_reported() -> None:
    # A control character is a reader error: a YAMLError that carries no mark.
    with pytest.raises(InvalidClusterFileError) as caught:
        load_values("a: \x07\n")
    assert str(caught.value) == "not valid YAML"
    assert caught.value.problems


# ── The header ───────────────────────────────────────────────────────────────


def test_the_legacy_two_line_header_still_links_a_file_to_its_spec() -> None:
    provenance = read_provenance(
        '# specName: "agent-single"\n# specVersion: "1.0.0"\nmastertag: x\n'
    )
    assert provenance == Provenance("agent-single", "1.0.0", (), ())


def test_the_header_stops_at_the_first_line_that_is_not_a_comment() -> None:
    provenance = read_provenance('mastertag: x\n# specName: "late"\n')
    assert provenance.spec_name is None


def test_a_file_of_only_comments_is_read_to_its_end() -> None:
    provenance = read_provenance('# a note\n# specName: "only-comments"\n')
    assert provenance.spec_name == "only-comments"


def test_a_file_without_a_header_has_no_provenance() -> None:
    assert read_provenance(VALID) == Provenance()


def test_requested_addons_round_trip_through_the_header() -> None:
    addons = (
        RequestedAddon("redbull", "cluster-roles", "main", {"replicas": 3, "x": {"y": "z"}}),
        RequestedAddon("lynx", "backup", "1.2.0"),
    )
    content = with_provenance(VALID, Provenance("agent-standard", "1.0.0", addons))
    assert content.startswith('# specName: "agent-standard"\n# specVersion: "1.0.0"\n')
    assert content.endswith(VALID)
    assert load_values(content) == load_values(VALID)
    assert read_provenance(content) == Provenance("agent-standard", "1.0.0", addons, ())


def test_no_provenance_writes_no_header() -> None:
    assert with_provenance(VALID, Provenance()) == VALID


@pytest.mark.parametrize(
    "line",
    ["# wingmanAddons: not json", '# wingmanAddons: {"a": 1}', '# wingmanAddons: [{"team": "x"}]'],
)
def test_an_unreadable_addons_header_is_a_problem_not_a_crash(line: str) -> None:
    provenance = read_provenance(f'# specName: "s"\n{line}\nmastertag: x\n')
    assert provenance.spec_name == "s"
    assert provenance.requested_addons == ()
    assert len(provenance.problems) == 1
    assert "wingmanAddons" in provenance.problems[0]


# ── Rendered files ───────────────────────────────────────────────────────────


def test_a_valid_rendered_file_has_no_problems() -> None:
    assert rendered_file_problems(VALID) == []


def _without(content: str, key_line: str) -> str:
    return "\n".join(line for line in content.splitlines() if not line.startswith(key_line)) + "\n"


def test_mastertag_is_required() -> None:
    assert "mastertag is required" in rendered_file_problems(_without(VALID, "mastertag"))


@pytest.mark.parametrize("tag", ["4.18", "latest", "v4.18.22", "4.18.22-X86"])
def test_a_mastertag_that_is_not_a_release_is_refused(tag: str) -> None:
    content = VALID.replace("4.18.22-x86_64", tag)
    assert any("is not an OpenShift release" in p for p in rendered_file_problems(content))


@pytest.mark.parametrize("tag", ["4.18.22", "4.16.27-x86_64", "4.21.40-multi"])
def test_releases_with_and_without_an_arch_are_accepted(tag: str) -> None:
    assert rendered_file_problems(VALID.replace("4.18.22-x86_64", tag)) == []


@pytest.mark.parametrize("nodepool", ["nodepool: []\n", "nodepool: x\n", ""])
def test_a_rendered_file_needs_at_least_one_nodepool(nodepool: str) -> None:
    content = "mastertag: 4.18.22\n" + nodepool
    assert "nodepool must list at least one nodepool" in rendered_file_problems(content)


def test_the_agent_platform_needs_an_infra_env_per_nodepool() -> None:
    content = "mastertag: 4.18.22\nnodepool:\n  - name: workers\n    replicas: 1\n"
    problems = rendered_file_problems(content)
    assert any("infraEnvName is required on the Agent platform" in p for p in problems)


def test_kubevirt_nodepools_need_only_a_name() -> None:
    content = "mastertag: 4.18.22\nplatform: kubevirt\nnodepool:\n  - name: zone-a\n"
    assert rendered_file_problems(content) == []


def test_a_nodepool_needs_an_infra_env_or_a_name() -> None:
    content = "mastertag: 4.18.22\nplatform: kubevirt\nnodepool:\n  - replicas: 1\n"
    assert any("infraEnvName or an explicit name" in p for p in rendered_file_problems(content))


def test_a_nodepool_entry_must_be_a_mapping() -> None:
    content = "mastertag: 4.18.22\nnodepool:\n  - just-a-string\n"
    assert "nodepool[0] must be a mapping" in rendered_file_problems(content)


def test_two_nodepools_sharing_an_infra_env_must_each_set_name() -> None:
    shared = "mastertag: 4.18.22\nnodepool:\n  - infraEnvName: pool\n  - infraEnvName: pool\n"
    assert any("used twice" in p for p in rendered_file_problems(shared))
    named = (
        "mastertag: 4.18.22\nnodepool:\n"
        "  - {infraEnvName: pool, name: zone-a}\n  - {infraEnvName: pool, name: zone-b}\n"
    )
    assert rendered_file_problems(named) == []


@pytest.mark.parametrize("replicas", ["-1", "true", "two", "1.5"])
def test_replicas_must_be_a_whole_number_of_at_least_zero(replicas: str) -> None:
    content = f"mastertag: 4.18.22\nnodepool:\n  - infraEnvName: pool\n    replicas: {replicas}\n"
    assert any("replicas must be a whole number" in p for p in rendered_file_problems(content))


def test_zero_replicas_is_honoured() -> None:
    content = "mastertag: 4.18.22\nnodepool:\n  - infraEnvName: pool\n    replicas: 0\n"
    assert rendered_file_problems(content) == []


@pytest.mark.parametrize("key", AUTOMATION_KEYS)
def test_a_rendered_file_never_carries_an_automation_key(key: str) -> None:
    problems = rendered_file_problems(VALID + f"{key}: x\n")
    assert any(p.startswith(f"{key} is written by automation") for p in problems)


@pytest.mark.parametrize("key", PATH_KEYS)
def test_a_rendered_file_never_sets_what_its_path_says(key: str) -> None:
    problems = rendered_file_problems(VALID + f"{key}: x\n")
    assert any(p.startswith(f"{key} comes from the file's path") for p in problems)


def test_an_unparsable_render_reports_the_parse_problem() -> None:
    assert rendered_file_problems("a: [\n")


def test_require_valid_raises_only_when_there_are_problems() -> None:
    require_valid([], message="fine")
    with pytest.raises(InvalidClusterFileError) as caught:
        require_valid(["one", "two"], message="broken")
    assert caught.value.problems == ("one", "two")


# ── Edits ────────────────────────────────────────────────────────────────────


def test_an_edit_that_keeps_automations_keys_is_accepted() -> None:
    edited = ALLOCATED.replace("replicas: 2", "replicas: 3")
    assert edit_problems(ALLOCATED, edited) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("vlanId: 412", "vlanId: 413"),
        ("vlanId: 412\n", ""),
        ("  network: 10.20.99.0", "  network: 10.20.98.0"),
    ],
)
def test_changing_or_dropping_what_automation_wrote_is_refused(old: str, new: str) -> None:
    problems = edit_problems(ALLOCATED, ALLOCATED.replace(old, new))
    assert any("owned by automation" in p for p in problems)


@pytest.mark.parametrize("key", ["mcFiles", "mcConfigMap"])
def test_adding_a_ci_key_in_an_edit_is_refused(key: str) -> None:
    problems = edit_problems(ALLOCATED, ALLOCATED + f"{key}: []\n")
    assert any(p.startswith(f"{key} is owned by automation") for p in problems)


def test_changing_cluster_name_would_rename_the_cluster_and_is_refused() -> None:
    current = VALID + "clusterName: herzi\n"
    problems = edit_problems(current, current.replace("clusterName: herzi", "clusterName: other"))
    assert any("clusterName is owned by the file name" in p for p in problems)


def test_an_edit_of_a_file_without_nodepools_needs_no_nodepools() -> None:
    current = "dhcp_values:\n  network: 10.20.44.0\n\nmastertag: 4.16.27-x86_64\n"
    assert edit_problems(current, current.replace("4.16.27", "4.16.28")) == []


def test_an_edit_still_needs_a_valid_mastertag() -> None:
    assert "mastertag is required" in edit_problems(VALID, _without(VALID, "mastertag"))


def test_adding_site_or_mce_in_an_edit_is_refused() -> None:
    problems = edit_problems(VALID, VALID + "site: elsewhere\nmce: other\n")
    assert sum("comes from the file's path" in p for p in problems) == 2


def test_an_edit_that_does_not_parse_reports_why() -> None:
    assert edit_problems(VALID, "a: [\n")


def test_an_edit_of_a_broken_file_is_checked_against_nothing() -> None:
    assert edit_problems("a: [\n", VALID) == []


# ── Reading values ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: Path(p).stem)
def test_every_fixture_cluster_file_parses_and_reads(path: Path) -> None:
    values = read_values(load_values(path.read_text(encoding="utf-8")))
    assert values.mastertag is not None
    assert values.platform in ("agent", "kubevirt")


def test_twelve_fixture_cluster_files_exist() -> None:
    assert len(FIXTURE_FILES) == 12


def test_read_values_picks_out_what_day1_shows() -> None:
    values = read_values(load_values(ALLOCATED + "clusterName: custom\n"))
    assert values.owner == {"merkaz": "1234", "anaf": "56", "mador": "7"}
    assert values.mastertag == "4.18.22-x86_64"
    assert values.platform == "agent"
    assert values.vlan_id == 412
    assert values.dhcp_network == "10.20.99.0"
    assert values.cluster_name == "custom"
    assert values.automation_keys == ("vlanId", "dhcp_values")
    (pool,) = values.nodepools
    assert pool.infra_env_name == "dell-r660-site1-128c-1024gb-5tb"
    assert pool.replicas == 2
    assert pool.allow_deletion is False
    assert pool.configs == ("worker-kubeletconfig-reserved",)
    assert pool.name is None


def test_read_values_is_lenient_about_odd_shapes() -> None:
    values = read_values(
        {
            "owner": "not-a-mapping",
            "nodepool": [
                "not-a-mapping",
                {"replicas": True, "configs": "x", "labels": "y", "nodeLabels": "z"},
                {"configs": [{"name": "a"}, "b", {"other": 1}], "nodeLabels": {"k": "v"}},
            ],
            "dhcp_values": "x",
            "platform": "kubevirt",
        }
    )
    assert values.owner is None
    assert values.dhcp_network is None
    assert values.platform == "kubevirt"
    first, second = values.nodepools
    assert (first.replicas, first.configs, first.allow_deletion, first.node_labels) == (
        None,
        (),
        None,
        {},
    )
    assert second.configs == ("a",)
    assert second.node_labels == {"k": "v"}


def test_read_values_of_a_non_list_nodepool_is_no_nodepools() -> None:
    assert read_values({"nodepool": "x"}).nodepools == ()


def test_describe_for_review_lists_each_nodepool() -> None:
    text = describe_for_review(read_values(load_values(VALID)))
    assert "- mastertag: `4.18.22-x86_64`" in text
    assert "- platform: `agent`" in text
    assert (
        "- nodepool `dell-r660-site1-128c-1024gb-5tb`: InfraEnv "
        "`dell-r660-site1-128c-1024gb-5tb`, 2 replicas, configs: worker-kubeletconfig-reserved"
    ) in text
    sparse = describe_for_review(read_values({"nodepool": [{"name": "zone-a"}]}))
    assert "- mastertag: `(none)`" in sparse
    assert "nodepool `zone-a`: InfraEnv `None`, 1 replicas, configs: none" in sparse
