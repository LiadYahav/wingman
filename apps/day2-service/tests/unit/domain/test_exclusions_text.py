"""Editing exclusions.yaml in place: one chart's list changes, every comment stays (ADR-0053)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.exclusions import platform_exclusions, set_excluded

PATH = "defaults/mces/exclusions.yaml"
# The fixture's file: 40 lines of comments, then one entry.
FIXTURE = (default_fixture_root() / "sigs" / "redbull" / PATH).read_text(encoding="utf-8")

LISTS = """\
# Who skips what, and why.
exclusions:
  # The prep MCE runs its own DHCP.
  dhcp-api-token:
    - ocp4-prep-mce-site1-a  # until 2026-12
    # the lab MCE is being rebuilt
    - ocp4-test-mce-lab
  example-chart: [ocp4-prod-mce-site1-a]  # flow style is fine too
"""


def comments(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]


def names(text: str | None) -> dict[str, tuple[str, ...]]:
    found = platform_exclusions(yaml.safe_load(text or "") if text else None)
    assert found is not None
    return dict(found.by_chart)


def test_adding_a_name_appends_one_line_and_keeps_the_40_comment_lines() -> None:
    out = set_excluded(
        FIXTURE, "dhcp-api-token", ["ocp4-prep-mce-site1-a", "ocp4-prod-mce-site1-a"], path=PATH
    )
    assert out is not None
    assert out == FIXTURE.replace(
        "    - ocp4-prep-mce-site1-a\n",
        "    - ocp4-prep-mce-site1-a\n    - ocp4-prod-mce-site1-a\n",
    )
    assert comments(out) == comments(FIXTURE) and len(comments(FIXTURE)) > 30


def test_removing_the_last_name_leaves_an_empty_mapping_and_every_comment() -> None:
    out = set_excluded(FIXTURE, "dhcp-api-token", [], path=PATH)
    assert out is not None
    assert out.endswith("exclusions: {}\n") and comments(out) == comments(FIXTURE)
    assert names(out) == {}


def test_a_new_chart_goes_after_the_last_one_in_the_files_style() -> None:
    out = set_excluded(FIXTURE, "example-chart", ["ocp4-prep-mce-site1-a"], path=PATH)
    assert out is not None and out.startswith(FIXTURE)
    assert out[len(FIXTURE) :] == "  example-chart:\n    - ocp4-prep-mce-site1-a\n"


def test_an_absent_file_is_created_and_stays_absent_when_nothing_is_excluded() -> None:
    assert set_excluded(None, "kyverno", ["a", "b"], path=PATH) == (
        "exclusions:\n  kyverno:\n    - a\n    - b\n"
    )
    assert set_excluded(None, "kyverno", [], path=PATH) is None


def test_comments_inside_and_beside_a_list_stay_with_the_names_they_sit_by() -> None:
    out = set_excluded(LISTS, "dhcp-api-token", ["ocp4-prep-mce-site1-a", "ocp4-x"], path=PATH)
    assert out == LISTS.replace("    - ocp4-test-mce-lab\n", "    - ocp4-x\n")
    assert comments(out) == comments(LISTS)
    # A removed name takes its own line, with its own trailing comment, and no comment line.
    out = set_excluded(LISTS, "dhcp-api-token", ["ocp4-test-mce-lab"], path=PATH)
    assert out is not None and "until 2026-12" not in out and comments(out) == comments(LISTS)
    assert names(out)["dhcp-api-token"] == ("ocp4-test-mce-lab",)


def test_a_flow_list_is_edited_on_its_line_and_keeps_its_comment() -> None:
    out = set_excluded(
        LISTS, "example-chart", ["ocp4-prod-mce-site1-a", "ocp4-prep-mce-site1-a"], path=PATH
    )
    assert out == LISTS.replace(
        "[ocp4-prod-mce-site1-a]  #", "[ocp4-prod-mce-site1-a, ocp4-prep-mce-site1-a]  #"
    )
    out = set_excluded(LISTS, "example-chart", [], path=PATH)
    assert out is not None and "example-chart" not in out and "flow style" not in out
    assert names(out) == {"dhcp-api-token": ("ocp4-prep-mce-site1-a", "ocp4-test-mce-lab")}


def test_files_without_entries_get_the_block_and_keep_their_comments() -> None:
    assert set_excluded("# none yet\n{}\n", "a", ["x"], path=PATH) == (
        "# none yet\nexclusions:\n  a:\n    - x\n"
    )
    assert set_excluded("exclusions: {}  # none yet\n", "a", ["x"], path=PATH) == (
        "exclusions:  # none yet\n  a:\n    - x\n"
    )
    assert set_excluded("# only a header\n", "a", ["x"], path=PATH) == (
        "# only a header\nexclusions:\n  a:\n    - x\n"
    )


def test_an_unchanged_list_gives_back_the_same_text() -> None:
    assert set_excluded(FIXTURE, "dhcp-api-token", ["ocp4-prep-mce-site1-a"], path=PATH) == FIXTURE


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("exclusions: {a: [x]}\n", "flow style"),
        ("exclusions:\n  a:\n\t- x\n", "tabs"),
        ("exclusions:\n  a:\n    - name: x\n", "not a `- <name>` line"),
        ("exclusions:\n  a:\n    - x\n---\nexclusions: {}\n", "document marker"),
        ("exclusions:\n  a: x\n", "not a list of names"),
        ("- x\n", "not a mapping"),
        ("exclusions: [a]\n", "not a mapping of charts"),
    ],
)
def test_a_layout_it_cannot_edit_exactly_is_refused_with_the_reason(text: str, reason: str) -> None:
    with pytest.raises(ChangeRefusedError) as raised:
        set_excluded(text, "a", ["y"], path=PATH)
    assert raised.value.details["rule"] == "exclusions-layout"
    assert reason in str(raised.value.details["reason"])


def test_the_fixture_is_the_one_the_tests_read() -> None:
    assert Path(default_fixture_root(), "sigs", "redbull", PATH).is_file()
    assert names(FIXTURE) == {"dhcp-api-token": ("ocp4-prep-mce-site1-a",)}
