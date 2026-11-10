"""Where things live in the two repositories day1 reads and writes.

Day1 values repo (``gitops-day1/platform-config``), the layout the
ApplicationSets read (ADR-0012)::

    sites/configValues.yaml
    sites/<site>/values.yaml
    sites/<site>/mces/<mce>/values.yaml      # the MCE's defaults, incl. mastertag
    sites/<site>/mces/<mce>/version.yaml     # the hub's own version (day2 reads it)
    sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml
    mc-files/...                             # machine-config sources CI renders (read only)
    upgrade/ladder.yaml                      # the verified releases (ADR-0034)
    upgrade/mces/<mce>.yaml                  # the minors each MCE can host

Specs repo (``wingman/cluster-specs``)::

    cluster-template.j2
    nodepool-defaults.yaml                   # the configs a new nodepool starts with
    specs/<spec>.yaml

Every path is built through ``RepoPath.of``, so a name from a request can
never leave the directory it is meant for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from wingman_core.domain.git import RepoPath

SITES: Final = RepoPath("sites")
HOSTED_CLUSTERS_DIR: Final = "hostedClusters"
CLUSTER_SUFFIX: Final = ".yaml"
MC_FILES: Final = RepoPath("mc-files")
UPGRADE_LADDER: Final = RepoPath("upgrade/ladder.yaml")
"""The releases the upgrade workflow steps through; the create form offers them (ADR-0034)."""

TEMPLATE_FILE: Final = RepoPath("cluster-template.j2")
NODEPOOL_DEFAULTS_FILE: Final = RepoPath("nodepool-defaults.yaml")
SPEC_SUFFIX: Final = ".yaml"


def site_dir(site: str) -> RepoPath:
    """``sites/<site>``."""
    return RepoPath.of("sites", site)


def mce_dir(site: str, mce: str) -> RepoPath:
    """``sites/<site>/mces/<mce>``."""
    return RepoPath.of("sites", site, "mces", mce)


def mce_values(site: str, mce: str) -> RepoPath:
    """``sites/<site>/mces/<mce>/values.yaml``: the MCE layer, incl. its default mastertag."""
    return mce_dir(site, mce).child("values.yaml")


def mce_version(site: str, mce: str) -> RepoPath:
    """``sites/<site>/mces/<mce>/version.yaml``: the hub's own OCP version."""
    return mce_dir(site, mce).child("version.yaml")


def upgrade_mce_rules(mce: str) -> RepoPath:
    """``upgrade/mces/<mce>.yaml``: the OCP minors the MCE's HyperShift can host."""
    return RepoPath.of("upgrade", "mces", f"{mce}.yaml")


def hosted_clusters_dir(site: str, mce: str) -> RepoPath:
    """``sites/<site>/mces/<mce>/hostedClusters``: every file here is an Argo Application."""
    return mce_dir(site, mce).child(HOSTED_CLUSTERS_DIR)


@dataclass(frozen=True, slots=True, order=True)
class ClusterRef:
    """A cluster file's place in the tree: site folder, MCE folder, file stem."""

    site: str
    mce: str
    name: str

    @property
    def path(self) -> RepoPath:
        """``sites/<site>/mces/<mce>/hostedClusters/<name>.yaml``."""
        return hosted_clusters_dir(self.site, self.mce).child(f"{self.name}{CLUSTER_SUFFIX}")


@dataclass(frozen=True, slots=True)
class HostedClustersEntry:
    """A file found under some ``hostedClusters/`` folder."""

    site: str
    mce: str
    filename: str

    @property
    def cluster(self) -> ClusterRef | None:
        """The cluster this file is, or ``None`` for a file that is not ``<name>.yaml``.

        Such files (``.gitkeep``, ``<x>.wingman.yaml``) still become Argo
        Applications; they are reported as stray, never treated as clusters.
        """
        stem = self.filename.removesuffix(CLUSTER_SUFFIX)
        if stem == self.filename or not stem or "." in stem:
            return None
        return ClusterRef(self.site, self.mce, stem)


def parse_hosted_clusters_path(path: RepoPath) -> HostedClustersEntry | None:
    """``sites/<site>/mces/<mce>/hostedClusters/<file>`` → its parts; anything else → ``None``."""
    parts = path.parts
    if len(parts) != 6 or parts[0] != "sites" or parts[2] != "mces":
        return None
    if parts[4] != HOSTED_CLUSTERS_DIR:
        return None
    return HostedClustersEntry(site=parts[1], mce=parts[3], filename=parts[5])


def spec_file(specs_root: str, name: str) -> RepoPath:
    """``<specs_root>/<name>.yaml``."""
    return RepoPath.of(*RepoPath(specs_root).parts, f"{name}{SPEC_SUFFIX}")
