"""Discovery: every team repo plus day1, turned into teams, plans and clusters (ADR-0020).

Clusters come from directories across all team repos, joined with the day1
repo, which knows MCEs and hosted clusters a team repo may not place yet. A
hosted cluster's env is the env of the team folder it sits in; for a day1
cluster no team places, it is the env of its MCE's folder in any team repo,
else the one its name carries (``ocp4-<env>-...``), else unknown.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ClusterKind, ClusterRef, env_from_name
from wingman_day2.domain.day1 import Day1Index
from wingman_day2.domain.errors import (
    AmbiguousClusterError,
    UnknownClusterError,
    UnknownTeamError,
)
from wingman_day2.domain.findings import Finding, Rule, warning
from wingman_day2.domain.lints import lint_team, position_conflicts
from wingman_day2.domain.platform import Destination, TeamPlan, discover, plan_team
from wingman_day2.domain.teams import Team, TeamRepo, control_files
from wingman_day2.ports import Day1Repository, SigsRepository


@dataclass(frozen=True, slots=True)
class TeamState:
    """One team: its repo as the generators see it, what it generates, and what is wrong."""

    team: Team
    repo: TeamRepo
    plan: TeamPlan
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class ClusterSummary:
    """One destination, where it is known from, and its version."""

    ref: ClusterRef
    ocp_version: str | None
    teams: tuple[str, ...]
    in_day1: bool
    findings: tuple[Finding, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Topology:
    """Everything discovery found, at one moment."""

    teams: tuple[TeamState, ...]
    day1: Day1Index
    clusters: tuple[ClusterSummary, ...]
    findings: tuple[Finding, ...]

    def team(self, name: str) -> TeamState:
        """The team called ``name``."""
        for state in self.teams:
            if state.team.name == name:
                return state
        raise UnknownTeamError(f"no team {name!r} in the sigs group", details={"team": name})

    def cluster(self, ref: ClusterRef) -> ClusterSummary:
        """The summary of ``ref``."""
        for summary in self.clusters:
            if summary.ref == ref:
                return summary
        raise UnknownClusterError(
            f"no cluster {ref.id} in day1 or any team repo", details={"cluster": ref.id}
        )

    def resolve(self, key: str, *, mce: str | None = None) -> ClusterSummary:
        """The cluster ``key`` names: a cluster id, or a bare name that is unique.

        ``mce`` (the legacy query parameter) narrows a bare name to one MCE.
        """
        if key == "hub" or ":" in key:
            return self.cluster(ClusterRef.parse(key))
        found = [
            s for s in self.clusters if s.ref.name == key and (mce is None or s.ref.mce == mce)
        ]
        if not found:
            raise UnknownClusterError(
                f"no cluster named {key!r} in day1 or any team repo", details={"cluster": key}
            )
        if len(found) > 1:
            ids = sorted(s.ref.id for s in found)
            raise AmbiguousClusterError(
                f"{key!r} names {len(ids)} destinations; address one by its id",
                details={"cluster": key, "candidates": ids},
            )
        return found[0]


class TopologyService:
    """Load the topology from the team repos and day1."""

    def __init__(self, sigs: SigsRepository, day1: Day1Repository) -> None:
        """Read through ``sigs`` and ``day1`` (both cache)."""
        self._sigs = sigs
        self._day1 = day1

    async def team_repo(self, team: Team) -> TeamRepo:
        """``team``'s tree and control files."""
        tree = await self._sigs.tree(team)
        paths = control_files(tree)
        files = await asyncio.gather(*(self._sigs.read(team, p) for p in paths))
        return TeamRepo(
            team.name,
            tree,
            {str(p): f.content for p, f in zip(paths, files, strict=True) if f is not None},
        )

    async def load(self) -> Topology:
        """Discover everything."""
        teams, day1 = await asyncio.gather(self._sigs.teams(), self._day1.index())
        repos = await asyncio.gather(*(self.team_repo(t) for t in teams))
        states = []
        for team, repo in zip(teams, repos, strict=True):
            plan = plan_team(repo, day1)
            states.append(TeamState(team, repo, plan, tuple(lint_team(repo, day1, plan))))
        return build_topology(tuple(states), day1)


