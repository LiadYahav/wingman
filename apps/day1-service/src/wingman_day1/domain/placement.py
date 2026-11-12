"""Which MCE a new hosted cluster goes to, and why (ADR-0050).

The person gives the site, the environment, the OpenShift version, the
owner (the cluster's mador, ADR-0028) and the flavor with its nodepools. The
**candidates** are the MCEs at the site whose name says that environment
(ADR-0014). Each candidate is **checked**: it hosts the version (ADR-0034),
it has at least the minimum free pods on its workers, it has enough healthy
free servers of every node type the nodepools need, and Wingman could read
it; one that fails a check is not offered, and one whose check is unknown is
never picked. The candidates
that pass are **ranked**: fewest clusters of this owner, then fewest
clusters, then most usable spare servers (an unknown count after every
known one), then name. The first is the pick.

Nothing is reserved and there is no cap: two creates at the same moment can
get the same pick, and both are accepted. An admin may choose another
candidate that passes every check, with a reason; the choice is checked
again at create (:func:`admit`). Everything here is pure: the counts come in
as :class:`McePicture`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from wingman_day1.domain.errors import InvalidInputError, PlacementChangedError
from wingman_day1.domain.mce_capacity import FreePods, NodeTypeSupply, SpareServers, Supply
from wingman_day1.domain.names import Env
from wingman_day1.domain.openshift_versions import OpenShiftVersions, newest_first

MAX_REASON: Final = 500
"""The longest override reason, in characters, after its whitespace is folded."""
_SPACES = re.compile(r"\s+")
_SHOWN_VERSIONS: Final = 6


class Check(StrEnum):
    """A required check; failing one takes a candidate out."""

    VERSION = "version"
    FREE_PODS = "free_pods"
    SERVERS = "servers"
    READABLE = "readable"


class Status(StrEnum):
    """How a check came out."""

    PASS = "pass"  # noqa: S105 - a check's outcome, not a password
    FAIL = "fail"
    UNKNOWN = "unknown"


class Step(StrEnum):
    """A ranking step, in order: where a candidate falls behind the pick."""

    OWNER_CLUSTERS = "owner_clusters"
    CLUSTERS = "clusters"
    SPARE_SERVERS = "spare_servers"
    NAME = "name"


class Decision(StrEnum):
    """How a create came out of the placement check (the metric's ``decision``)."""

    PICKED = "picked"
    OVERRIDE = "override"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check of one candidate, with one sentence on why."""

    check: Check
    status: Status
    detail: str


@dataclass(frozen=True, slots=True)
class PlacementInputs:
    """What the person chose."""

    site: str
    env: Env
    version: str | None
    """A bare release, ``4.18.22``; ``None`` until one is chosen."""
    owner: str | None
    """The mador; ``None`` skips the first ranking step."""
    flavor: str | None
    min_free_pods: int
    needs: tuple[tuple[str, int], ...] = ()
    """Replicas the new cluster needs per node type (InfraEnv), summed, sorted."""


@dataclass(frozen=True, slots=True)
class McePicture:
    """What Wingman read about one candidate."""

    mce: str
    versions: OpenShiftVersions
    clusters: int
    """Cluster files under the MCE, and open merge requests that create one there."""
    open_creates: int
    """Of ``clusters``, the open create merge requests."""
    owner_clusters: int | None
    """Of ``clusters``, the owner's; ``None`` without an owner."""
    spare: SpareServers | None
    """``None`` when unknown; ``spare_detail`` says why."""
    spare_detail: str | None
    pods: FreePods | None
    """``None`` when the MCE could not be read; ``hub_error`` says why."""
    hub_error: str | None = None
    node_types: tuple[NodeTypeSupply, ...] = ()
    """Per need, the MCE's healthy free servers of that type."""
    agents_error: str | None = None
    """Why the MCE's Agents could not be read, when they could not."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """A candidate, its checks, and its place in the ranking when it passes them all."""

    picture: McePicture
    checks: tuple[CheckResult, ...]
    rank: int | None = None
    """1-based among the candidates that pass; ``None`` for the others."""
    behind_on: Step | None = None
    """For a passing candidate that is not the pick: the first step the pick beats it on."""

    @property
    def mce(self) -> str:
        """The MCE folder name."""
        return self.picture.mce

    @property
    def eligible(self) -> bool:
        """Whether every check passes."""
        return all(check.status is Status.PASS for check in self.checks)

    @property
    def picked(self) -> bool:
        """Whether this is Wingman's pick."""
        return self.rank == 1

    @property
    def failures(self) -> tuple[str, ...]:
        """Each check that did not pass, as ``<check>: <why>``."""
        return tuple(f"{c.check}: {c.detail}" for c in self.checks if c.status is not Status.PASS)


@dataclass(frozen=True, slots=True)
class Placement:
    """Every candidate, ranked, and the pick."""

    inputs: PlacementInputs
    candidates: tuple[Candidate, ...]
    """The passing candidates by rank, then the others by name."""
    versions: tuple[str, ...]
    """Every version some candidate hosts, newest first."""
    problems: tuple[str, ...] = ()
    server_scan_error: str | None = None

    @property
    def pick(self) -> str | None:
        """Wingman's pick; ``None`` when no candidate passes every check."""
        first = self.candidates[0] if self.candidates else None
        return first.mce if first is not None and first.picked else None

    @property
    def why(self) -> str | None:
        """One sentence on why the pick won, against the runner-up."""
        eligible = [c for c in self.candidates if c.rank is not None]
        if not eligible:
            return None
        if len(eligible) == 1:
            inputs = self.inputs
            return (
                f"{eligible[0].mce} is the only {inputs.env} MCE at {inputs.site} that passes "
                "every check."
            )
        return _why(eligible[0], eligible[1], self.inputs.owner)

    def candidate(self, mce: str) -> Candidate | None:
        """The candidate ``mce``, if it is one."""
        return next((c for c in self.candidates if c.mce == mce), None)


# ── The checks ───────────────────────────────────────────────────────────────


def version_check(offered: OpenShiftVersions, version: str | None) -> CheckResult:
    """The MCE hosts the version (ADR-0034); unknown until a version is chosen."""
    if version is None:
        return CheckResult(Check.VERSION, Status.UNKNOWN, "Choose an OpenShift version.")
    if version in offered.versions:
        return CheckResult(Check.VERSION, Status.PASS, f"Hosts OpenShift {version}.")
    if not offered.versions:
        why = " ".join(offered.problems) or "Its upgrade file offers none."
        return CheckResult(Check.VERSION, Status.FAIL, f"Hosts no OpenShift version: {why}")
    return CheckResult(
        Check.VERSION,
        Status.FAIL,
        f"Does not host OpenShift {version}; it hosts {_some(offered.versions)}.",
    )


def free_pods_check(pods: FreePods | None, minimum: int) -> CheckResult:
    """At least ``minimum`` free pods; unknown when the MCE could not be read."""
    if pods is None:
        return CheckResult(
            Check.FREE_PODS, Status.UNKNOWN, "Unknown: Wingman could not read the MCE."
        )
    status = Status.PASS if pods.free >= minimum else Status.FAIL
    return CheckResult(
        Check.FREE_PODS, status, f"{pods.free} free pods; a new cluster needs {minimum}."
    )


_SUPPLY_STATUS: Final = {
    Supply.ENOUGH: Status.PASS,
    Supply.SHORT: Status.FAIL,
    Supply.UNKNOWN: Status.UNKNOWN,
}


def servers_check(
    node_types: Sequence[NodeTypeSupply], agents_error: str | None = None
) -> CheckResult:
    """Enough healthy free servers of every node type the nodepools need.

    One type short fails the check; one unknown (and none short) makes it
    unknown; with no type needed yet there is nothing to check.
    """
    if not node_types:
        return CheckResult(Check.SERVERS, Status.PASS, "No nodepool names a node type yet.")
    statuses = {_SUPPLY_STATUS[supply.status] for supply in node_types}
    status = next(s for s in (Status.FAIL, Status.UNKNOWN, Status.PASS) if s in statuses)
    detail = "; ".join(supply.detail for supply in node_types) + "."
    if agents_error is not None and status is Status.UNKNOWN:
        detail += f" {agents_error}"
    return CheckResult(Check.SERVERS, status, detail)


def readable_check(hub_error: str | None) -> CheckResult:
    """Wingman read the MCE's nodes and pods. An MCE it cannot read is never picked."""
    if hub_error is not None:
        return CheckResult(
            Check.READABLE,
            Status.FAIL,
            f"Wingman could not read its nodes and pods: {hub_error}",
        )
    return CheckResult(Check.READABLE, Status.PASS, "Wingman read its nodes and pods.")


def checks_of(picture: McePicture, inputs: PlacementInputs) -> tuple[CheckResult, ...]:
    """Every required check of one candidate, in order."""
    return (
        version_check(picture.versions, inputs.version),
        free_pods_check(picture.pods, inputs.min_free_pods),
        servers_check(picture.node_types, picture.agents_error),
        readable_check(picture.hub_error),
    )


# ── The ranking ──────────────────────────────────────────────────────────────


def _spare_key(picture: McePicture) -> tuple[int, int]:
    """Known spare before unknown, then more usable spare first."""
    if picture.spare is None:
        return (1, 0)
    return (0, -picture.spare.usable)


def _rank_key(candidate: Candidate, *, owner: bool) -> tuple[int, int, tuple[int, int], str]:
    picture = candidate.picture
    return (
        (picture.owner_clusters or 0) if owner else 0,
        picture.clusters,
        _spare_key(picture),
        picture.mce,
    )


def behind_on(pick: Candidate, other: Candidate, *, owner: bool) -> Step:
    """The first ranking step on which ``pick`` beats ``other``."""
    first, second = pick.picture, other.picture
    if owner and (first.owner_clusters or 0) != (second.owner_clusters or 0):
        return Step.OWNER_CLUSTERS
    if first.clusters != second.clusters:
        return Step.CLUSTERS
    if _spare_key(first) != _spare_key(second):
        return Step.SPARE_SERVERS
    return Step.NAME


def place(
    inputs: PlacementInputs,
    pictures: Iterable[McePicture],
    *,
    problems: Sequence[str] = (),
    server_scan_error: str | None = None,
) -> Placement:
    """Check every candidate, rank those that pass, and pick the first."""
    judged = [Candidate(p, checks_of(p, inputs)) for p in pictures]
    owner = inputs.owner is not None
    eligible = sorted((c for c in judged if c.eligible), key=lambda c: _rank_key(c, owner=owner))
    ranked = [
        replace(c, rank=i, behind_on=None if i == 1 else behind_on(eligible[0], c, owner=owner))
        for i, c in enumerate(eligible, start=1)
    ]
    others = sorted((c for c in judged if not c.eligible), key=lambda c: c.mce)
    found: list[str] = []
    if not judged:
        found.append(
            f"{inputs.site} has no {inputs.env} MCE (ocp4-{inputs.env}-mce-{inputs.site}-<letter>)."
        )
    elif inputs.version is None:
        found.append("Choose an OpenShift version.")
    elif not ranked:
        found.append(f"No {inputs.env} MCE at {inputs.site} passes every check.")
    return Placement(
        inputs=inputs,
        candidates=(*ranked, *others),
        versions=newest_first(v for c in judged for v in c.picture.versions.versions),
        problems=(*found, *problems),
        server_scan_error=server_scan_error,
    )


def _spare_text(spare: SpareServers | None) -> str:
    return "unknown" if spare is None else str(spare.usable)


def _why(pick: Candidate, runner: Candidate, owner: str | None) -> str:
    first, second = pick.picture, runner.picture
    step = runner.behind_on or behind_on(pick, runner, owner=owner is not None)
    if step is Step.OWNER_CLUSTERS:
        return (
            f"{first.mce} has the fewest clusters of owner {owner}: {first.owner_clusters}, "
            f"against {second.owner_clusters} on {second.mce}."
        )
    if step is Step.CLUSTERS:
        tie = f"; both have {first.owner_clusters} of owner {owner}" if owner else ""
        return (
            f"{first.mce} has the fewest clusters: {first.clusters}, against {second.clusters} "
            f"on {second.mce}{tie}."
        )
    if step is Step.SPARE_SERVERS:
        tie = f", {first.owner_clusters} of them owner {owner}'s" if owner else ""
        return (
            f"{first.mce} has the most usable spare servers: {_spare_text(first.spare)}, against "
            f"{_spare_text(second.spare)} on {second.mce}; both have {first.clusters} "
            f"clusters{tie}."
        )
    return f"{first.mce} ties with {second.mce} on every count and comes first by name."


def _some(versions: Sequence[str]) -> str:
    shown = ", ".join(versions[:_SHOWN_VERSIONS])
    more = len(versions) - _SHOWN_VERSIONS
    return f"{shown} and {more} more" if more > 0 else shown


# ── A create's choice, checked again ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Choice:
    """What the form sends with a create: the pick it showed, and an override's reason."""

    pick: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Admission:
    """A create's MCE, accepted: Wingman's pick, or an admin's other choice with its reason."""

    placement: Placement
    chosen: str
    reason: str | None = None

    @property
    def override(self) -> bool:
        """Whether an admin chose another MCE than Wingman's pick."""
        return self.chosen != self.placement.pick

    @property
    def decision(self) -> Decision:
        """For the metric."""
        return Decision.OVERRIDE if self.override else Decision.PICKED


def fold_reason(text: str | None) -> str:
    """An override reason on one line: every run of whitespace becomes one space."""
    return _SPACES.sub(" ", text or "").strip()


def admit(placement: Placement, chosen: str, choice: Choice | None) -> Admission:
    """Accept ``chosen`` for a create, or say why not.

    - It must pass every check (422).
    - It is the pick: accepted.
    - It passes but is not the pick: an override, which needs a reason (422),
      unless the form showed it as the pick and the pick has moved since,
      which is a stale form (409, :class:`PlacementChangedError`).
    """
    inputs = placement.inputs
    pick = placement.pick
    if pick is None:
        raise InvalidInputError(
            f"No {inputs.env} MCE at {inputs.site} can take this cluster",
            [
                *placement.problems,
                *(f"{c.mce}: {f}" for c in placement.candidates for f in c.failures),
            ],
        )
    candidate = placement.candidate(chosen)
    if candidate is None:
        names = ", ".join(c.mce for c in placement.candidates)
        raise InvalidInputError(
            f"MCE {chosen} is not a {inputs.env} MCE of site {inputs.site}",
            [f"the {inputs.env} MCEs of {inputs.site} are {names}"],
        )
    if not candidate.eligible:
        raise InvalidInputError(f"MCE {chosen} cannot take this cluster", candidate.failures)
    if chosen == pick:
        return Admission(placement, chosen)
    reason = fold_reason(choice.reason if choice else None)[:MAX_REASON]
    if reason:
        return Admission(placement, chosen, reason)
    if choice is not None and choice.pick == chosen:
        raise PlacementChangedError(
            f"Wingman's pick changed from {chosen} to {pick} since the form showed it: "
            f"{placement.why} Review the placement and choose again",
            pick=pick,
        )
    raise InvalidInputError(
        f"Choosing {chosen} over Wingman's pick {pick} needs a reason",
        [f"placement.reason: say why {chosen} and not {pick} ({placement.why})"],
    )


# ── The merge request's record ───────────────────────────────────────────────


def _cell(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _servers_cell(node_types: Sequence[NodeTypeSupply]) -> str:
    if not node_types:
        return "—"
    return ", ".join(f"{t.infra_env} {_cell(t.healthy)}/{t.needed}" for t in node_types).replace(
        "|", "/"
    )


def _checks_cell(candidate: Candidate) -> str:
    if candidate.eligible:
        return "pass"
    failed = "; ".join(
        c.detail.rstrip(".") for c in candidate.checks if c.status is not Status.PASS
    )
    return f"not offered: {failed}".replace("|", "/")


def describe_placement(admission: Admission) -> str:
    """The "MCE placement" section of a create's merge request: the choice, the inputs, the numbers.

    The reason is an admin's free text: it goes in a code span, so it can
    neither format the description nor mention anyone.
    """
    placement = admission.placement
    inputs = placement.inputs
    lines = ["### MCE placement", ""]
    if admission.override:
        reason = (admission.reason or "").replace("`", "'")
        lines += [
            f"An admin chose `{admission.chosen}` over Wingman's pick `{placement.pick}`. "
            f"Reason: `{reason}`",
            "",
            f"Wingman's pick: {placement.why}",
        ]
    else:
        lines.append(f"Wingman picked `{admission.chosen}`: {placement.why}")
    lines += [
        "",
        f"Site `{inputs.site}`, {inputs.env}, OpenShift {inputs.version or '?'}, owner "
        f"{inputs.owner or 'not given'}, flavor `{inputs.flavor or '?'}`; a new cluster needs "
        f"{inputs.min_free_pods} free pods"
        + (
            " and "
            + ", ".join(f"{count} `{infra_env}`" for infra_env, count in inputs.needs)
            + " servers."
            if inputs.needs
            else "."
        ),
        "",
        "| MCE | Owner's clusters | Clusters | Usable spare (of all) | Free pods | "
        "Healthy free servers / needed | Checks |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for candidate in placement.candidates:
        picture = candidate.picture
        marks = [
            m
            for m, on in (("pick", candidate.picked), ("chosen", candidate.mce == admission.chosen))
            if on
        ]
        name = f"`{picture.mce}`" + (f" ({', '.join(marks)})" if marks else "")
        spare = (
            "unknown"
            if picture.spare is None
            else f"{picture.spare.usable} ({picture.spare.total})"
        )
        free = "unknown" if picture.pods is None else str(picture.pods.free)
        owner = "—" if inputs.owner is None else _cell(picture.owner_clusters)
        checks = _checks_cell(candidate)
        servers = _servers_cell(picture.node_types)
        lines.append(
            f"| {name} | {owner} | {picture.clusters} | {spare} | {free} | {servers} | {checks} |"
        )
    return "\n".join(lines)
