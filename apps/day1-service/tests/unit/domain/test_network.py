"""A cluster's network from its file, checked against segments-manager (ADR-0039)."""

from __future__ import annotations

import dataclasses

import pytest

from wingman_day1.domain.network import (
    FileNetwork,
    NetworkView,
    SegmentRecord,
    checked,
    disagreements,
    file_network,
    segment_of,
    unchecked,
    vlan_of,
)

CLUSTER = "ocp4-prep-amit-site2-a"
FILE = FileNetwork(vlan_id=412, segment="10.20.90.0/24")
RECORD = SegmentRecord(
    segment="10.20.90.0/24",
    vlan_id=412,
    epg_name="EPG_site2_HC_412",
    cluster_name=CLUSTER,
    status="Allocated",
    type="HC",
    site="site2",
)


@pytest.mark.parametrize(
    ("network", "segment"),
    [
        ("10.20.90.0", "10.20.90.0/24"),
        (" 10.20.90.0 ", "10.20.90.0/24"),
        ("10.20.90.5", None),
        ("10.20.90", None),
        ("not-an-address", None),
        ("", None),
        (None, None),
    ],
)
def test_the_segment_is_the_files_network_as_a_slash_24(
    network: str | None, segment: str | None
) -> None:
    assert segment_of(network) == segment


@pytest.mark.parametrize(
    ("raw", "vlan"),
    [
        (412, 412),
        ("412", 412),
        (" 412 ", 412),
        (None, None),
        (True, None),
        ("x", None),
        (4.5, None),
    ],
)
def test_the_files_vlan_is_read_as_a_number(raw: object, vlan: int | None) -> None:
    assert vlan_of(raw) == vlan


def test_the_file_network_reads_both_keys() -> None:
    assert file_network(412, "10.20.90.0") == FILE
    assert file_network(None, None) == FileNetwork(None, None)


def test_a_record_that_agrees_adds_only_the_epg() -> None:
    assert checked(FILE, RECORD, cluster=CLUSTER) == NetworkView(
        vlan_id=412, segment="10.20.90.0/24", epg="EPG_site2_HC_412", ledger=RECORD, problems=()
    )


def test_git_wins_on_the_values_shown_whatever_the_ledger_says() -> None:
    other = dataclasses.replace(RECORD, vlan_id=413, cluster_name="ocp4-prod-x-site2")
    view = checked(FILE, other, cluster=CLUSTER)
    assert (view.vlan_id, view.segment) == (412, "10.20.90.0/24")
    assert view.epg == "EPG_site2_HC_412"
    assert len(view.problems) == 2


def test_a_vlan_that_differs_is_a_problem_in_plain_words() -> None:
    other = dataclasses.replace(RECORD, vlan_id=413)
    assert disagreements(FILE, other, cluster=CLUSTER) == (
        "segments-manager has VLAN 413 for this segment; the file has 412",
    )


def test_a_file_without_a_vlan_id_disagrees_with_a_ledger_that_has_one() -> None:
    no_vlan = FileNetwork(vlan_id=None, segment=FILE.segment)
    assert disagreements(no_vlan, RECORD, cluster=CLUSTER) == (
        "segments-manager has VLAN 412 for this segment; the file has no vlanId",
    )


def test_another_cluster_holding_the_segment_is_a_problem() -> None:
    other = dataclasses.replace(RECORD, cluster_name="ocp4-prep-kite-site2")
    assert disagreements(FILE, other, cluster=CLUSTER) == (
        f"segments-manager allocated this segment to ocp4-prep-kite-site2, not to {CLUSTER}",
    )


def test_a_shared_upi_segment_must_list_the_cluster() -> None:
    shared = dataclasses.replace(RECORD, type="UPI", cluster_name=("seed-a", CLUSTER))
    assert disagreements(FILE, shared, cluster=CLUSTER) == ()
    without = dataclasses.replace(shared, cluster_name=("seed-a", "seed-b"))
    assert disagreements(FILE, without, cluster=CLUSTER) == (
        f"segments-manager shares this segment among seed-a, seed-b, not with {CLUSTER}",
    )


def test_a_segment_that_is_not_allocated_says_so_once() -> None:
    free = dataclasses.replace(RECORD, status="Available", cluster_name=None, type=None)
    assert disagreements(FILE, free, cluster=CLUSTER) == (
        "segments-manager marks this segment Available, not Allocated",
    )
    unknown = dataclasses.replace(free, status=None)
    assert disagreements(FILE, unknown, cluster=CLUSTER) == (
        "segments-manager gives this segment no status, not Allocated",
    )


def test_an_allocated_segment_held_by_nobody_is_a_problem() -> None:
    nobody = dataclasses.replace(RECORD, cluster_name=None)
    assert disagreements(FILE, nobody, cluster=CLUSTER) == (
        "segments-manager allocated this segment to no cluster",
    )


def test_a_segment_segments_manager_does_not_have_is_a_problem() -> None:
    view = checked(FILE, None, cluster=CLUSTER)
    assert (view.epg, view.ledger) == (None, None)
    assert view.problems == ("segments-manager has no segment 10.20.90.0/24",)


def test_the_cluster_name_is_compared_exactly_with_the_file_stem() -> None:
    other = dataclasses.replace(RECORD, cluster_name="prep-amit-site2-a")
    assert disagreements(FILE, other, cluster=CLUSTER), "the chart's clusterName is not the stem"


def test_a_file_without_a_segment_has_nothing_to_check() -> None:
    assert disagreements(FileNetwork(None, None), RECORD, cluster=CLUSTER) == ()


def test_unchecked_is_the_file_alone_with_the_error_if_any() -> None:
    assert unchecked(FILE) == NetworkView(vlan_id=412, segment="10.20.90.0/24")
    failed = unchecked(FILE, ledger_error="SegmentsManagerUnavailable: answered 503")
    assert (failed.epg, failed.ledger, failed.problems) == (None, None, ())
    assert failed.ledger_error == "SegmentsManagerUnavailable: answered 503"
