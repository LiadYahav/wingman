"""The placement rule (ADR-0050): every check, every ranking step, the unknowns, admission."""

from __future__ import annotations

from dataclasses import replace

import pytest

from wingman_day1.domain.errors import InvalidInputError, PlacementChangedError
from wingman_day1.domain.mce_capacity import (
    ExcludedNodes,
    FreePods,
    NodeTypeSupply,
    SpareServers,
)
from wingman_day1.domain.names import Env
from wingman_day1.domain.openshift_versions import OpenShiftVersions
from wingman_day1.domain.placement import (
    LIVE_READS_OFF,
    MAX_REASON,
    Admission,
    Candidate,
    Check,
    Choice,
    Decision,
    McePicture,
    PlacementInputs,
    Status,
    Step,
    admit,
    describe_placement,
    fold_reason,
    place,
)

A, B, C = (f"ocp4-prod-mce-site1-{x}" for x in "abc")
VERSIONS = ("4.18.22", "4.17.30", "4.16.27")
INPUTS = PlacementInputs(
    site="site1", env=Env.PROD, version="4.18.22", owner="7", flavor="rcs", min_free_pods=70
)


def pods(free: int) -> FreePods:
    return FreePods(allocatable=500, used=500 - free, nodes_counted=2, excluded=ExcludedNodes(3))


def picture(mce: str, **changes: object) -> McePicture:
    base = McePicture(
        mce=mce,
        versions=OpenShiftVersions(mce, VERSIONS),
        clusters=3,
        open_creates=0,
        owner_clusters=1,
        spare=SpareServers(total=4, usable=2),
        spare_detail=None,
        pods=pods(200),
    )
    return replace(base, **changes)


def statuses(candidate: Candidate) -> dict[Check, Status]:
    return {c.check: c.status for c in candidate.checks}


# ── The checks ───────────────────────────────────────────────────────────────


def test_a_candidate_that_passes_every_check_is_offered() -> None:
    placement = place(INPUTS, [picture(A)])
    (only,) = placement.candidates
    assert statuses(only) == dict.fromkeys(Check, Status.PASS)
    assert (only.eligible, only.rank, only.picked, placement.pick) == (True, 1, True, A)
    assert placement.why == f"{A} is the only prod MCE at site1 that passes every check."
    assert placement.problems == ()


def test_an_mce_that_does_not_host_the_version_is_not_offered() -> None:
    older = OpenShiftVersions(B, ("4.17.30", "4.16.27"))
    placement = place(INPUTS, [picture(A), picture(B, versions=older, clusters=0)])
    candidate = placement.candidate(B)
    assert candidate is not None
    assert statuses(candidate)[Check.VERSION] is Status.FAIL
    assert candidate.checks[0].detail == (
        "Does not host OpenShift 4.18.22; it hosts 4.17.30, 4.16.27."
    )
    assert (candidate.eligible, candidate.rank, placement.pick) == (False, None, A)


def test_an_mce_without_its_upgrade_file_hosts_nothing_and_says_why() -> None:
    missing = OpenShiftVersions(A, (), ("MCE X has no upgrade/mces/X.yaml in the day1 repo.",))
    (candidate,) = place(INPUTS, [picture(A, versions=missing)]).candidates
    assert candidate.checks[0].detail == (
        "Hosts no OpenShift version: MCE X has no upgrade/mces/X.yaml in the day1 repo."
    )


def test_too_few_free_pods_is_not_offered() -> None:
    placement = place(INPUTS, [picture(A, pods=pods(69)), picture(B, pods=pods(70))])
    low = placement.candidate(A)
    assert low is not None
    assert statuses(low)[Check.FREE_PODS] is Status.FAIL
    assert low.checks[1].detail == "69 free pods; a new cluster needs 70."
    assert placement.pick == B, "exactly the minimum passes"


