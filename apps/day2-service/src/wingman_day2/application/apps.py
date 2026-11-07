"""Reading one app's layer files and computing what the platform deploys for it."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from wingman_core.domain.git import FileContent
from wingman_day2.domain.deploy_config import LeafApplication, leaf_application
from wingman_day2.domain.findings import Finding
from wingman_day2.domain.lints import lint_leaf
from wingman_day2.domain.merge import MergeResult, merge_values
from wingman_day2.domain.platform import PlannedApp
from wingman_day2.domain.stacks import Layer
from wingman_day2.domain.teams import Team
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.yaml_values import YamlProblem, parse_values
from wingman_day2.ports import SigsRepository


@dataclass(frozen=True, slots=True)
class LoadedLayer:
    """One layer file, read and parsed (``file`` is ``None`` when it does not exist)."""

    layer: Layer
    file: FileContent | None
    values: dict[str, object]
    problem: YamlProblem | None = None

    @property
    def exists(self) -> bool:
        """Whether the file exists."""
        return self.file is not None


@dataclass(frozen=True, slots=True)
class AppDeploy:
    """An app's deploy-config layers, their merge (provenance labels are file paths) and leaf."""

    app: PlannedApp
    layers: tuple[LoadedLayer, ...]
    merged: MergeResult
    leaf: LeafApplication
    findings: tuple[Finding, ...]

    def layer(self, path: str) -> LoadedLayer | None:
        """The loaded layer at ``path``."""
        return next((x for x in self.layers if str(x.layer.path) == path), None)


async def load_layers(
    sigs: SigsRepository, team: Team, tree: RepoTree, layers: Sequence[Layer]
) -> tuple[LoadedLayer, ...]:
    """Read every layer that exists in ``tree``; absent ones load as empty."""

    async def load(layer: Layer) -> LoadedLayer:
        if not tree.is_file(layer.path):
            return LoadedLayer(layer, None, {})
        file = await sigs.read(team, layer.path)
        if file is None:
            return LoadedLayer(layer, None, {})
        values, problem = parse_values(file.content, path=str(layer.path))
        return LoadedLayer(layer, file, values, problem)

    return tuple(await asyncio.gather(*(load(layer) for layer in layers)))


def deploy_of(app: PlannedApp, layers: tuple[LoadedLayer, ...], tree: RepoTree) -> AppDeploy:
    """The leaf Application ``layers`` (the app's deploy-config files) render."""
    merged = merge_values({}, [(str(x.layer.path), x.values) for x in layers if x.exists])
    leaf = leaf_application(merged.values, team=app.team, chart=app.chart, ref=app.ref)
    docs = [(x.layer, x.values if x.exists else None, x.problem) for x in layers]
    return AppDeploy(app, layers, merged, leaf, tuple(lint_leaf(app, docs, leaf, tree)))


async def load_deploy(
    sigs: SigsRepository, team: Team, tree: RepoTree, app: PlannedApp
) -> AppDeploy:
    """Read ``app``'s deploy-config files and render its leaf."""
    return deploy_of(app, await load_layers(sigs, team, tree, app.deploy_config_layers), tree)
