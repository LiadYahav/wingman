"""The machine-config catalogue and the nodepool defaults, read through the cached repos.

The catalogue is ``mc-files/`` in the day1 repo, which day1 only ever reads
(ADR-0027); the defaults are ``nodepool-defaults.yaml`` in the specs project.
Both reads are the cached default-branch reads every other day1 read uses
(ADR-0011). A missing ``mc-files/`` is an empty catalogue that says so, and
a missing defaults file means no defaults; a defaults file that does not
parse is reported with its error, never treated as empty (ADR-0004).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import EntryKind
from wingman_day1.domain import paths
from wingman_day1.domain.errors import InvalidNodepoolDefaultsError
from wingman_day1.domain.machine_configs import (
    MachineConfigCatalog,
    NodepoolDefaults,
    defaults_problems,
    parse_nodepool_defaults,
)
from wingman_day1.ports import RepoReads


@dataclass(frozen=True, slots=True)
class DefaultsReading:
    """``nodepool-defaults.yaml`` as read: its entries, or why it could not be used."""

    defaults: NodepoolDefaults
    found: bool
    error: InvalidNodepoolDefaultsError | None = None


@dataclass(frozen=True, slots=True)
class MachineConfigOverview:
    """What the web's config picker needs: the catalogue and the defaults, checked against it."""

    catalog: MachineConfigCatalog
    defaults: DefaultsReading
    defaults_problems: tuple[str, ...]


class MachineConfigService:
    """Read the catalogue (day1 repo) and the nodepool defaults (specs project)."""

    def __init__(self, day1: RepoReads, specs: RepoReads) -> None:
        """Read ``mc-files/`` through ``day1`` and the defaults through ``specs``, both cached."""
        self._day1 = day1
        self._specs = specs

    async def catalog(self) -> MachineConfigCatalog:
        """Every config ``mc-files/`` offers, by the CI's rule."""
        try:
            entries = await self._day1.tree(paths.MC_FILES, recursive=True)
        except NotFoundError:
            return MachineConfigCatalog(
                problems=(f"the day1 repo has no {paths.MC_FILES}/ folder: no config resolves",)
            )
        return MachineConfigCatalog.from_files(e.path for e in entries if e.kind is EntryKind.FILE)

    async def defaults(self) -> DefaultsReading:
        """``nodepool-defaults.yaml``: missing is no defaults, broken carries its error."""
        try:
            file = await self._specs.read(paths.NODEPOOL_DEFAULTS_FILE)
        except NotFoundError:
            return DefaultsReading(NodepoolDefaults(), found=False)
        try:
            return DefaultsReading(parse_nodepool_defaults(file.content), found=True)
        except InvalidNodepoolDefaultsError as exc:
            return DefaultsReading(NodepoolDefaults(), found=True, error=exc)

    async def overview(self) -> MachineConfigOverview:
        """The catalogue and the defaults, with the default entries that would not resolve."""
        catalog, defaults = await asyncio.gather(self.catalog(), self.defaults())
        return MachineConfigOverview(
            catalog, defaults, tuple(defaults_problems(defaults.defaults, catalog))
        )