def test_an_mce_wingman_cannot_read_is_unknown_and_never_picked() -> None:
    unread = picture(A, pods=None, hub_error="its token may not list nodes and pods (403).")
    placement = place(INPUTS, [unread, picture(B, clusters=9)])
    candidate = placement.candidate(A)
    assert candidate is not None
    assert statuses(candidate) == {
        Check.VERSION: Status.PASS,
        Check.FREE_PODS: Status.UNKNOWN,
        Check.SERVERS: Status.PASS,
        Check.READABLE: Status.FAIL,
    }
    assert "403" in candidate.checks[3].detail
    assert placement.pick == B
    assert candidate.failures == (
        "free_pods: Unknown: Wingman could not read the MCE.",
        "readable: Wingman could not read its nodes and pods: its token may not list nodes "
        "and pods (403).",
    )


def test_without_a_version_every_version_check_is_unknown_and_nothing_is_picked() -> None:
    placement = place(replace(INPUTS, version=None), [picture(A), picture(B)])
    assert {statuses(c)[Check.VERSION] for c in placement.candidates} == {Status.UNKNOWN}
    assert (placement.pick, placement.why) == (None, None)
    assert placement.problems == ("Choose an OpenShift version.",)
    assert placement.versions == VERSIONS


def test_versions_are_every_candidates_newest_first() -> None:
    newer = OpenShiftVersions(B, ("4.19.3", "4.18.22"))
    older = OpenShiftVersions(A, ("4.17.30", "4.16.27"))
    placement = place(INPUTS, [picture(A, versions=older), picture(B, versions=newer)])
    assert placement.versions == ("4.19.3", "4.18.22", "4.17.30", "4.16.27")


def test_no_candidate_at_all_is_a_problem_not_an_error() -> None:
    placement = place(INPUTS, [])
    assert (placement.candidates, placement.pick) == ((), None)
    assert placement.problems == ("site1 has no prod MCE (ocp4-prod-mce-site1-<letter>).",)


def test_when_every_candidate_fails_there_is_no_pick() -> None:
    placement = place(INPUTS, [picture(A, pods=pods(10)), picture(B, pods=pods(5))])
    assert placement.pick is None
    assert placement.problems == ("No prod MCE at site1 passes every check.",)
    assert [c.mce for c in placement.candidates] == [A, B], "the others by name"


# ── The ranking ──────────────────────────────────────────────────────────────


def test_fewest_clusters_of_this_owner_first() -> None:
    placement = place(
        INPUTS,
        [picture(A, owner_clusters=2, clusters=1), picture(B, owner_clusters=0, clusters=8)],
    )
    assert [c.mce for c in placement.candidates] == [B, A]
    assert placement.candidates[1].behind_on is Step.OWNER_CLUSTERS
    assert placement.why == f"{B} has the fewest clusters of owner 7: 0, against 2 on {A}."


def test_then_fewest_clusters() -> None:
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=4)])
    assert placement.pick == B
    assert placement.candidates[1].behind_on is Step.CLUSTERS
    assert placement.why == (
        f"{B} has the fewest clusters: 4, against 5 on {A}; both have 1 of owner 7."
    )


def test_then_most_usable_spare_servers() -> None:
    placement = place(
        INPUTS,
        [
            picture(A, spare=SpareServers(total=9, usable=1)),
            picture(B, spare=SpareServers(total=3, usable=3)),
        ],
    )
    assert placement.pick == B, "usable spare ranks, not the total"
    assert placement.candidates[1].behind_on is Step.SPARE_SERVERS
    assert placement.why == (
        f"{B} has the most usable spare servers: 3, against 1 on {A}; both have 3 clusters, "
        "1 of them owner 7's."
    )


def test_unknown_spare_ranks_after_any_known_count_even_zero() -> None:
    placement = place(
        INPUTS,
        [
            picture(A, spare=None, spare_detail="server-scan names no server for A"),
            picture(B, spare=SpareServers(total=0, usable=0)),
        ],
    )
    assert placement.pick == B
    assert placement.why is not None
    assert "0, against unknown on" in placement.why


def test_then_the_name() -> None:
    placement = place(INPUTS, [picture(B), picture(A)])
    assert [c.mce for c in placement.candidates] == [A, B]
    assert placement.candidates[1].behind_on is Step.NAME
    assert placement.why == f"{A} ties with {B} on every count and comes first by name."


def test_without_an_owner_the_first_step_is_skipped() -> None:
    no_owner = replace(INPUTS, owner=None)
    placement = place(
        no_owner,
        [picture(A, owner_clusters=None, clusters=2), picture(B, owner_clusters=None, clusters=1)],
    )
    assert placement.pick == B
    assert placement.why == f"{B} has the fewest clusters: 1, against 2 on {A}."


