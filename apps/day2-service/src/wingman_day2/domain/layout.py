"""Paths in a team repo (``sigs/<team>``) and in the day1 repo, as the platform reads them.

Every path is built from validated segments (``RepoPath.of``), so a name from a
request can never reach outside the folder it is meant for.
"""

from __future__ import annotations

from typing import Final

from wingman_core.domain.git import RepoPath
from wingman_day2.domain.clusters import IN_CLUSTER, ClusterKind, ClusterRef, DefaultsScope
from wingman_day2.domain.errors import ChangeRefusedError

OPERATORS: Final = "operators"
OCP_VERSIONS: Final = "ocp-versions"
DEFAULTS: Final = "defaults"
SITES: Final = "sites"
MCES: Final = "mces"
UPI: Final = "upi"
HOSTED_CLUSTERS: Final = "hostedClusters"
VALUES_FILE: Final = "values.yaml"
VERSION_FILE: Final = "version.yaml"
EXCLUSIONS_FILE: Final = "exclusions.yaml"
GITKEEP: Final = ".gitkeep"


def deploy_config_name(chart: str) -> str:
    """``<chart>.yaml``: the deploy config the platform reads from a chart folder."""
    return f"{chart}.yaml"


def operators_dir(chart: str) -> RepoPath:
    """``operators/<chart>``: the team's default for a chart (never scanned by a generator)."""
    return RepoPath.of(OPERATORS, chart)


def ocp_versions_dir(chart: str) -> RepoPath:
    """``operators/<chart>/ocp-versions``: per-OCP-version pins of a version-sensitive chart."""
    return operators_dir(chart).child(OCP_VERSIONS)


def ocp_version_dir(chart: str, version: str) -> RepoPath:
    """``operators/<chart>/ocp-versions/<full version>``."""
    return ocp_versions_dir(chart).child(version)


def defaults_dir(scope: DefaultsScope) -> RepoPath:
    """``defaults/<scope>``."""
    return RepoPath.of(DEFAULTS, str(scope))


def exclusions_file(scope: DefaultsScope) -> RepoPath:
    """``defaults/<scope>/exclusions.yaml``: the one structural opt-out of a fleet scope."""
    return defaults_dir(scope).child(EXCLUSIONS_FILE)


def site_dir(site: str) -> RepoPath:
    """``sites/<site>``."""
    return RepoPath.of(SITES, site)


def site_env_dir(site: str, env: str) -> RepoPath:
    """``sites/<site>/<env>``."""
    return site_dir(site).child(_env(env))


def mce_dir(site: str, env: str, mce: str) -> RepoPath:
    """``sites/<site>/<env>/mces/<mce>``: the folder that registers an MCE with a team."""
    return site_env_dir(site, env).child(MCES, mce)


def upi_dir(site: str, env: str) -> RepoPath:
    """``sites/<site>/<env>/upi``: the UPI-wide slot's folder."""
    return site_env_dir(site, env).child(UPI)


def cluster_dir(ref: ClusterRef) -> RepoPath:
    """The folder whose chart subfolders are this destination's charts."""
    if ref.kind is ClusterKind.HUB:
        return defaults_dir(DefaultsScope.HUB)
    if ref.kind is ClusterKind.MCE:
        return mce_dir(ref.site, ref.env, ref.mce).child(IN_CLUSTER)
    if ref.kind is ClusterKind.HOSTED:
        return mce_dir(ref.site, ref.env, ref.mce).child(ref.name)
    return upi_dir(ref.site, ref.env).child(ref.name)


def registration_dir(ref: ClusterRef) -> RepoPath | None:
    """The folder whose existence registers ``ref`` with a team (none for the hub).

    For an MCE hub it is the MCE folder, not ``in-cluster/``: the in-cluster
    app exists for every MCE folder, with or without charts of its own.
    """
    if ref.kind is ClusterKind.HUB:
        return None
    if ref.kind is ClusterKind.MCE:
        return mce_dir(ref.site, ref.env, ref.mce)
    return cluster_dir(ref)


def chart_dir(ref: ClusterRef, chart: str) -> RepoPath:
    """``<cluster folder>/<chart>``."""
    return cluster_dir(ref).child(chart)


def upi_version_file(ref: ClusterRef) -> RepoPath:
    """A UPI cluster's optional ``version.yaml`` in its own folder."""
    return cluster_dir(ref).child(VERSION_FILE)


def day1_mce_dir(site: str, mce: str) -> RepoPath:
    """day1 ``sites/<site>/mces/<mce>`` (the day1 tree has no env level)."""
    return RepoPath.of(SITES, site, MCES, mce)


def day1_mce_version_file(site: str, mce: str) -> RepoPath:
    """day1 ``sites/<site>/mces/<mce>/version.yaml``: the MCE hub's own OCP version."""
    return day1_mce_dir(site, mce).child(VERSION_FILE)


def day1_hosted_cluster_file(site: str, mce: str, cluster: str) -> RepoPath:
    """day1 ``sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml``."""
    return day1_mce_dir(site, mce).child(HOSTED_CLUSTERS, f"{cluster}.yaml")


def _env(env: str) -> str:
    if not env:
        raise ChangeRefusedError(
            "This cluster's env is unknown: no team repo places it under sites/<site>/<env>/ and "
            "its name does not follow ocp4-<env>-<name>-<site>.",
            details={"rule": "env-unknown"},
        )
    return env
