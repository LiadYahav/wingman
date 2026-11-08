"""The releases an MCE offers, from upgrade/ladder.yaml and upgrade/mces/<mce>.yaml (ADR-0034)."""

from __future__ import annotations

import pytest

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.openshift_versions import (
    HostedMinors,
    Ladder,
    OpenShiftVersions,
    bare_release,
    missing_ladder,
    missing_mce_rules,
    parse_ladder,
    parse_mce_rules,
    unhostable_problems,
    versions_for,
)

UPGRADE = default_fixture_root() / "gitops-day1/platform-config/upgrade"

LADDER = """\
schemaVersion: 1
ladder:
  - { version: 4.16.55, must: true }
  - { version: 4.17.58, must: true }
  - { version: 4.18.56, must: true, dataPlane: required }
  - { version: 4.18.60 }
"""


def rules(*minors: str) -> str:
    listed = ", ".join(minors)
    return f"mce:\n  version: 2.8.2\n  supportedHostedVersions: [{listed}]\n"


def test_the_fixture_ladder_and_mce_files_parse_cleanly() -> None:
    ladder = parse_ladder((UPGRADE / "ladder.yaml").read_text())
    assert ladder.problems == ()
    assert ladder.releases[0] == "4.15.41"
    for path in sorted((UPGRADE / "mces").glob("*.yaml")):
        hosted = parse_mce_rules(path.stem, path.read_text())
        assert hosted.problems == (), path.name
        assert hosted.minors, path.name


def test_an_mce_offers_the_rungs_of_its_minors_newest_first() -> None:
    offered = versions_for(
        "m", parse_ladder(LADDER), parse_mce_rules("m", rules('"4.18"', '"4.16"'))
    )
    assert offered == OpenShiftVersions("m", ("4.18.60", "4.18.56", "4.16.55"), ())


def test_minors_the_ladder_has_no_rung_for_add_nothing() -> None:
    hosted = parse_mce_rules("m", rules('"4.22"', '"4.17"', '"4.14"'))
    assert versions_for("m", parse_ladder(LADDER), hosted).versions == ("4.17.58",)


def test_no_overlap_says_so() -> None:
    offered = versions_for("m", parse_ladder(LADDER), parse_mce_rules("m", rules('"4.22"')))
    assert offered.versions == ()
    assert offered.problems == (
        "No release in upgrade/ladder.yaml is in a minor MCE m can host (4.22). "
        "Add a rung for one of them.",
    )


def test_a_missing_mce_file_offers_nothing_never_the_whole_ladder() -> None:
    offered = versions_for(
        "ocp4-prod-mce-site1-a", parse_ladder(LADDER), missing_mce_rules("ocp4-prod-mce-site1-a")
    )
    assert offered.versions == ()
    assert offered.problems == (
        "MCE ocp4-prod-mce-site1-a has no upgrade/mces/ocp4-prod-mce-site1-a.yaml in the day1 "
        "repo, so Wingman can't tell which OpenShift versions it can host. "
        "Add it (see upgrade/README.md).",
    )


def test_a_missing_ladder_offers_nothing() -> None:
    offered = versions_for("m", missing_ladder(), parse_mce_rules("m", rules('"4.18"')))
    assert offered.versions == ()
    assert "has no upgrade/ladder.yaml" in offered.problems[0]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("ladder: [", "upgrade/ladder.yaml is not valid YAML at line"),
        ("- 4.18.56\n", "upgrade/ladder.yaml is not a YAML mapping"),
        ("schemaVersion: 1\nladder: []\n", "has no ladder: list"),
        ("schemaVersion: 1\n", "has no ladder: list"),
    ],
)
def test_a_broken_ladder_is_a_problem_and_no_release(text: str, problem: str) -> None:
    ladder = parse_ladder(text)
    assert ladder.releases == ()
    assert len(ladder.problems) == 1
    assert problem in ladder.problems[0]


@pytest.mark.parametrize("header", ["", "schemaVersion: 1\n", "schemaVersion: 2\n"])
def test_the_rungs_are_read_whatever_the_schema_version(header: str) -> None:
    # Production's ladder has no schemaVersion; Wingman reads only ladder[].version.
    ladder = parse_ladder(f"{header}ladder:\n  - {{ version: 4.18.56 }}\n")
    assert (ladder.releases, ladder.problems) == (("4.18.56",), ())


def test_a_rung_that_breaks_the_schema_is_left_out_and_named() -> None:
    ladder = parse_ladder(
        "schemaVersion: 1\nladder:\n"
        "  - { version: 4.18.56 }\n"
        "  - { version: 4.19.53-x86_64 }\n"
        "  - { version: 4.20 }\n"
        "  - { must: true }\n"
        "  - { version: 4.18.56 }\n"
    )
    assert ladder.releases == ("4.18.56",)
    assert ladder.problems == (
        "upgrade/ladder.yaml ladder[1].version '4.19.53-x86_64' is not a bare release like "
        "4.20.44 (no -x86_64)",
        "upgrade/ladder.yaml ladder[2].version 4.2 is not a bare release like 4.20.44 (no -x86_64)",
        "upgrade/ladder.yaml ladder[3] has no version",
    )


def test_an_unquoted_minor_is_a_float_and_is_named_not_guessed() -> None:
    hosted = parse_mce_rules("m", rules('"4.18"', "4.20", '"4.2x"'))
    assert hosted.minors == ("4.18",)
    assert hosted.problems == (
        "upgrade/mces/m.yaml mce.supportedHostedVersions[1] is the number 4.2; "
        'quote it, as in "4.20"',
        "upgrade/mces/m.yaml mce.supportedHostedVersions[2] '4.2x' is not a minor like \"4.22\"",
    )


@pytest.mark.parametrize(
    "text", ["maxConcurrentControlPlanes: 1\n", "mce: {version: 2.8.2}\n", rules(), "mce: []\n"]
)
def test_an_mce_file_without_minors_offers_nothing(text: str) -> None:
    hosted = parse_mce_rules("m", text)
    assert hosted == HostedMinors(
        (), ("upgrade/mces/m.yaml has no mce.supportedHostedVersions list",)
    )


def test_the_problems_of_both_files_are_kept() -> None:
    ladder = Ladder(("4.18.56",), ("ladder problem",))
    hosted = HostedMinors(("4.18",), ("mce problem",))
    assert versions_for("m", ladder, hosted).problems == ("ladder problem", "mce problem")


def test_a_release_is_compared_without_its_architecture_suffix() -> None:
    offered = OpenShiftVersions("m", ("4.18.56", "4.16.55"))
    assert bare_release(" 4.18.56-x86_64 ") == "4.18.56"
    assert unhostable_problems("4.18.56-x86_64", offered) == []
    assert unhostable_problems("4.18.56", offered) == []
    assert unhostable_problems("4.19.53-x86_64", offered) == [
        "MCE m can host 4.18.56, 4.16.55; 4.19.53 is not one of them"
    ]


def test_an_mce_that_offers_nothing_refuses_every_release_with_the_reason() -> None:
    offered = OpenShiftVersions("m", (), ("MCE m has no upgrade/mces/m.yaml ...",))
    assert unhostable_problems("4.18.56", offered) == [
        "MCE m offers no OpenShift version",
        "MCE m has no upgrade/mces/m.yaml ...",
    ]
