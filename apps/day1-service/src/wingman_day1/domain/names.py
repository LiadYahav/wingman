"""Hosted-cluster and MCE naming rules (ADR-0014).

The team's conventions:

- MCE folder:      ``ocp4-<env>-mce-<site>-<letter>``
- cluster file:    ``ocp4-<env>-<name>-<site>[-<seq>].yaml``, env in {prod, prep, test}
- a new cluster's ``<seq>`` is one letter, ``a`` to ``z`` (ADR-0040)

The site token may itself contain dashes (``site-a``, ``bat-yam``), so a site
is never parsed out of a name by splitting on dashes: a name is matched
against the site folder it lives in. Existing names that break the
convention (``ocp4-upgrade-demo`` under ``ocp4-mce-workflow-test``) are
listed and flagged, never hidden; only new names are refused.

What ArgoCD and the chart make of a cluster file stem is
:class:`HostedClusterNaming`: production's ApplicationSet strips ``ocp4-``
(``ocp4-prod-x-site1`` in ``hcp-prod-x-site1``), the GitHub sandbox keeps
the whole stem. Which one applies is a deployment setting (ADR-0015).
"""

from __future__ import annotations

import re
import string
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

CLUSTER_FILE_PREFIX: Final = "ocp4-"
MAX_DNS_LABEL: Final = 63
HOSTED_CLUSTER_PREFIX: Final = "ocp4-"
"""What the chart puts before ``clusterName`` to name the HostedCluster."""

_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_SEGMENT = r"[a-z0-9]+"
_NAME = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
SEQUENCE_LETTERS: Final = string.ascii_lowercase
"""A new cluster's sequence, in the order they are given (ADR-0040)."""
_NOT_LABEL_CHARS = re.compile(r"[^a-z0-9]+")


class Env(StrEnum):
    """The environment field of cluster and MCE names."""

    PROD = "prod"
    PREP = "prep"
    TEST = "test"


_ENVS = "|".join(e.value for e in Env)


def dns_label_problems(value: str, *, what: str) -> list[str]:
    """Why ``value`` is not a Kubernetes DNS-1123 label; empty when it is one."""
    problems: list[str] = []
    if len(value) > MAX_DNS_LABEL:
        problems.append(f"{what} {value!r} is longer than {MAX_DNS_LABEL} characters")
    if not _DNS_LABEL.match(value):
        problems.append(
            f"{what} {value!r} must be lowercase letters, digits and '-', "
            "starting and ending with a letter or digit"
        )
    return problems


@dataclass(frozen=True, slots=True)
class MceNaming:
    """What an MCE folder name says, read against its site folder."""

    name: str
    site: str
    env: Env | None
    letter: str | None
    problems: tuple[str, ...]

    @property
    def follows_convention(self) -> bool:
        """Whether the name is ``ocp4-<env>-mce-<site>-<letter>`` for its own site."""
        return not self.problems


def describe_mce(name: str, *, site: str) -> MceNaming:
    """Read an MCE folder name against the site folder it sits in."""
    pattern = re.compile(rf"^ocp4-(?P<env>{_ENVS})-mce-{re.escape(site)}-(?P<letter>{_SEGMENT})$")
    match = pattern.match(name)
    if match:
        return MceNaming(name, site, Env(match["env"]), match["letter"], ())
    return MceNaming(
        name,
        site,
        None,
        None,
        (f"MCE {name!r} does not follow ocp4-<env>-mce-{site}-<letter>",),
    )


@dataclass(frozen=True, slots=True)
class ClusterNaming:
    """What a cluster file stem says, read against its site folder."""

    stem: str
    site: str
    env: Env | None
    short_name: str | None
    sequence: str | None
    problems: tuple[str, ...]

    @property
    def follows_convention(self) -> bool:
        """Whether the stem is ``ocp4-<env>-<name>-<site>[-<seq>]`` for its own site."""
        return not self.problems


def describe_cluster(stem: str, *, site: str) -> ClusterNaming:
    """Read a cluster file stem against the site folder it sits in.

    A greedy ``<name>`` makes the reading unique: ``ocp4-prep-amit-site2-a``
    is name ``amit``, sequence ``a``; ``ocp4-test-storage-site-a-a`` with site
    ``site-a`` is name ``storage``, sequence ``a``.
    """
    problems = dns_label_problems(stem, what="cluster name")
    pattern = re.compile(
        rf"^ocp4-(?P<env>{_ENVS})-(?P<name>{_NAME})-{re.escape(site)}(?:-(?P<seq>{_SEGMENT}))?$"
    )
    match = pattern.match(stem)
    if match is None:
        problems.append(f"cluster {stem!r} does not follow ocp4-<env>-<name>-{site}[-<seq>]")
        return ClusterNaming(stem, site, None, None, None, tuple(problems))
    return ClusterNaming(
        stem, site, Env(match["env"]), match["name"], match["seq"], tuple(problems)
    )


