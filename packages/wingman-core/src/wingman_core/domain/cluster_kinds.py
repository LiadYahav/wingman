"""What an MCE-level folder or a cluster file of the day1 repo is (ADR-0067).

The platform's naming convention (``kubevirt-workflows``
``docs/naming-convention.md`` §1; ADR-0067 says which revision) reserves three
cluster flavors, ``mce``, ``seed`` and ``kv``, so that day1 tells an
infrastructure cluster from a tenant's by its name:

| Kind | In the day1 repo | Name |
|---|---|---|
| Customer MCE | ``sites/<site>/mces/<mce>/`` | ``ocp4-<lc>-mce-<site>-<id>`` |
| Seed | ``sites/<site>/mces/<seed>/`` | ``ocp4-<lc>-seed-<site>-<zone>-<id>`` |
| KV cluster | ``.../mces/<seed>/hostedClusters/<kv>.yaml`` | ``ocp4-<lc>-kv-<site>-<zone>-<id>`` |
| Tenant hosted cluster | any other cluster file | the cluster's own flavor |

The deployed workflows (team-redbull/workflows ``main`` on 2026-11-23,
``shared/cluster_names.py`` and ``activities/vm_lifecycle/day1_repo.py``)
still name a seed ``ocp4-seed-<site>-<zone>`` and a KV cluster
``ocp4-kubevirt-<site>-<zone>…``, and take every file in a seed's folder as
a KV cluster; both shapes are recognised. A seed may also be named
``ocp4-<lc>-mce-seed-<site>-<id>`` (the user, 2026-11-24: no written source
has it, so it is read as a seed and flagged, ADR-0067's amendment): after
``mce-seed-`` come at least two segments, so ``ocp4-prod-mce-seed-a`` is
still a Customer MCE of the site ``seed``. Only the reserved word decides the
kind; whether the rest of a name follows the convention is the naming
rules' to say. A folder that is not a seed is a Customer MCE whatever its
name, and a file that is not a KV cluster is a tenant's.

Pure, in core, so day1 and day2 classify the same tree the same way.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

LIFECYCLES: Final = ("prod", "prep", "test")
"""The convention's ``<lc>``: the environment a cluster belongs to."""

_LC = "|".join(LIFECYCLES)
_SEED: Final = re.compile(
    rf"^ocp4-(?:(?:(?:{_LC})-)?seed(?:-|$)|(?:{_LC})-mce-seed(?:-[a-z0-9]+){{2,}}$)"
)
"""``ocp4-<lc>-seed-…`` (the convention), ``ocp4-seed-…`` (the deployed workflows) or
``ocp4-<lc>-mce-seed-<site>-<id>`` (a name the user expects; ADR-0067's amendment)."""
_KV: Final = re.compile(rf"^ocp4-(?:(?:(?:{_LC})-)?kv|kubevirt)(?:-|$)")
"""``ocp4-<lc>-kv-…`` (the convention) or ``ocp4-kubevirt-…`` (the deployed workflows)."""


class MceKind(StrEnum):
    """What an MCE-level folder, ``sites/<site>/mces/<x>/``, is."""

    MCE = "mce"
    """A Customer MCE: its hosted clusters are tenants'."""
    SEED = "seed"
    """A seed: it hosts one zone's KV clusters, never a tenant's cluster."""


class HostedClusterKind(StrEnum):
    """What a cluster file, ``.../hostedClusters/<name>.yaml``, is."""

    TENANT = "tenant"
    """A customer's hosted cluster."""
    KV = "kv"
    """A KV cluster: a hosted cluster on a seed whose workers host tenants' VMs."""


def mce_kind(folder: str) -> MceKind:
    """A seed when the folder's name carries the reserved word ``seed``; else a Customer MCE."""
    return MceKind.SEED if _SEED.match(folder) else MceKind.MCE


def is_kv_name(stem: str) -> bool:
    """Whether a cluster file stem carries the reserved word ``kv`` (or ``kubevirt``)."""
    return _KV.match(stem) is not None


def hosted_cluster_kind(stem: str, *, mce: str) -> HostedClusterKind:
    """A KV cluster when its folder is a seed or its name says so; else a tenant's.

    ``mce`` may be empty when only the name is known (a merge request's title):
    then the name alone decides.
    """
    if (mce and mce_kind(mce) is MceKind.SEED) or is_kv_name(stem):
        return HostedClusterKind.KV
    return HostedClusterKind.TENANT
