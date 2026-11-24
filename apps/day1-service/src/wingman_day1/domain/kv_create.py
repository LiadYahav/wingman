"""A new KV cluster on a seed, the same as the ones before it (ADR-0069).

A KV cluster has no flavor and no form: an admin picks a seed, and Wingman
fills the file from the platform's rules and the KV clusters already there.

- **The name** is ``ocp4-<lc>-kv-<site>-<zone>-<id>`` with the lowest ``<id>``
  letter no cluster file and no open provision merge request has (acceptance
  P10), ``<lc>`` the seed's lifecycle (:func:`next_kv_name`).
- **The zone** is the seed name's; a seed whose name gives none takes it from
  its bare-metal InfraEnvs, ``<flavor>-mtl-<zone>`` (naming convention §1):
  :func:`zones_of`.
- **One NodePool** from that zone's bare-metal pool (:func:`zone_pools`),
  ``replicas`` 3 by default (acceptance P1), at most ``maxNodes`` (40), its
  ``nodeLabels`` the zone.
- **The rest from a model**, so every KV cluster is the same: the newest KV
  cluster on the same seed, else the site, else any (:func:`choose_model`);
  its owner, its first NodePool's configs and tuning profiles
  (:func:`kv_inputs`).

Pure: the application reads the tree, the files and the InfraEnvs.
"""

from __future__ import annotations

import re
import string
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.cluster_file import ClusterValues
from wingman_day1.domain.kind_names import describe_kv_cluster
from wingman_day1.domain.kv_clusters import MAX_KV_WORKERS, ZONE_LABEL
from wingman_day1.domain.machine_configs import GENERIC_HARDWARE, NETWORK_CONFIG
from wingman_day1.domain.names import Env, HostedClusterNaming, create_length_problems
from wingman_day1.domain.openshift_versions import bare_release
from wingman_day1.domain.owners import OWNER_INPUTS
from wingman_day1.domain.paths import ClusterRef

DEFAULT_KV_WORKERS: Final = 3
"""A new KV cluster's workers: acceptance P1's three, inside the policy's standby 1-5."""
STANDBY_WORKERS: Final = (1, 5)
"""The capacity policy's ``standbyWorkers``: what a standby KV cluster is built with (AD31)."""
OWNER_FIELDS: Final = tuple(name.removeprefix("owner_") for name in OWNER_INPUTS)
"""``merkaz``, ``anaf``, ``mador``: the file's ``owner`` keys."""

_POOL = re.compile(r"^(?P<flavor>[a-z0-9]+)-mtl-(?P<zone>[a-z0-9]+)$")
"""A bare-metal InfraEnv by the naming convention: ``<flavor>-mtl-<zone>``."""


def pool_zone(infra_env: str) -> str | None:
    """The zone of a bare-metal InfraEnv ``<flavor>-mtl-<zone>``; ``None`` for any other name."""
    found = _POOL.match(infra_env)
    return found["zone"] if found else None


def zones_of(infra_envs: Iterable[str]) -> tuple[str, ...]:
    """The zones the bare-metal InfraEnvs serve, sorted, each once."""
    return tuple(sorted({z for name in infra_envs if (z := pool_zone(name)) is not None}))


def zone_pools(infra_envs: Iterable[str], zone: str) -> tuple[str, ...]:
    """The bare-metal InfraEnvs of ``zone``, sorted, each once."""
    return tuple(sorted({name for name in infra_envs if pool_zone(name) == zone}))


def kv_stem(env: Env, *, site: str, zone: str, letter: str) -> str:
    """``ocp4-<lc>-kv-<site>-<zone>-<id>``."""
    return f"ocp4-{env.value}-kv-{site}-{zone}-{letter}"


def next_kv_name(env: Env, *, site: str, zone: str, taken: Collection[str]) -> str | None:
    """The lowest ``<id>`` letter's name no name in ``taken`` has; ``None`` when all 26 are."""
    for letter in string.ascii_lowercase:
        name = kv_stem(env, site=site, zone=zone, letter=letter)
        if name not in taken:
            return name
    return None


def kv_name_problems(name: str, *, site: str, naming: HostedClusterNaming) -> list[str]:
    """Why ``name`` cannot be a new KV cluster's: its kind's rule, provision-cluster's length."""
    return [*describe_kv_cluster(name, site=site).problems, *create_length_problems(name, naming)]