def test_ranks_count_only_the_candidates_that_pass() -> None:
    placement = place(
        INPUTS,
        [picture(A, clusters=1, pods=pods(0)), picture(B, clusters=3), picture(C, clusters=2)],
    )
    assert [(c.mce, c.rank) for c in placement.candidates] == [(C, 1), (B, 2), (A, None)]
    assert placement.candidates[1].behind_on is Step.CLUSTERS


# ── Admission at create ──────────────────────────────────────────────────────


def test_the_pick_is_admitted_without_a_reason() -> None:
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=1)])
    admission = admit(placement, B, Choice(pick=B, reason="ignored"))
    assert (admission.chosen, admission.override, admission.reason) == (B, False, None)
    assert admission.decision is Decision.PICKED
    assert admit(placement, B, None).chosen == B


def test_another_mce_that_passes_needs_a_reason() -> None:
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=1)])
    with pytest.raises(InvalidInputError, match=f"Choosing {A} over Wingman's pick {B}") as caught:
        admit(placement, A, Choice(pick=B, reason="   "))
    assert caught.value.problems[0].startswith(f"placement.reason: say why {A} and not {B}")
    admission = admit(placement, A, Choice(pick=B, reason="  near\n their   storage "))
    assert (admission.override, admission.reason) == (True, "near their storage")
    assert admission.decision is Decision.OVERRIDE


def test_an_mce_that_fails_a_check_is_refused_even_with_a_reason() -> None:
    placement = place(INPUTS, [picture(A, pods=pods(10)), picture(B)])
    with pytest.raises(InvalidInputError, match=f"MCE {A} cannot take this cluster") as caught:
        admit(placement, A, Choice(pick=B, reason="I know better"))
    assert caught.value.problems == ("free_pods: 10 free pods; a new cluster needs 70.",)


def test_no_mce_that_passes_refuses_every_create_with_every_reason() -> None:
    placement = place(INPUTS, [picture(A, pods=pods(10)), picture(B, pods=None, hub_error="x.")])
    with pytest.raises(InvalidInputError, match="No prod MCE at site1 can take this cluster") as e:
        admit(placement, A, None)
    assert e.value.problems[0] == "No prod MCE at site1 passes every check."
    assert f"{A}: free_pods: 10 free pods; a new cluster needs 70." in e.value.problems


def test_a_pick_that_moved_since_the_form_showed_it_is_stale() -> None:
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=1)])
    with pytest.raises(PlacementChangedError, match=f"changed from {A} to {B}") as caught:
        admit(placement, A, Choice(pick=A))
    assert caught.value.pick == B


def test_an_mce_that_is_no_candidate_is_refused() -> None:
    placement = place(INPUTS, [picture(A)])
    with pytest.raises(InvalidInputError, match="is not a prod MCE of site site1"):
        admit(placement, "ocp4-prep-mce-site1-a", None)


def test_reasons_are_folded_and_cut() -> None:
    assert fold_reason(" a\tb\n\nc ") == "a b c"
    assert fold_reason(None) == ""
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=1)])
    long = admit(placement, A, Choice(reason="x" * (MAX_REASON + 50)))
    assert long.reason is not None
    assert len(long.reason) == MAX_REASON


# ── Servers of each node type ────────────────────────────────────────────────

DELL, HP = "dell-r650", "hp-gen11"
NEEDS = replace(INPUTS, needs=((DELL, 6), (HP, 2)))


def supply(
    infra_env: str, needed: int, free: int | None, healthy: int | None, **more: object
) -> NodeTypeSupply:
    return NodeTypeSupply(infra_env, needed, free, healthy, **more)  # ty: ignore[invalid-argument-type]


def servers(candidate: Candidate) -> tuple[Status, str]:
    check = next(c for c in candidate.checks if c.check is Check.SERVERS)
    return check.status, check.detail


def test_enough_healthy_free_servers_of_every_type_passes() -> None:
    enough = (supply(DELL, 6, 7, 6), supply(HP, 2, 2, 2))
    (candidate,) = place(NEEDS, [picture(A, node_types=enough)]).candidates
    assert servers(candidate) == (
        Status.PASS,
        "dell-r650: 6 healthy free of 6 needed; hp-gen11: 2 healthy free of 2 needed.",
    )
    assert candidate.picked


