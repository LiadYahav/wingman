"""Repo lints on demand, and the "prepare an OCP upgrade" check."""

from __future__ import annotations

import asyncio

from wingman_day2.application.apps import load_deploy
from wingman_day2.application.topology import ClusterSummary, TeamState, TopologyService
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.lints import upgrade_check
from wingman_day2.domain.versions import mastertag_problem
from wingman_day2.ports import SigsRepository


class LintService:
    """Run every check on the team repos."""

    def __init__(self, topology: TopologyService, sigs: SigsRepository) -> None:
        """Discover through ``topology``; read deploy configs through ``sigs``."""
        self._topology = topology
        self._sigs = sigs

    async def _leaf_findings(self, state: TeamState) -> list[Finding]:
        deploys = await asyncio.gather(
            *(load_deploy(self._sigs, state.team, state.repo.tree, app) for app in state.plan.apps)
        )
        return [f for deploy in deploys for f in deploy.findings]

    async def report(self, team: str | None = None) -> list[Finding]:
        """Structural findings plus every app's deploy-config findings (one team, or all)."""
        topology = await self._topology.load()
        states = [topology.team(team)] if team else list(topology.teams)
        leaf = await asyncio.gather(*(self._leaf_findings(s) for s in states))
        structural = (
            [f for f in topology.findings if f.team == team] if team else list(topology.findings)
        )
        return sorted({*structural, *(f for found in leaf for f in found)})

    async def upgrade_check(
        self, key: str, to: str, *, mce: str | None = None
    ) -> tuple[ClusterSummary, list[Finding]]:
        """The charts on a cluster that lack an ``ocp-versions/<to>/`` pin they would need."""
        problem = mastertag_problem(to)
        if problem:
            raise ChangeRefusedError(problem, details={"rule": "version"})
        topology = await self._topology.load()
        summary = topology.resolve(key, mce=mce)
        apps = [a for s in topology.teams for a in s.plan.apps_on(summary.ref)]
        trees = {s.team.name: s.repo.tree for s in topology.teams}
        return summary, upgrade_check(apps, trees, to.split("-", 1)[0])
