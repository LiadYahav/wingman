"""Editing a cluster file's text: what changes is the edit, everything else is byte for byte."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.cluster_file import Provenance, load_values, read_provenance
from wingman_day1.domain.cluster_text import (
    CI_MARKER,
    SetConfigs,
    SetValue,
    edit_values,
    with_header,
)
from wingman_day1.domain.errors import UneditableFileError
from wingman_day1.domain.locks import InputPath

HOSTED = (
    default_fixture_root()
    / "gitops-day1/platform-config/sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
)
LARK = (HOSTED / "ocp4-prod-lark-site1.yaml").read_text()
HERON = (HOSTED / "ocp4-prod-heron-site1.yaml").read_text()
BASELINE = Provenance("agent-baseline", "1.0.0")


def value(key: str, to: object) -> SetValue:
    return SetValue(InputPath.parse(key), to)


def tail(content: str) -> str:
    return content[content.index(CI_MARKER) :]


# ── The header ───────────────────────────────────────────────────────────────


def test_a_header_goes_first_and_nothing_else_changes() -> None:
    edited = with_header(LARK, BASELINE)
    assert edited == '# specName: "agent-baseline"\n# specVersion: "1.0.0"\n' + LARK
    assert read_provenance(edited) == BASELINE


def test_a_header_replaces_the_old_one_where_it_was() -> None:
    old = (
        "# kept above\n"
        '# specName: "agent-dell"\n'
        "# kept between\n"
        '# specVersion: "0.9.0"\n'
        '# specName: "a-stale-duplicate"\n'
        '# wingmanAddons: [{"team": "t", "name": "n", "version": "1", "override_values": {}}]\n'
        "mastertag: 4.18.22\n"
        '# specName: "not-the-header"\n'
    )
    edited = with_header(old, BASELINE)
    assert edited == (
        "# kept above\n"
        '# specName: "agent-baseline"\n'
        '# specVersion: "1.0.0"\n'
        "# kept between\n"
        "mastertag: 4.18.22\n"
        '# specName: "not-the-header"\n'
    )


def test_a_header_with_requested_addons_reads_back() -> None:
    addons = (RequestedAddon("redbull", "cluster-roles", "main", {"a": 1}),)
    edited = with_header(HERON, Provenance("agent-baseline", "2.0.0", addons))
    assert read_provenance(edited) == Provenance("agent-baseline", "2.0.0", addons)
    assert edited.endswith(HERON)


def test_a_header_keeps_windows_line_endings_and_a_missing_last_newline() -> None:
    old = "# note\r\nmastertag: 4.18.22\r\nnodepool: []"
    edited = with_header(old, BASELINE)
    assert edited == '# specName: "agent-baseline"\r\n# specVersion: "1.0.0"\r\n' + old


def test_a_file_that_starts_with_a_blank_line_gets_the_header_at_the_top() -> None:
    edited = with_header("\n# note\nmastertag: 4.18.22\n", BASELINE)
    assert edited.startswith('# specName: "agent-baseline"\n# specVersion: "1.0.0"\n\n# note\n')


def test_a_header_on_a_file_that_does_not_parse_is_refused() -> None:
    with pytest.raises(UneditableFileError) as caught:
        with_header("x: [\n", BASELINE)
    assert str(caught.value) == "the cluster file does not parse, so Wingman cannot edit it"


# ── Configs ──────────────────────────────────────────────────────────────────

LARK_SYNCED = (
    ("nm-conf-prod-lark-site1-dell", "workers-chrony-configuration", "nic-ring-buffer"),
    ("nm-conf-prod-lark-site1-dell-data", "workers-chrony-configuration", "nic-ring-buffer"),
)


def test_configs_lose_exactly_the_removed_lines_and_gain_new_ones_after_the_last_kept() -> None:
    edited = edit_values(LARK, [SetConfigs(0, LARK_SYNCED[0]), SetConfigs(1, LARK_SYNCED[1])])
    expected = LARK.replace("  - name: worker-kubeletconfig-reserved\n", "", 1).replace(
        "  - name: restored-example-config  # restored by hand, not onboarded yet\n",
        "  - name: nic-ring-buffer\n",
        1,
    )
    # The CI's mcFiles list still names the removed configs: only the human part changes.
    assert edited == expected
    assert tail(edited) == tail(LARK)


def test_the_templates_indented_style_is_kept_for_new_entries() -> None:
    edited = edit_values(
        HERON,
        [
            SetConfigs(
                0,
                (
                    "nm-conf-prod-heron-site1-cisco",
                    "workers-chrony-configuration",
                    "nic-ring-buffer",
                ),
            ),
            SetConfigs(
                1,
                (
                    "nm-conf-prod-heron-site1-dell",
                    "workers-chrony-configuration",
                    "nic-ring-buffer",
                ),
            ),
        ],
    )
    first_before = (
        "      - name: worker-kubeletconfig-reserved\n      - name: workers-chrony-configuration\n"
    )
    first_after = (
        "      - name: workers-chrony-configuration\n"
        "      - name: nm-conf-prod-heron-site1-cisco\n"
        "      - name: nic-ring-buffer\n"
    )
    second_before = (
        "      - name: nm-conf-prod-heron-site1-dell\n"
        "      - name: nm-conf-prod-heron-site1-cisco\n"
    )
    second_after = "      - name: nm-conf-prod-heron-site1-dell\n"
    assert HERON.count(first_before) == HERON.count(second_before) == 1
    assert edited == HERON.replace(second_before, second_after).replace(first_before, first_after)
    assert tail(edited) == tail(HERON)


SMALL = """\
# people's comment
owner:
  merkaz: "1"  # the team's number
  anaf: "2"
