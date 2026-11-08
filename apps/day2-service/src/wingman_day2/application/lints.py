"""Repo lints on demand, and the "prepare an OCP upgrade" check."""

from __future__ import annotations

import asyncio

from wingman_core.domain.git import RepoPath
from wingman_day2.application.apps import AppDeploy, load_deploy, load_layers
from wingman_day2.application.catalog import chart_repo_findings, check_chart_repo
from wingman_day2.application.topology import ClusterSummary, TeamState, TopologyService
from wingman_day2.domain import layout
from wingman_day2.domain.deploy_config import REPOURL, truthy
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.lints import upgrade_check
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.versions import mastertag_problem
from wingman_day2.ports import ChartRepository, SigsRepository


class LintService:
    """Run every check on the team repos."""

    def __init__(
        self, topology: TopologyService, sigs: SigsRepository, charts: ChartRepository
    ) -> None:
        """Discover through ``topology``, read through ``sigs``, find chart repos in ``charts``."""
        self._topology = topology
        self._sigs = sigs
        self._charts = charts

    async def _deploys(self, state: TeamState) -> list[AppDeploy]:
        return list(
            await asyncio.gather(
                *(
                    load_deploy(self._sigs, state.team, state.repo.tree, app)
                    for app in state.plan.apps
                )
            )
        )

    async def _team_defaults(self, state: TeamState) -> list[tuple[str, str, str, str]]:
        """``(team, path, repourl, chart)`` of every catalog entry, installed anywhere or not."""
        tree = state.repo.tree
        charts = tree.subdirs(RepoPath.of(layout.OPERATORS))
        paths = [layout.operators_dir(c).child(layout.deploy_config_name(c)) for c in charts]
        loaded = await load_layers(
            self._sigs, state.team, tree, [Layer(LayerRole.TEAM, p) for p in paths]
        )
        return [
            (state.team.name, str(x.layer.path), str(x.values[REPOURL]), chart)
            for chart, x in zip(charts, loaded, strict=True)
            if truthy(x.values.get(REPOURL))
        ]

    async def _repourl_findings(
        self, states: list[TeamState], deploys: list[AppDeploy]
    ) -> list[Finding]:
        """Every file that sets a ``repourl`` GitLab moved or refuses, once per file and URL."""
        setters: dict[tuple[str, str, str], str] = {}
        for found in await asyncio.gather(*map(self._team_defaults, states)):
            for team, path, url, chart in found:
                setters.setdefault((team, path, url), chart)
        for deploy in deploys:
            label = deploy.merged.provenance.get(REPOURL)
            if deploy.leaf.repo_url and isinstance(label, str):
                key = (deploy.app.team, label, deploy.leaf.repo_url)
                setters.setdefault(key, deploy.app.chart)
        urls = sorted({url for _, _, url in setters})
        found = await asyncio.gather(*(check_chart_repo(self._charts, u) for u in urls))
        checks = dict(zip(urls, found, strict=True))
        return [
            finding
            for (team, path, url), chart in setters.items()
            for finding in chart_repo_findings(checks[url], path=path, team=team, chart=chart)
        ]

    async def report(self, team: str | None = None) -> list[Finding]:
        """Structural findings, every app's deploy-config findings, and stale chart repos."""
        topology = await self._topology.load()
        states = [topology.team(team)] if team else list(topology.teams)
        deploys = [d for found in await asyncio.gather(*map(self._deploys, states)) for d in found]
        structural = (
            [f for f in topology.findings if f.team == team] if team else list(topology.findings)
        )
        leaf = [f for deploy in deploys for f in deploy.findings]
        return sorted({*structural, *leaf, *await self._repourl_findings(states, deploys)})

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
