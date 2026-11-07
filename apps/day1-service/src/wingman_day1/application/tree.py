"""The day1 repo's shape, from one recursive tree listing of ``sites/``.

Sites and MCEs are folders that already exist (ADR-0018): Wingman lists them
and never creates them. Clusters are the ``<name>.yaml`` files under each
``hostedClusters/``; any other file there is reported as stray, because the
ApplicationSet turns it into an Application too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import EntryKind
from wingman_day1.domain import paths
from wingman_day1.domain.paths import ClusterRef, HostedClustersEntry
from wingman_day1.ports import RepoReads

_SITE_DEPTH: Final = 2  # sites/<site>
_MCE_DEPTH: Final = 4  # sites/<site>/mces/<mce>


@dataclass(frozen=True, slots=True)
class Day1Tree:
    """Sites, MCEs and hostedClusters entries at the default branch."""

    sites: tuple[str, ...]
    mces: tuple[tuple[str, str], ...]
    """``(site, mce)`` pairs."""
    entries: tuple[HostedClustersEntry, ...]

    @property
    def clusters(self) -> list[ClusterRef]:
        """Every cluster file, sorted by site, MCE and name."""
        return sorted(ref for e in self.entries if (ref := e.cluster) is not None)

    def stray_files(self, site: str, mce: str) -> list[str]:
        """Files under an MCE's ``hostedClusters/`` that are not ``<name>.yaml``."""
        return sorted(
            e.filename for e in self.entries if (e.site, e.mce) == (site, mce) and e.cluster is None
        )

    def find(self, name: str) -> list[ClusterRef]:
        """Clusters with this file stem, under any MCE."""
        return [ref for ref in self.clusters if ref.name == name]


async def read_tree(day1: RepoReads) -> Day1Tree:
    """List ``sites/`` recursively (one cached call). No ``sites/`` folder means no sites."""
    try:
        entries = await day1.tree(paths.SITES, recursive=True)
    except NotFoundError:
        return Day1Tree((), (), ())
    sites: list[str] = []
    mces: list[tuple[str, str]] = []
    found: list[HostedClustersEntry] = []
    for entry in entries:
        parts = entry.path.parts
        if entry.kind is EntryKind.DIRECTORY:
            if len(parts) == _SITE_DEPTH:
                sites.append(parts[1])
            elif len(parts) == _MCE_DEPTH and parts[2] == "mces":
                mces.append((parts[1], parts[3]))
        elif (hosted := paths.parse_hosted_clusters_path(entry.path)) is not None:
            found.append(hosted)
    return Day1Tree(tuple(sorted(sites)), tuple(sorted(mces)), tuple(found))
