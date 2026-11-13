"""A segment's holders and mismatches, from the day1 repo's cluster files (ADR-0047)."""

from __future__ import annotations

import dataclasses

from wingman_day1.domain.network import FileNetwork, SegmentRecord
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.segments import (
    Holder,
    Mismatch,
    SegmentRow,
    holder_names,
    holders_of,
    refs_by_stem,
    unlinked,
    with_mismatches,
)

HERZI = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")
RECORD = SegmentRecord(
    segment="10.20.44.0/24",
    vlan_id=1418,
    epg_name="EPG_site1_HC_1418",
    cluster_name=HERZI.name,
    status="Allocated",
    type="HC",
    site="site1",
)


def test_holder_names_are_one_a_shared_list_or_none() -> None:
    assert holder_names("ocp4-x") == ("ocp4-x",)
    assert holder_names(("ocp4-upi-a", "ocp4-upi-b")) == ("ocp4-upi-a", "ocp4-upi-b")
    assert holder_names(None) == ()


def test_a_holder_with_one_cluster_file_links_to_it() -> None:
    refs = refs_by_stem([HERZI, ClusterRef("site2", "ocp4-prep-mce-site2-a", "ocp4-prep-amit")])
    assert holders_of(RECORD, refs) == (Holder(HERZI.name, HERZI),)


def test_an_mce_a_upi_cluster_and_an_unknown_name_are_names_only() -> None:
    refs = refs_by_stem([HERZI])
    mce = dataclasses.replace(RECORD, type="INVENTORY", cluster_name="ocp4-prod-mce-site1-a")
    assert holders_of(mce, refs) == (Holder("ocp4-prod-mce-site1-a", None),)
    upi = dataclasses.replace(RECORD, type="UPI", cluster_name=("ocp4-upi-a", HERZI.name))
    assert holders_of(upi, refs) == (Holder("ocp4-upi-a", None), Holder(HERZI.name, HERZI))
    free = dataclasses.replace(RECORD, status="Available", cluster_name=None, type=None)
    assert holders_of(free, refs) == ()


def test_a_name_two_cluster_files_share_is_not_linked() -> None:
    twin = ClusterRef("site1", "ocp4-prod-mce-site1-b", HERZI.name)
    assert holders_of(RECORD, refs_by_stem([HERZI, twin])) == (Holder(HERZI.name, None),)


def test_unlinked_keeps_every_name() -> None:
    upi = dataclasses.replace(RECORD, cluster_name=("ocp4-upi-a", "ocp4-upi-b"))
    assert unlinked(upi).holders == (Holder("ocp4-upi-a", None), Holder("ocp4-upi-b", None))


# ── Mismatches: ADR-0039's checks from the segment's side (stage 5 of the area) ──

AMIT = ClusterRef("site2", "ocp4-prep-mce-site2-a", "ocp4-prep-amit-site2-a")


def checked(record: SegmentRecord, files: dict[ClusterRef, FileNetwork]) -> list[Mismatch]:
    """The record's mismatches against ``files``, its holders joined to them."""
    row = SegmentRow(record, holders_of(record, refs_by_stem(files)))
    (out,) = with_mismatches([row], files)
    return list(out.mismatches)


def test_a_file_and_segments_manager_that_agree_have_no_mismatch() -> None:
    files = {HERZI: FileNetwork(vlan_id=1418, segment=RECORD.segment)}
    assert checked(RECORD, files) == []


def test_another_vlan_is_adr_0039s_sentence_word_for_word() -> None:
    files = {HERZI: FileNetwork(vlan_id=1410, segment=RECORD.segment)}
    assert checked(RECORD, files) == [
        Mismatch(HERZI, "segments-manager has VLAN 1418 for this segment; the file has 1410")
    ]


def test_a_file_naming_a_segment_another_cluster_holds() -> None:
    files = {
        HERZI: FileNetwork(vlan_id=1418, segment=RECORD.segment),
        AMIT: FileNetwork(vlan_id=1418, segment=RECORD.segment),
    }
    assert checked(RECORD, files) == [
        Mismatch(
            AMIT,
            f"segments-manager allocated this segment to {HERZI.name}, not to {AMIT.name}",
        )
    ]


def test_a_file_naming_an_available_segment() -> None:
    free = dataclasses.replace(RECORD, status="Available", cluster_name=None, type=None)
    files = {HERZI: FileNetwork(vlan_id=1418, segment=RECORD.segment)}
    assert checked(free, files) == [
        Mismatch(HERZI, "segments-manager marks this segment Available, not Allocated")
    ]


def test_a_shared_segment_without_the_file_that_names_it() -> None:
    upi = dataclasses.replace(RECORD, type="UPI", cluster_name=("ocp4-upi-a", "ocp4-upi-b"))
    files = {HERZI: FileNetwork(vlan_id=1418, segment=RECORD.segment)}
    assert checked(upi, files) == [
        Mismatch(
            HERZI,
            "segments-manager shares this segment among ocp4-upi-a, ocp4-upi-b, "
            f"not with {HERZI.name}",
        )
    ]


def test_a_holder_whose_file_names_another_segment_or_none() -> None:
    elsewhere = {HERZI: FileNetwork(vlan_id=1418, segment="10.20.99.0/24")}
    assert checked(RECORD, elsewhere) == [
        Mismatch(HERZI, "the file has segment 10.20.99.0/24, not this one")
    ]
    none_yet = {HERZI: FileNetwork(vlan_id=None, segment=None)}
    assert checked(RECORD, none_yet) == [Mismatch(HERZI, "the file has no segment")]


def test_holders_that_are_not_day1_clusters_and_unparsable_files_are_not_checked() -> None:
    mce = dataclasses.replace(RECORD, type="MCE", cluster_name="ocp4-prod-mce-site1-a")
    assert checked(mce, {}) == []
    # A holder whose file does not parse is linked but has no network to compare
    row = SegmentRow(RECORD, (Holder(HERZI.name, HERZI),))
    (out,) = with_mismatches([row], {})
    assert out.mismatches == ()
