"""How a seed's and a KV cluster's names read, and each folder and file by its kind (ADR-0067).

The kind comes from the reserved words (``wingman_core.domain.cluster_kinds``);
this module says whether the rest of the name follows the platform's
convention for that kind, read against the site folder it sits in (a site may
hold dashes, ADR-0014):

- seed: ``ocp4-<lc>-seed-<site>-<zone>-<id>``
- KV cluster: ``ocp4-<lc>-kv-<site>-<zone>-<id>``

The deployed workflows' shapes, ``ocp4-seed-<site>-<zone>`` and
``ocp4-kubevirt-<site>-<zone>…``, are read too (their zone is known) and
flagged, never hidden, as every off-convention name is; so is a seed named
``ocp4-<lc>-mce-seed-<site>-<id>`` (its lifecycle and id are read, it has no
zone: a KV cluster on it takes its zone from the seed's InfraEnvs, ADR-0069). A Customer MCE and a
tenant's cluster keep their rules (``names.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from wingman_core.domain.cluster_kinds import (
    HostedClusterKind,
    MceKind,
    hosted_cluster_kind,
    mce_kind,
)
from wingman_day1.domain.errors import InvalidInputError
from wingman_day1.domain.names import (
    ClusterNaming,
    Env,
    MceNaming,
    describe_cluster,
    describe_mce,
    dns_label_problems,
)
from wingman_day1.domain.paths import ClusterRef

_ENVS = "|".join(e.value for e in Env)
_SEGMENT = r"[a-z0-9]+"
_LETTER = r"[a-z]"


def describe_hub(name: str, *, site: str) -> MceNaming:
    """An MCE-level folder's name, read by its kind: a seed's or a Customer MCE's."""
    if mce_kind(name) is MceKind.SEED:
        return describe_seed(name, site=site)
    return describe_mce(name, site=site)


def describe_seed(name: str, *, site: str) -> MceNaming:
    """A seed folder's name against ``ocp4-<lc>-seed-<site>-<zone>-<id>``."""
    site_re = re.escape(site)
    convention = re.match(
        rf"^ocp4-(?P<env>{_ENVS})-seed-{site_re}-(?P<zone>{_SEGMENT})-(?P<id>{_LETTER})$", name
    )
    if convention:
        return MceNaming(
            name, site, Env(convention["env"]), convention["id"], (), zone=convention["zone"]
        )
    expected = f"ocp4-<lc>-seed-{site}-<zone>-<id>"
    hub_shaped = re.match(rf"^ocp4-(?P<env>{_ENVS})-mce-seed-{site_re}-(?P<id>{_LETTER})$", name)
    if hub_shaped:
        problem = (
            f"seed {name!r} is named ocp4-<lc>-mce-seed-<site>-<id>, a shape no written source "
            f"gives, not as the convention's {expected}; its name carries no zone"
        )
        return MceNaming(name, site, Env(hub_shaped["env"]), hub_shaped["id"], (problem,))
    deployed = re.match(rf"^ocp4-seed-{site_re}-(?P<zone>{_SEGMENT})$", name)
    if deployed:
        problem = (
            f"seed {name!r} is named as the deployed workflows find a seed "
            f"(ocp4-seed-<site>-<zone>), not as the convention's {expected}"
        )
        return MceNaming(name, site, None, None, (problem,), zone=deployed["zone"])
    return MceNaming(name, site, None, None, (f"seed {name!r} does not follow {expected}",))


def describe_kv_cluster(stem: str, *, site: str) -> ClusterNaming:
    """A KV cluster file's stem against ``ocp4-<lc>-kv-<site>-<zone>-<id>``."""
    problems = dns_label_problems(stem, what="cluster name")
    site_re = re.escape(site)
    convention = re.match(
        rf"^ocp4-(?P<env>{_ENVS})-kv-{site_re}-(?P<zone>{_SEGMENT})-(?P<id>{_LETTER})$", stem
    )
    if convention:
        env, zone, sequence = Env(convention["env"]), convention["zone"], convention["id"]
        return ClusterNaming(stem, site, env, "kv", sequence, tuple(problems), zone=zone)
    expected = f"ocp4-<lc>-kv-{site}-<zone>-<id>"
    deployed = re.match(rf"^ocp4-kubevirt-{site_re}-(?P<zone>{_SEGMENT})(?:-.+)?$", stem)
    if deployed:
        problems.append(
            f"KV cluster {stem!r} is named as the deployed workflows name one "
            f"(ocp4-kubevirt-<site>-<zone>), not as the convention's {expected}"
        )
        zone = deployed["zone"]
        return ClusterNaming(stem, site, None, None, None, tuple(problems), zone=zone)
    problems.append(f"KV cluster {stem!r} does not follow {expected}")
    return ClusterNaming(stem, site, None, None, None, tuple(problems))


def customer_mces(names: Iterable[str], *, site: str, env: Env) -> list[str]:
    """The Customer MCEs among ``names`` whose name gives ``env``: placement's candidates.

    A seed hosts KV clusters only, so it is never one, by its kind (ADR-0050's
    amendment by ADR-0067), whatever its name says.
    """
    return [
        m for m in names if mce_kind(m) is MceKind.MCE and describe_mce(m, site=site).env is env
    ]


def require_customer_mce(mce: str) -> None:
    """Refuse a seed as a new tenant cluster's MCE (``InvalidInputError``, 422)."""
    if mce_kind(mce) is MceKind.SEED:
        raise InvalidInputError(
            f"{mce!r} is a seed: it hosts KV clusters, never a tenant's cluster (ADR-0067)"
        )


def describe_cluster_file(ref: ClusterRef) -> ClusterNaming:
    """A cluster file's stem, read by its kind: a KV cluster's or a tenant's."""
    if hosted_cluster_kind(ref.name, mce=ref.mce) is HostedClusterKind.KV:
        return describe_kv_cluster(ref.name, site=ref.site)
    return describe_cluster(ref.name, site=ref.site)
