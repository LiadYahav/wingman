"""A segment's holders, joined to the day1 repo's cluster files (ADR-0047)."""

from __future__ import annotations

import dataclasses

from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.segments import Holder, holder_names, holders_of, refs_by_stem, unlinked

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