def build_topology(states: tuple[TeamState, ...], day1: Day1Index) -> Topology:
    """Join the team plans with day1 into one list of clusters."""
    registered: dict[ClusterRef, list[Destination]] = defaultdict(list)
    teams_of: dict[ClusterRef, set[str]] = defaultdict(set)
    refs_by_team = {}
    for state in states:
        refs_by_team[state.team.name] = discover(state.repo.tree)
        for destination in state.plan.destinations:
            registered[destination.ref].append(destination)
            if destination.ref.kind is not ClusterKind.HUB or state.plan.apps_on(destination.ref):
                teams_of[destination.ref].add(state.team.name)
    mce_envs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ref in registered:
        if ref.kind is ClusterKind.MCE:
            mce_envs[(ref.site, ref.mce)].add(ref.env)

    def env_of(site: str, mce: str, name: str) -> list[str]:
        envs = sorted(mce_envs.get((site, mce), set()))
        return envs or [env_from_name(mce) or env_from_name(name)]

    from_day1: dict[ClusterRef, str | None] = {}
    for (site, mce), entry in day1.mces.items():
        for env in env_of(site, mce, mce):
            from_day1[ClusterRef.mce_hub(site, env, mce)] = entry.ocp_version
    for (site, mce, name), entry in day1.hosted.items():
        placed = [r for r in registered if r.kind is ClusterKind.HOSTED and r.name == name]
        refs = [r for r in placed if (r.site, r.mce) == (site, mce)] or [
            ClusterRef.hosted(site, env, mce, name) for env in env_of(site, mce, name)
        ]
        for ref in refs:
            from_day1[ref] = entry.ocp_version

    summaries = []
    for ref in sorted({*registered, *from_day1}, key=_order):
        versions = {d.ocp_version for d in registered.get(ref, []) if d.ocp_version}
        version = from_day1.get(ref) or (versions.pop() if len(versions) == 1 else None)
        findings: list[Finding] = []
        if ref.kind is not ClusterKind.HUB and not ref.env:
            findings.append(
                warning(
                    Rule.ENV_UNKNOWN,
                    f"{ref.name}'s env is unknown: no team repo places it or its MCE, and its name "
                    "does not follow ocp4-<env>-<name>-<site>; it cannot be installed to",
                    cluster=ref.id,
                )
            )
        for state in states:
            findings += [f for f in state.findings if f.cluster == ref.id or _about(f.path, ref)]
        summaries.append(
            ClusterSummary(
                ref,
                version,
                tuple(sorted(teams_of.get(ref, set()))),
                ref in from_day1,
                tuple(findings),
            )
        )
    team_findings = tuple(f for s in states for f in s.findings)
    return Topology(
        states, day1, tuple(summaries), (*team_findings, *position_conflicts(refs_by_team))
    )


def _about(path: str, ref: ClusterRef) -> bool:
    """Whether a finding at ``path`` is about ``ref``: its own folder, or the MCE folder itself."""
    if not path or ref.kind is ClusterKind.HUB or not ref.env:
        return False
    own = str(layout.cluster_dir(ref))
    if path == own or path.startswith(f"{own}/"):
        return True
    return ref.kind is ClusterKind.MCE and path == str(layout.mce_dir(ref.site, ref.env, ref.mce))


_KIND_ORDER = {ClusterKind.HUB: 0, ClusterKind.MCE: 1, ClusterKind.HOSTED: 2, ClusterKind.UPI: 3}


def _order(ref: ClusterRef) -> tuple[object, ...]:
    return (ref.site, ref.env, ref.mce, _KIND_ORDER[ref.kind], ref.name)