def test_one_type_short_fails_the_mce_in_plain_words() -> None:
    short = (supply(DELL, 6, 6, 2), supply(HP, 2, 2, 2))
    placement = place(
        NEEDS,
        [
            picture(A, node_types=short),
            picture(B, clusters=9, node_types=(supply(DELL, 6, 8, 8), supply(HP, 2, 3, 3))),
        ],
    )
    candidate = placement.candidate(A)
    assert candidate is not None
    status, detail = servers(candidate)
    assert status is Status.FAIL
    assert detail.startswith("dell-r650: 2 healthy free of 6 needed;")
    assert placement.pick == B, "the servers check is required, not a ranking step"


def test_too_few_free_agents_fails_even_when_health_is_unknown() -> None:
    (candidate,) = place(NEEDS, [picture(A, node_types=(supply(DELL, 6, 3, None),))]).candidates
    assert servers(candidate)[0] is Status.FAIL


@pytest.mark.parametrize(
    ("node_type", "words"),
    [
        (supply(DELL, 6, None, None), "the MCE's Agents could not be read"),
        (supply(DELL, 6, 8, None), "their health unknown without server-scan"),
        (supply(DELL, 6, 8, 4, not_in_server_scan=2), "2 more free, not in server-scan"),
    ],
)
def test_an_unknown_type_is_unknown_and_never_picked(node_type: NodeTypeSupply, words: str) -> None:
    placement = place(NEEDS, [picture(A, node_types=(node_type, supply(HP, 2, 2, 2)))])
    (candidate,) = placement.candidates
    status, detail = servers(candidate)
    assert (status, placement.pick) == (Status.UNKNOWN, None)
    assert words in detail


def test_a_short_type_beats_an_unknown_one() -> None:
    mixed = (supply(DELL, 6, None, None), supply(HP, 2, 2, 1))
    (candidate,) = place(NEEDS, [picture(A, node_types=mixed)]).candidates
    assert servers(candidate)[0] is Status.FAIL


def test_without_server_scan_free_agents_count_as_they_are() -> None:
    unchecked = (supply(DELL, 6, 6, None, health_checked=False),)
    (candidate,) = place(NEEDS, [picture(A, node_types=unchecked)]).candidates
    assert servers(candidate) == (
        Status.PASS,
        "dell-r650: 6 free of 6 needed, their health not checked (server-scan is not configured).",
    )


def test_no_node_type_named_yet_has_nothing_to_check() -> None:
    (candidate,) = place(INPUTS, [picture(A)]).candidates
    assert servers(candidate) == (Status.PASS, "No nodepool names a node type yet.")


def test_the_agents_read_error_is_said_when_it_makes_the_check_unknown() -> None:
    unread = picture(
        A,
        node_types=(supply(DELL, 6, None, None),),
        agents_error="Its token may not list Agents (403).",
    )
    (candidate,) = place(NEEDS, [unread]).candidates
    assert servers(candidate)[1].endswith("Its token may not list Agents (403).")


# ── Without live MCE reads (ADR-0050's amendment) ────────────────────────────


def unread(mce: str, **changes: object) -> McePicture:
    """A candidate as Wingman sees it with live status off: Git and server-scan only."""
    return picture(mce, pods=None, live=False, **changes)


def test_without_live_reads_the_mce_checks_are_not_checked_and_do_not_block() -> None:
    placement = place(
        replace(INPUTS, needs=((DELL, 6),)), [unread(A, clusters=4), unread(B)], live_reads=False
    )
    assert placement.live_reads is False
    assert placement.pick == B
    for candidate in placement.candidates:
        assert statuses(candidate) == {
            Check.VERSION: Status.PASS,
            Check.FREE_PODS: Status.NOT_CHECKED,
            Check.SERVERS: Status.NOT_CHECKED,
            Check.READABLE: Status.NOT_CHECKED,
        }
        assert candidate.eligible
        assert candidate.failures == ()
        assert candidate.not_checked == (Check.FREE_PODS, Check.SERVERS, Check.READABLE)
        assert {c.detail for c in candidate.checks[1:]} == {LIVE_READS_OFF}


