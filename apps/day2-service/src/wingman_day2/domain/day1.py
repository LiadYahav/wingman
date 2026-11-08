"""What day2 reads from the day1 repo (``gitops-day1/platform-config``): MCEs, clusters, versions.

day2 never writes the day1 repo. It needs only names and ``mastertag``s:

- ``sites/<site>/mces/<mce>/version.yaml``: the MCE hub's own version (day2-owned, hand-maintained);
- ``sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml``: a hosted cluster, and its version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from wingman_core.domain.git import RepoPath
from wingman_day2.domain import layout
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.versions import VersionFile, read_version_file


@dataclass(frozen=True, slots=True)
class Day1Entry:
    """An MCE or hosted cluster day1 knows, and its version file (``None`` when absent)."""

    site: str
    mce: str
    name: str
    path: RepoPath
    version: VersionFile | None

    @property
    def ocp_version(self) -> str | None:
        """The derived OCP version, if the file carries a ``mastertag``."""
        return self.version.ocp_version if self.version else None


@dataclass(frozen=True, slots=True)
class Day1Index:
    """Every MCE folder and hosted-cluster file of the day1 repo."""

    mces: Mapping[tuple[str, str], Day1Entry] = field(default_factory=dict)
    hosted: Mapping[tuple[str, str, str], Day1Entry] = field(default_factory=dict)

    def mce(self, site: str, mce: str) -> Day1Entry | None:
        """The day1 MCE folder ``sites/<site>/mces/<mce>``, if it exists."""
        return self.mces.get((site, mce))

    def hosted_cluster(self, site: str, mce: str, name: str) -> Day1Entry | None:
        """The day1 hosted-cluster file, if it exists."""
        return self.hosted.get((site, mce, name))


def day1_version_files(tree: RepoTree) -> list[RepoPath]:
    """The files :func:`build_day1_index` reads: MCE ``version.yaml``s and hosted-cluster files."""
    paths: list[RepoPath] = []
    sites = RepoPath.of(layout.SITES)
    for site in tree.subdirs(sites):
        for mce in tree.subdirs(sites.child(site, layout.MCES)):
            version = layout.day1_mce_version_file(site, mce)
            if tree.is_file(version):
                paths.append(version)
            paths += [entry for _, entry in _hosted_files(tree, site, mce)]
    return paths


def _hosted_files(tree: RepoTree, site: str, mce: str) -> list[tuple[str, RepoPath]]:
    """The hosted-cluster files of an MCE, by cluster name, as day1 reads them.

    A cluster name has no dot, so ``<name>.yaml`` with a dotted stem (the
    legacy ``<cluster>.wingman.yaml`` sidecar, a dotfile) is not a cluster.
    """
    folder = layout.day1_mce_dir(site, mce).child(layout.HOSTED_CLUSTERS)
    found = []
    for file in tree.files_under(folder):
        stem = file.name.removesuffix(".yaml")
        if file.parent == folder and stem != file.name and stem and "." not in stem:
            found.append((stem, file))
    return found


def build_day1_index(tree: RepoTree, contents: Mapping[str, str]) -> Day1Index:
    """The index of ``tree``, given the text of the files :func:`day1_version_files` named."""
    mces: dict[tuple[str, str], Day1Entry] = {}
    hosted: dict[tuple[str, str, str], Day1Entry] = {}
    sites = RepoPath.of(layout.SITES)

    def version(path: RepoPath) -> VersionFile | None:
        text = contents.get(str(path))
        return None if text is None else read_version_file(text, path=str(path))

    for site in tree.subdirs(sites):
        for mce in tree.subdirs(sites.child(site, layout.MCES)):
            path = layout.day1_mce_version_file(site, mce)
            mces[(site, mce)] = Day1Entry(site, mce, mce, path, version(path))
            for name, file in _hosted_files(tree, site, mce):
                hosted[(site, mce, name)] = Day1Entry(site, mce, name, file, version(file))
    return Day1Index(mces, hosted)