@dataclass(frozen=True, slots=True)
class HostedClusterRef:
    """The objects the chart renders for one cluster file."""

    cluster_name: str
    """The chart's ``clusterName``."""

    @property
    def name(self) -> str:
        """The HostedCluster: ``ocp4-<clusterName>``, the full file stem in production.

        The team's hostedclusters-setup chart has always named it so (checked
        live on several MCEs, 2026-11-08). Only the namespace takes the bare
        ``clusterName``.
        """
        return f"{HOSTED_CLUSTER_PREFIX}{self.cluster_name}"

    @property
    def namespace(self) -> str:
        """Where the HostedCluster and its NodePools live: ``hcp-<clusterName>``."""
        return f"hcp-{self.cluster_name}"

    @property
    def control_plane_namespace(self) -> str:
        """HyperShift's control-plane namespace: ``<namespace>-<name>``."""
        return f"{self.namespace}-{self.name}"


@dataclass(frozen=True, slots=True)
class HostedClusterNaming:
    """How a cluster file stem becomes the chart's ``clusterName``.

    ``strip_prefix`` is ``ocp4-`` in production (its ApplicationSet passes
    ``trimPrefix "ocp4-"`` of the file name) and empty in the GitHub sandbox,
    whose ApplicationSet passes the whole stem. A ``clusterName`` key in the
    file itself wins over both, as in production.
    """

    strip_prefix: str = CLUSTER_FILE_PREFIX

    def for_file(self, stem: str, *, explicit: str | None = None) -> HostedClusterRef:
        """The HostedCluster a file with this stem (and optional ``clusterName``) renders."""
        if explicit:
            return HostedClusterRef(explicit)
        return HostedClusterRef(stem.removeprefix(self.strip_prefix) if self.strip_prefix else stem)


def new_cluster_problems(
    stem: str, *, site: str, mce: str, naming: HostedClusterNaming
) -> list[str]:
    """Every reason ``stem`` may not be used for a new cluster under ``site``/``mce``.

    The name must follow the convention for its site, its env must be the
    MCE's env (so the MCE must follow the convention too), and every object
    name the chart derives from it must fit in a DNS-1123 label.
    """
    cluster = describe_cluster(stem, site=site)
    problems = list(cluster.problems)
    mce_naming = describe_mce(mce, site=site)
    if not mce_naming.follows_convention:
        problems.append(
            f"MCE {mce!r} does not follow ocp4-<env>-mce-{site}-<letter>, so the cluster's env "
            "cannot be checked against it; Wingman creates clusters only under MCEs that do"
        )
    elif cluster.env is not None and cluster.env is not mce_naming.env:
        problems.append(
            f"cluster env {cluster.env.value!r} does not match MCE {mce!r} env "
            f"{mce_naming.env.value if mce_naming.env else '?'!r}"
        )
    sequence = cluster.sequence
    if sequence is not None and (len(sequence) != 1 or sequence not in SEQUENCE_LETTERS):
        base = stem.removesuffix(f"-{sequence}")
        problems.append(
            f"sequence {sequence!r} of cluster {stem!r} must be one letter, a to z "
            f"({base}-a): a number is not the convention"
        )
    problems.extend(_length_problems(stem, naming))
    return problems


def _length_problems(stem: str, naming: HostedClusterNaming) -> list[str]:
    """The chart's object names for ``stem`` that would not fit in a DNS-1123 label."""
    ref = naming.for_file(stem)
    return [
        f"{what} {value!r} would be {len(value)} characters; the limit is {MAX_DNS_LABEL}"
        for what, value in (
            ("HostedCluster name", ref.name),
            ("control-plane namespace", ref.control_plane_namespace),
        )
        if len(value) > MAX_DNS_LABEL
    ]


def short_name_of(flavor: str) -> str:
    """A flavor's name as a cluster's ``<name>``: lowercase, other characters as single dashes."""
    return _NOT_LABEL_CHARS.sub("-", flavor.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class NameSuggestion:
    """A name for a new cluster from a flavor, or why there is none (ADR-0040)."""

    name: str | None
    env: Env | None
    short_name: str
    sequence: str | None
    problems: tuple[str, ...] = ()


def suggest_cluster_name(
    flavor: str,
    *,
    site: str,
    mce: str,
    taken: Collection[str],
    naming: HostedClusterNaming,
) -> NameSuggestion:
    """``ocp4-<env>-<flavor>-<site>-<letter>`` with the first letter no name in ``taken`` has.

    The env is the MCE's. The flavor's name is cut short (never below one
    character) until the chart's object names fit in a DNS-1123 label.
    """
    short = short_name_of(flavor)
    env = describe_mce(mce, site=site).env
    if env is None:
        return NameSuggestion(
            None,
            None,
            short,
            None,
            (f"MCE {mce!r} does not follow ocp4-<env>-mce-{site}-<letter>, so it gives no env",),
        )
    while len(short) > 1 and _length_problems(f"ocp4-{env}-{short}-{site}-a", naming):
        short = short[:-1].rstrip("-")
    base = f"ocp4-{env}-{short}-{site}"
    free = next((letter for letter in SEQUENCE_LETTERS if f"{base}-{letter}" not in taken), None)
    if free is None:
        return NameSuggestion(
            None,
            env,
            short,
            None,
            (f"every name from {base}-a to {base}-z is taken; type another name",),
        )
    name = f"{base}-{free}"
    return NameSuggestion(name, env, short, free, tuple(_length_problems(name, naming)))