mastertag: 4.18.22
nodepool:
  - infraEnvName: a
    replicas: 2  # two for now
    configs:
      # the network one first
      - name: x
      - name: y
        extra: kept
      - name: x
  - infraEnvName: b
    configs: []
vlanId: 7
# === Added by CI ===
mcConfigMap:

  - name: x
    config: CI-OWNED
"""


def test_a_duplicate_entry_is_removed_once_and_a_multi_line_entry_whole() -> None:
    edited = edit_values(SMALL, [SetConfigs(0, ("x",))])
    assert "      - name: y\n        extra: kept\n" not in edited
    assert edited.count("      - name: x\n") == 1
    assert "      # the network one first\n" in edited
    assert tail(edited) == tail(SMALL)


def test_a_kept_entry_keeps_every_key_it_has() -> None:
    edited = edit_values(SMALL, [SetConfigs(0, ("y", "z"))])
    assert "      - name: y\n        extra: kept\n      - name: z\n" in edited
    assert load_values(edited)["nodepool"][0]["configs"] == [  # ty: ignore[not-subscriptable]
        {"name": "y", "extra": "kept"},
        {"name": "z"},
    ]


def test_no_configs_left_is_an_empty_list_and_an_empty_list_can_grow() -> None:
    edited = edit_values(SMALL, [SetConfigs(0, ()), SetConfigs(1, ("p", "q"))])
    # The emptied list's comment survives where it was.
    assert (
        "    configs: []\n      # the network one first\n  - infraEnvName: b\n"
        "    configs:\n      - name: p\n      - name: q\nvlanId: 7\n"
    ) in edited
    assert load_values(edited)["nodepool"] == [
        {"infraEnvName": "a", "replicas": 2, "configs": []},
        {"infraEnvName": "b", "configs": [{"name": "p"}, {"name": "q"}]},
    ]


def test_a_nodepool_without_configs_gets_them_in_the_files_own_style() -> None:
    compact = "nodepool:\n- infraEnvName: a\n  configs:\n  - name: x\n- infraEnvName: b\n"
    edited = edit_values(compact, [SetConfigs(1, ("y",))])
    assert edited == compact + "  configs:\n  - name: y\n"
    indented = "nodepool:\n  - infraEnvName: b\n    replicas: 1\nvlanId: 3\n"
    edited = edit_values(indented, [SetConfigs(0, ("y",)), value("nodepool[0].replicas", 2)])
    assert edited == (
        "nodepool:\n  - infraEnvName: b\n    replicas: 2\n"
        "    configs:\n      - name: y\nvlanId: 3\n"
    )


def test_a_name_yaml_would_read_as_another_type_is_quoted() -> None:
    edited = edit_values("nodepool:\n  - infraEnvName: a\n", [SetConfigs(0, ("true", "1.5"))])
    assert '      - name: "true"\n      - name: "1.5"\n' in edited


# ── Owners, platform, replicas, labels ───────────────────────────────────────


def test_a_replaced_value_keeps_its_lines_comment() -> None:
    edited = edit_values(
        SMALL,
        [
            value("owner.merkaz", "0042"),
            value("nodepool[0].replicas", 3),
            value("owner.mador", "9"),
        ],
    )
    assert '  merkaz: "0042"  # the team\'s number\n' in edited
    assert "    replicas: 3  # two for now\n" in edited
    assert '  anaf: "2"\n  mador: "9"\nmastertag' in edited
    assert tail(edited) == tail(SMALL)


def test_a_file_without_owner_gets_the_owner_block_first() -> None:
    old = "# a note\nmastertag: 4.18.22\n"
    edited = edit_values(old, [value("owner.merkaz", "1"), value("owner.anaf", "2")])
    assert edited == '# a note\nowner:\n  merkaz: "1"\n  anaf: "2"\n\nmastertag: 4.18.22\n'


def test_a_new_key_never_goes_above_the_flavor_header() -> None:
    old = '# specName: "agent-baseline"\n# specVersion: "1.0.0"\nnodepool:\n  - infraEnvName: a\n'
    edited = edit_values(old, [value("owner.merkaz", "1"), value("platform", "kubevirt")])
    assert edited.startswith('# specName: "agent-baseline"\n# specVersion: "1.0.0"\nowner:\n')
    assert read_provenance(edited) == BASELINE


def test_platform_is_replaced_in_place_or_written_above_the_nodepools() -> None:
    edited = edit_values(
        "platform: agent  # for now\nnodepool: []\n", [value("platform", "kubevirt")]
    )
    assert edited == "platform: kubevirt  # for now\nnodepool: []\n"
    old = "mastertag: 4.18.22\n\n# the pools\nnodepool:\n  - infraEnvName: a\n"
    edited = edit_values(old, [value("platform", "kubevirt")])
    assert edited == (
        "mastertag: 4.18.22\n\nplatform: kubevirt\n\n# the pools\nnodepool:\n  - infraEnvName: a\n"
    )


def test_labels_are_written_as_one_json_line_as_the_template_writes_them() -> None:
    edited = edit_values(LARK, [value("nodepool[1].nodeLabels", {"zone": "b"})])
    assert '  nodeLabels: {"zone": "b"}\n\nvlanId: 1412\n' in edited
    edited = edit_values(SMALL, [value("nodepool[1].nodeLabels", {"zone": "c"})])
    assert '    configs: []\n    nodeLabels: {"zone": "c"}\nvlanId: 7\n' in edited


def test_a_key_on_an_items_first_line_is_edited_there() -> None:
    old = "nodepool:\n  - replicas: 1  # one\n    infraEnvName: a\n"
    assert edit_values(old, [value("nodepool[0].replicas", 2)]) == (
        "nodepool:\n  - replicas: 2  # one\n    infraEnvName: a\n"
    )


# ── What the editor refuses ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("content", "edit", "reason"),
    [
        ("x: [\n", value("platform", "kubevirt"), "does not parse"),
        ("nodepool: [{infraEnvName: a}]\n", SetConfigs(0, ("x",)), "nodepool is not a block list"),
        ("mastertag: 1\n", SetConfigs(0, ("x",)), "changed shape"),
        ("nodepool:\n  - infraEnvName: a\n", SetConfigs(1, ("x",)), "changed shape"),
        (
            "nodepool:\n  - infraEnvName: a\n    replicas:\n      3\n",
            value("nodepool[0].replicas", 2),
            "not a one-line value",
        ),
        ('owner: {merkaz: "1"}\n', value("owner.merkaz", "2"), "owner is not a block mapping"),
        ("platform:\n  kubevirt\n", value("platform", "agent"), "not a one-line value"),
        (
            "nodepool:\n  - infraEnvName: a\n    configs: [{name: x, extra: 1}]\n",
            SetConfigs(0, ("x", "y")),
            "could not edit the cluster file safely",
        ),
        (
            # A key below the CI marker is never edited, so a second one would be written.
            f"mastertag: 1\n{CI_MARKER}\nplatform: agent\n",
            value("platform", "kubevirt"),
            "could not edit the cluster file safely",
        ),
        ("mastertag: 1\n", value("mastertag", "2"), "does not edit that key"),
    ],
)
def test_a_layout_the_editor_cannot_handle_is_refused_with_the_reason(
    content: str, edit: Any, reason: str
) -> None:
    with pytest.raises(UneditableFileError) as caught:
        edit_values(content, [edit])
    assert reason in f"{caught.value} {' '.join(caught.value.problems)}"


# ── The guarantee, for any configs ───────────────────────────────────────────

NAMES = st.sampled_from(["a", "b", "c", "nm-conf-x-dell", "legacy"])


@settings(max_examples=150, deadline=None)
@given(
    first=st.lists(NAMES, max_size=5),
    second=st.lists(NAMES, max_size=5),
    want_first=st.lists(NAMES, max_size=5),
    want_second=st.lists(NAMES, max_size=5),
    compact=st.booleans(),
)
def test_any_configs_edit_changes_only_the_configs_and_keeps_the_ci_block(
    first: list[str],
    second: list[str],
    want_first: list[str],
    want_second: list[str],
    compact: bool,
) -> None:
    def entries(names: list[str], column: int) -> str:
        if not names:
            return f"{' ' * column}configs: []\n"
        dash = column if compact else column + 2
        return f"{' ' * column}configs:\n" + "".join(f"{' ' * dash}- name: {n}\n" for n in names)

    lead = "" if compact else "  "
    content = (
        '# hand-written\nowner:\n  merkaz: "1"\nmastertag: 4.18.22\nnodepool:\n'
        f"{lead}- infraEnvName: a  # first\n{entries(first, len(lead) + 2)}\n"
        f"# between\n{lead}- infraEnvName: b\n{lead}  replicas: 1\n{entries(second, len(lead) + 2)}"
        f"vlanId: 9\n{CI_MARKER}\nmcConfigMap:\n- name: a\n  config: X\n"
    )
    edited = edit_values(
        content, [SetConfigs(0, tuple(want_first)), SetConfigs(1, tuple(want_second))]
    )
    pools = load_values(edited)["nodepool"]
    assert sorted(c["name"] for c in pools[0]["configs"]) == sorted(want_first)  # ty: ignore[not-subscriptable]
    assert sorted(c["name"] for c in pools[1]["configs"]) == sorted(want_second)  # ty: ignore[not-subscriptable]
    assert tail(edited) == tail(content)
    for kept in (
        "# hand-written\n",
        '  merkaz: "1"\n',
        "- infraEnvName: a  # first\n",
        "# between\n",
        "vlanId: 9\n",
    ):
        assert kept in edited
    unchanged = [
        line for line in content.splitlines() if "name:" not in line and "configs" not in line
    ]
    assert [
        line for line in edited.splitlines() if "name:" not in line and "configs" not in line
    ] == unchanged
