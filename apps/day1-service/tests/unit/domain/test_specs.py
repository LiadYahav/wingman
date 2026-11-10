"""Cluster specs: the legacy document shape, presets and locks, and strict validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.errors import InvalidSpecError
from wingman_day1.domain.locks import InputPath, Lock
from wingman_day1.domain.machine_configs import MachineConfigCatalog, flavor_config_problems
from wingman_day1.domain.specs import (
    ClusterSpec,
    dump_spec,
    parse_spec,
    rule_problems,
    validate_spec,
    with_template,
)

SPECS_DIR = default_fixture_root() / "wingman" / "cluster-specs" / "specs"
FIXTURE_SPECS = sorted(SPECS_DIR.glob("*.yaml"))


def _document(**spec: object) -> dict[str, object]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": "my-spec", "version": "1.2.0"},
        "spec": spec or {"day1": {}, "day2": {}},
    }


@pytest.mark.parametrize("path", FIXTURE_SPECS, ids=lambda p: Path(p).stem)
def test_every_fixture_spec_parses(path: Path) -> None:
    spec = parse_spec(path.read_text(encoding="utf-8"), expected_name=path.stem)
    assert spec.metadata.name == path.stem
    assert spec.spec.day1.template == ""


def test_agent_standard_asks_for_its_addon() -> None:
    spec = parse_spec((SPECS_DIR / "agent-standard.yaml").read_text(encoding="utf-8"))
    assert [str(a.key) for a in spec.spec.day2.addons] == ["redbull/cluster-roles"]
    assert spec.spec.day1.structure == {"nodepools": [{"configs": [{}]}, {"configs": [{}]}]}


def test_a_spec_whose_name_differs_from_its_file_is_refused() -> None:
    content = (SPECS_DIR / "agent-single.yaml").read_text(encoding="utf-8")
    with pytest.raises(InvalidSpecError) as caught:
        parse_spec(content, expected_name="other")
    assert "other.yaml" in caught.value.problems[0]


@pytest.mark.parametrize("content", ["a: [\n", "- a list\n", "just text\n"])
def test_a_spec_that_is_not_a_yaml_mapping_is_refused(content: str) -> None:
    with pytest.raises(InvalidSpecError):
        parse_spec(content)


def test_a_spec_file_that_breaks_the_schema_lists_every_problem() -> None:
    with pytest.raises(InvalidSpecError) as caught:
        parse_spec("metadata:\n  name: Bad Name\n  version: '1 0'\nextra: 1\n")
    problems = " ".join(caught.value.problems)
    assert "metadata.name" in problems
    assert "metadata.version" in problems
    assert "extra" in problems


def test_unknown_keys_are_refused_anywhere_in_the_document() -> None:
    for document in (
        {**_document(), "extra": 1},
        _document(day1={"variabels": []}),
        _document(day2={"addons": [{"team": "t", "name": "n", "version": "v", "typo": 1}]}),
    ):
        with pytest.raises(InvalidSpecError) as caught:
            validate_spec(document)
        assert caught.value.problems


@pytest.mark.parametrize("name", ["My-Spec", "spec_1", "-spec", "a" * 64, "a/b"])
def test_a_spec_name_must_be_a_dns_label(name: str) -> None:
    document = _document()
    document["metadata"] = {"name": name}
    with pytest.raises(InvalidSpecError) as caught:
        validate_spec(document)
    assert any("metadata.name" in p for p in caught.value.problems)


@pytest.mark.parametrize("version", ["", "1 0", "v1/2", "-1"])
def test_a_spec_version_must_be_one_word(version: str) -> None:
    document = _document()
    document["metadata"] = {"name": "my-spec", "version": version}
    with pytest.raises(InvalidSpecError):
        validate_spec(document)


def test_an_addon_listed_twice_is_refused() -> None:
    addon = {"team": "redbull", "name": "cluster-roles", "version": "main"}
    with pytest.raises(InvalidSpecError) as caught:
        validate_spec(_document(day2={"addons": [addon, addon]}))
    assert any("redbull/cluster-roles" in p for p in caught.value.problems)


def test_addon_team_and_name_must_be_labels() -> None:
    with pytest.raises(InvalidSpecError):
        validate_spec(_document(day2={"addons": [{"team": "Red", "name": "x", "version": "1"}]}))


def test_the_api_version_and_kind_are_fixed() -> None:
    with pytest.raises(InvalidSpecError):
        validate_spec({**_document(), "kind": "Other"})


def test_requested_addons_carry_the_override_values_by_team_and_name() -> None:
    spec = validate_spec(
        _document(
            day2={
                "addons": [
                    {"team": "redbull", "name": "cluster-roles", "version": "main"},
                    {"team": "lynx", "name": "backup", "version": "1.0.0"},
                ]
            }
        )
    )
    assert spec.requested_addons({"lynx/backup": {"schedule": "daily"}}) == [
        RequestedAddon("redbull", "cluster-roles", "main", {}),
        RequestedAddon("lynx", "backup", "1.0.0", {"schedule": "daily"}),
    ]


def test_overrides_for_an_addon_the_spec_does_not_list_are_refused() -> None:
    spec = validate_spec(_document())
    with pytest.raises(InvalidSpecError) as caught:
        spec.requested_addons({"redbull/unknown": {}})
    assert "redbull/unknown" in caught.value.problems[0]


def test_dump_never_stores_the_template_and_round_trips() -> None:
    spec = validate_spec(
        _document(day1={"template": "{{ x }}", "values": {"nodepools": [{"replicas": 3}]}})
    )
    content = dump_spec(spec)
    assert "template" not in yaml.safe_load(content)["spec"]["day1"]
    again = parse_spec(content, expected_name="my-spec")
    assert again.spec.day1.values == {"nodepools": [{"replicas": 3}]}
    assert again == with_template(spec, "")


def test_with_template_fills_the_shared_template_without_touching_the_spec() -> None:
    spec = validate_spec(_document())
    filled = with_template(spec, "owner: {{ x }}\n")
    assert filled.spec.day1.template == "owner: {{ x }}\n"
    assert spec.spec.day1.template == ""
    assert filled.metadata == spec.metadata


def test_a_minimal_spec_gets_empty_day1_and_day2() -> None:
    spec = ClusterSpec.model_validate({"metadata": {"name": "tiny"}})
    assert spec.metadata.version == "1.0.0"
    assert spec.spec.day1.values == {}
    assert spec.spec.day2.addons == []


# ── Locks (ADR-0026) ─────────────────────────────────────────────────────────


def test_the_legacy_immutable_paths_are_read_as_locked_paths() -> None:
    spec = validate_spec(_document(day1={"immutable_paths": ["platform"]}))
    assert spec.spec.day1.locked_paths == ["platform"]
    stored = yaml.safe_load(dump_spec(spec))["spec"]["day1"]
    assert stored["locked_paths"] == ["platform"]
    assert "immutable_paths" not in stored


def test_both_names_at_once_are_refused() -> None:
    with pytest.raises(InvalidSpecError) as caught:
        validate_spec(_document(day1={"immutable_paths": [], "locked_paths": []}))
    assert "immutable_paths is the old name of locked_paths" in caught.value.problems[0]


def test_a_stored_spec_with_a_lock_that_fixes_nothing_loads_and_is_not_enforced() -> None:
    content = yaml.safe_dump(
        _document(
            day1={
                "immutable_paths": ["cluster_name", "platform", "owner_merkaz"],
                "values": {"owner_merkaz": "1234"},
            }
        )
    )
    spec = parse_spec(content)
    assert spec.locks() == (Lock(InputPath.parse("owner_merkaz"), "1234"),)
    assert [p.split(" ")[1] for p in rule_problems(spec)] == ["cluster_name", "platform"]


def test_rule_problems_cover_values_owners_and_locks() -> None:
    spec = validate_spec(
        _document(
            day1={
                "values": {"owner_anaf": "a\nb", "owner_mador": "x"},
                "locked_paths": ["nodepools[0].replicas"],
            }
        )
    )
    problems = rule_problems(spec)
    assert len(problems) == 4
    assert problems[0].startswith("owner_anaf: a value must be one line")
    assert problems[1].startswith("owner_anaf: must be a number")
    assert problems[2].startswith("owner_mador: must be a number")
    assert problems[3].startswith("locked_paths: nodepools[0].replicas is locked but")


def test_presets_put_the_values_over_legacy_variable_defaults() -> None:
    spec = validate_spec(
        _document(
            day1={
                "variables": [
                    {"name": "platform", "type": "string", "default": "agent"},
                    {"name": "owner_mador", "type": "string", "default": "7"},
                    {"name": "x", "type": "string"},
                ],
                "values": {"platform": "kubevirt"},
            }
        )
    )
    assert spec.presets() == {"platform": "kubevirt", "owner_mador": "7"}


@pytest.mark.parametrize("path", FIXTURE_SPECS, ids=lambda p: Path(p).stem)
def test_every_fixture_spec_meets_the_flavor_rules(path: Path) -> None:
    mc_files = default_fixture_root() / "gitops-day1" / "platform-config" / "mc-files"
    catalog = MachineConfigCatalog.from_files(
        RepoPath(f"mc-files/{f.relative_to(mc_files).as_posix()}")
        for f in mc_files.rglob("*")
        if f.is_file()
    )
    spec = parse_spec(path.read_text(encoding="utf-8"), expected_name=path.stem)
    assert rule_problems(spec) == []
    assert flavor_config_problems(spec.spec.day1.values, catalog) == []


def test_the_dell_fixture_flavor_locks_its_first_nodepools_configs() -> None:
    spec = parse_spec((SPECS_DIR / "agent-dell.yaml").read_text(encoding="utf-8"))
    (lock,) = spec.locks()
    assert str(lock.path) == "nodepools[0].configs"
    assert lock.value == [
        {"name": "nm-conf", "hardware": "dell"},
        {"name": "workers-chrony-configuration"},
        {"name": "nic-ring-buffer"},
    ]