def workers_problems(workers: int) -> list[str]:
    """A KV cluster holds 1 to ``maxNodes`` workers (AD31)."""
    if 1 <= workers <= MAX_KV_WORKERS:
        return []
    return [f"workers must be 1 to {MAX_KV_WORKERS} (the policy's maxNodes); got {workers}"]


@dataclass(frozen=True, slots=True)
class KvModel:
    """An existing KV cluster a new one copies: its owner, configs and tuning profiles."""

    ref: ClusterRef
    owner: Mapping[str, str]
    """The ``owner`` keys it has of ``merkaz``, ``anaf`` and ``mador``, as text."""
    configs: tuple[str, ...]
    """Its first NodePool's machine configs, as written."""
    tuning_config: object
    """Its first NodePool's ``tuningConfig``, as written (``None`` when it has none)."""
    infra_envs: tuple[str, ...]
    """Every NodePool's ``infraEnvName``: the pools it draws from, first one first."""

    @property
    def letter(self) -> str:
        """Its ``<id>`` letter; empty for a name off the convention."""
        return describe_kv_cluster(self.ref.name, site=self.ref.site).sequence or ""


def model_of(ref: ClusterRef, values: ClusterValues) -> KvModel:
    """What a KV cluster's file gives a new one."""
    owner = values.owner or {}
    first = values.nodepools[0] if values.nodepools else None
    return KvModel(
        ref=ref,
        owner={
            key: str(owner[key])
            for key in OWNER_FIELDS
            if isinstance(owner.get(key), str | int) and not isinstance(owner.get(key), bool)
        },
        configs=first.configs if first else (),
        tuning_config=first.tuning_config if first else None,
        infra_envs=tuple(p.infra_env_name for p in values.nodepools if p.infra_env_name),
    )


def choose_model(models: Sequence[KvModel], *, seed: str, site: str) -> KvModel | None:
    """The newest KV cluster (highest ``<id>`` letter) on ``seed``, else at ``site``, else any."""
    for nearby in (
        [m for m in models if (m.ref.site, m.ref.mce) == (site, seed)],
        [m for m in models if m.ref.site == site],
        list(models),
    ):
        if nearby:
            return max(nearby, key=lambda m: (m.letter, m.ref.name))
    return None


def owner_gaps(owner: Mapping[str, str]) -> list[str]:
    """The owner keys a new file needs and ``owner`` lacks."""
    return [key for key in OWNER_FIELDS if not owner.get(key)]


def _config_entry(name: str, model_cluster: str) -> dict[str, str]:
    """A model's config as an input: its own network config becomes the new cluster's."""
    if name == NETWORK_CONFIG:
        return {"name": NETWORK_CONFIG, "hardware": GENERIC_HARDWARE}
    own = f"{NETWORK_CONFIG}-{model_cluster}-"
    if name.startswith(own) and len(name) > len(own):
        return {"name": NETWORK_CONFIG, "hardware": name.removeprefix(own)}
    return {"name": name}


@dataclass(frozen=True, slots=True)
class KvPool:
    """The one NodePool a new KV cluster gets."""

    infra_env: str
    workers: int
    zone: str


def kv_inputs(
    pool: KvPool, *, owner: Mapping[str, str], model: KvModel | None, model_cluster: str
) -> dict[str, object]:
    """The template's inputs for a new KV cluster; ``model_cluster`` is the model's clusterName.

    The model's network config (``nm-conf-<its clusterName>-<hw>``) is given
    back as ``{name: nm-conf, hardware: <hw>}``, so it is expanded for the new
    cluster.
    """
    nodepool: dict[str, object] = {
        "infra_env": pool.infra_env,
        "replicas": pool.workers,
        "node_labels": {ZONE_LABEL: pool.zone},
    }
    if model is not None and model.configs:
        nodepool["configs"] = [_config_entry(name, model_cluster) for name in model.configs]
    if model is not None and model.tuning_config not in (None, "", []):
        nodepool["tuning_config"] = model.tuning_config
    owners = {f"owner_{key}": owner[key] for key in OWNER_FIELDS if key in owner}
    return {**owners, "nodepools": [nodepool]}


def version_choices(default: str | None, offered: Sequence[str]) -> tuple[str, ...]:
    """The releases the seed offers, newest first, its default spelled as its values.yaml does."""
    return tuple(default if default and bare_release(default) == v else v for v in offered)


def default_version(default: str | None, offered: Sequence[str]) -> str | None:
    """The seed's default ``mastertag`` when it offers it, else its newest release."""
    choices = version_choices(default, offered)
    if default in choices:
        return default
    return choices[0] if choices else None
