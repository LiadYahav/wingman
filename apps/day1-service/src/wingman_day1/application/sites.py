"""Sites and MCEs: read-only views of folders that already exist (ADR-0018).

Wingman never creates a site or an MCE: an MCE needs a hub Argo cluster
secret, its own GitOps operator and herzi, none of which a folder gives it.
For each MCE this shows the default ``mastertag`` its ``values.yaml`` sets for
hosted clusters, the hub's own version from ``version.yaml``, and the
OpenShift releases a new cluster on it may use, from the day1 repo's
``upgrade/`` folder (ADR-0034).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import RepoPath
from wingman_day1.application.tree import Day1Tree, read_tree
from wingman_day1.domain import paths
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import InvalidClusterFileError, ResourceNotFoundError
from wingman_day1.domain.names import MceNaming, describe_mce
from wingman_day1.domain.openshift_versions import (
    OpenShiftVersions,
    missing_ladder,
    missing_mce_rules,
    parse_ladder,
    parse_mce_rules,
    versions_for,
)
from wingman_day1.ports import RepoReads


@dataclass(frozen=True, slots=True)
class MceView:
    """One MCE folder and what its files say."""

    site: str
    naming: MceNaming
    default_mastertag: str | None
    """``mastertag`` in the MCE's ``values.yaml``: the default for its hosted clusters."""
    hub_version: str | None
    """``mastertag`` in ``version.yaml``: the hub's own OCP version."""
    cluster_count: int
    stray_files: tuple[str, ...]
    """Files in ``hostedClusters/`` that are not ``<name>.yaml``; each is a broken Application."""
    problems: tuple[str, ...]

    @property
    def name(self) -> str:
        """The MCE folder name."""
        return self.naming.name


class SiteCatalog:
    """Sites and MCEs of the day1 repo."""

    def __init__(self, day1: RepoReads) -> None:
        """Read through ``day1`` (cached)."""
        self._day1 = day1

    async def tree(self) -> Day1Tree:
        """The repo's shape."""
        return await read_tree(self._day1)

    async def sites(self) -> list[str]:
        """Site folder names, sorted."""
        return list((await self.tree()).sites)

    async def mce_names(self, site: str) -> list[str]:
        """MCE folder names under a site, sorted. Unknown site → ``ResourceNotFoundError``."""
        tree = await self.tree()
        if site not in tree.sites:
            raise ResourceNotFoundError(f"site {site!r} does not exist in the day1 repo")
        return [mce for s, mce in tree.mces if s == site]

    async def require_mce(self, site: str, mce: str) -> None:
        """Raise ``ResourceNotFoundError`` unless ``sites/<site>/mces/<mce>`` exists."""
        if mce not in await self.mce_names(site):
            raise ResourceNotFoundError(f"MCE {mce!r} does not exist under site {site!r}")

    async def mces(self, site: str | None = None) -> list[MceView]:
        """MCE views, for one site or all of them."""
        tree = await self.tree()
        if site is not None and site not in tree.sites:
            raise ResourceNotFoundError(f"site {site!r} does not exist in the day1 repo")
        pairs = [(s, m) for s, m in tree.mces if site is None or s == site]
        return list(await asyncio.gather(*(self._view(tree, s, m) for s, m in pairs)))

    async def openshift_versions(self, mce: str) -> OpenShiftVersions:
        """The releases a new cluster on ``mce`` may use, newest first.

        A missing or broken ``upgrade/`` file is a problem in the result, with
        no versions; an MCE folder that exists nowhere → ``ResourceNotFoundError``.
        """
        if all(name != mce for _, name in (await self.tree()).mces):
            raise ResourceNotFoundError(f"MCE {mce!r} does not exist in the day1 repo")
        return (await self.versions_by_mce([mce]))[mce]

    async def versions_by_mce(self, mces: Iterable[str]) -> dict[str, OpenShiftVersions]:
        """``openshift_versions`` of several MCEs, the ladder read once.

        For MCEs already found in the repo: none is checked to exist.
        """
        names = sorted(set(mces))
        ladder_text, *rules = await asyncio.gather(
            self._optional(paths.UPGRADE_LADDER),
            *(self._optional(paths.upgrade_mce_rules(mce)) for mce in names),
        )
        ladder = missing_ladder() if ladder_text is None else parse_ladder(ladder_text)
        return {
            mce: versions_for(
                mce, ladder, missing_mce_rules(mce) if text is None else parse_mce_rules(mce, text)
            )
            for mce, text in zip(names, rules, strict=True)
        }

    async def default_mastertag(self, site: str, mce: str) -> str | None:
        """The MCE's default ``mastertag`` for new clusters, if it sets one."""
        tag, _ = await self._mastertag(paths.mce_values(site, mce))
        return tag

    async def _view(self, tree: Day1Tree, site: str, mce: str) -> MceView:
        (default, default_problem), (hub, hub_problem) = await asyncio.gather(
            self._mastertag(paths.mce_values(site, mce)),
            self._mastertag(paths.mce_version(site, mce)),
        )
        return MceView(
            site=site,
            naming=describe_mce(mce, site=site),
            default_mastertag=default,
            hub_version=hub,
            cluster_count=sum(1 for c in tree.clusters if (c.site, c.mce) == (site, mce)),
            stray_files=tuple(tree.stray_files(site, mce)),
            problems=tuple(p for p in (default_problem, hub_problem) if p),
        )

    async def _optional(self, path: RepoPath) -> str | None:
        """A file's text; ``None`` when it does not exist (any other read error is raised)."""
        try:
            return (await self._day1.read(path)).content
        except NotFoundError:
            return None

    async def _mastertag(self, path: RepoPath) -> tuple[str | None, str | None]:
        """``(mastertag, problem)`` from a values file; a missing file is ``(None, None)``."""
        try:
            content = (await self._day1.read(path)).content
        except NotFoundError:
            return None, None
        try:
            tag = load_values(content).get("mastertag")
        except InvalidClusterFileError as exc:
            return None, f"{path}: {'; '.join(exc.problems) or exc}"
        return (str(tag) if tag is not None else None), None