def test_without_live_reads_the_version_still_decides() -> None:
    older = OpenShiftVersions(A, ("4.17.30",))
    placement = place(
        INPUTS, [unread(A, versions=older, clusters=0), unread(B, clusters=9)], live_reads=False
    )
    candidate = placement.candidate(A)
    assert candidate is not None
    assert (candidate.eligible, placement.pick) == (False, B)
    assert candidate.failures == ("version: Does not host OpenShift 4.18.22; it hosts 4.17.30.",), (
        "a not-checked check is not a failure"
    )


def test_not_checked_is_not_unknown_an_unknown_still_blocks() -> None:
    unknown = picture(A, pods=None, hub_error="it did not answer.")
    placement = place(INPUTS, [unknown, unread(B, clusters=9)])
    assert placement.pick == B
    assert statuses(placement.candidates[1])[Check.FREE_PODS] is Status.UNKNOWN


def test_the_description_says_what_was_not_checked() -> None:
    placement = place(INPUTS, [unread(A), unread(B, clusters=9)], live_reads=False)
    text = describe_placement(Admission(placement, A))
    assert (
        "Free pods and servers were **not checked**: live MCE reads are off "
        "(`CLUSTER_STATUS_ENABLED=false`). Wingman decided on the day1 repo and server-scan only."
    ) in text
    assert (
        f"| `{A}` (pick, chosen) | 1 | 3 | 2 (4) | not checked | not checked | "
        "pass (free pods, servers, readable not checked) |"
    ) in text


# ── The merge request's record ───────────────────────────────────────────────


def test_the_description_records_the_pick_the_inputs_and_every_number() -> None:
    placement = place(
        INPUTS,
        [
            picture(A, clusters=5, owner_clusters=2),
            picture(B, clusters=1, owner_clusters=0, spare=None, spare_detail="unknown"),
            picture(C, pods=None, hub_error="it did not answer."),
        ],
    )
    text = describe_placement(Admission(placement, B))
    assert text.splitlines()[:3] == [
        "### MCE placement",
        "",
        f"Wingman picked `{B}`: {B} has the fewest clusters of owner 7: 0, against 2 on {A}.",
    ]
    assert "Site `site1`, prod, OpenShift 4.18.22, owner 7, flavor `rcs`" in text
    assert f"| `{B}` (pick, chosen) | 0 | 1 | unknown | 200 | — | pass |" in text
    assert f"| `{A}` | 2 | 5 | 2 (4) | 200 | — | pass |" in text
    assert f"| `{C}` | 1 | 3 | 2 (4) | unknown | — | not offered: Unknown: Wingman could" in text


def test_the_description_records_the_servers_of_each_type() -> None:
    placement = place(
        NEEDS,
        [
            picture(A, node_types=(supply(DELL, 6, 7, 6), supply(HP, 2, 2, 2))),
            picture(B, node_types=(supply(DELL, 6, 6, 2), supply(HP, 2, None, None))),
        ],
    )
    text = describe_placement(Admission(placement, A))
    assert "a new cluster needs 70 free pods and 6 `dell-r650`, 2 `hp-gen11` servers." in text
    assert (
        f"| `{A}` (pick, chosen) | 1 | 3 | 2 (4) | 200 | dell-r650 6/6, hp-gen11 2/2 | pass |"
        in text
    )
    assert (
        f"| `{B}` | 1 | 3 | 2 (4) | 200 | dell-r650 2/6, hp-gen11 unknown/2 | not offered:" in text
    )


def test_the_description_records_an_override_and_quotes_its_reason_harmlessly() -> None:
    placement = place(INPUTS, [picture(A, clusters=5), picture(B, clusters=1)])
    admission = admit(placement, A, Choice(pick=B, reason="ask @alice | `rm` *now*"))
    text = describe_placement(admission)
    assert (
        f"An admin chose `{A}` over Wingman's pick `{B}`. Reason: `ask @alice | 'rm' *now*`"
    ) in text
    assert f"Wingman's pick: {B} has the fewest clusters" in text
    assert f"| `{A}` (chosen) |" in text
    assert f"| `{B}` (pick) |" in text
