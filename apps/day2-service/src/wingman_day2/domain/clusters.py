"""The four kinds of day2 destination and the identity Wingman gives each (ADR-0020).

| Kind   | Team repo folder                         | OCP version from                     |
|--------|------------------------------------------|--------------------------------------|
| hub    | ``defaults/hub/``                        | none (version-less)                  |
| mce    | ``sites/<s>/<env>/mces/<mce>/in-cluster/`` | day1 ``sites/<s>/mces/<mce>/version.yaml`` |
| hosted | ``sites/<s>/<env>/mces/<mce>/<cluster>/`` | day1 ``.../hostedClusters/<cluster>.yaml`` |
| upi    | ``sites/<s>/<env>/upi/<cluster>/``       | optional ``version.yaml`` there      |

A cluster id carries everything a path needs, so a write never guesses:
``hub``, ``mce:<site>:<env>:<mce>``, ``hosted:<site>:<env>:<mce>:<cluster>``,
``upi:<site>:<env>:<cluster>``. ``env`` comes from the path, never from a
file; it may be empty only for a day1 cluster that no team repo places and
whose name does not follow the naming convention, and such a cluster cannot
be written to until someone places it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.domain.git import RepoPath
from wingman_day2.domain.errors import InvalidClusterIdError

ALLOWED_ENVS: Final = frozenset({"prod", "prep", "test"})
IN_CLUSTER: Final = "in-cluster"
"""Every Argo's name for its own cluster: the MCE hub on an MCE's Argo, prod-hub on prod-hub's."""
HUB_NAME: Final = "prod-hub"
HUB_ID: Final = "hub"
UPI_ARGO_NAMESPACE: Final = "openshift-gitops-upi"
_SEPARATOR: Final = ":"


class ClusterKind(StrEnum):
    """Where a chart is deployed; each kind has its own folder and value stack."""

    HUB = "hub"
    MCE = "mce"
    HOSTED = "hosted"
    UPI = "upi"


class DefaultsScope(StrEnum):
    """A ``defaults/<scope>/`` folder: charts deployed to every destination of one kind."""

    HUB = "hub"
    MCES = "mces"
    HOSTED_CLUSTERS = "hosted-clusters"
    UPI = "upi"


_SCOPE_OF: Final = {
    ClusterKind.HUB: DefaultsScope.HUB,
    ClusterKind.MCE: DefaultsScope.MCES,
    ClusterKind.HOSTED: DefaultsScope.HOSTED_CLUSTERS,
    ClusterKind.UPI: DefaultsScope.UPI,
}

# Which of site/env/mce a kind carries. env may be empty for mce/hosted (see module docstring).
_REQUIRED: Final = {
    ClusterKind.HUB: frozenset[str](),
    ClusterKind.MCE: frozenset({"site", "mce"}),
    ClusterKind.HOSTED: frozenset({"site", "mce"}),
    ClusterKind.UPI: frozenset({"site", "env"}),
}
_FORBIDDEN: Final = {
    ClusterKind.HUB: frozenset({"site", "env", "mce"}),
    ClusterKind.MCE: frozenset[str](),
    ClusterKind.HOSTED: frozenset[str](),
    ClusterKind.UPI: frozenset({"mce"}),
}


def check_segment(value: str, what: str) -> str:
    """``value`` if it is usable as one path segment and inside an id; raises otherwise."""
    try:
        RepoPath.of(value)
    except InvalidRepoPathError as exc:
        raise InvalidClusterIdError(f"invalid {what} {value!r}") from exc
    if _SEPARATOR in value or value.startswith("."):
        raise InvalidClusterIdError(f"invalid {what} {value!r}")
    return value


@dataclass(frozen=True, slots=True, order=True)
class ClusterRef:
    """One day2 destination. Build it with the class methods or :meth:`parse`."""

    kind: ClusterKind
    name: str
    site: str = ""
    env: str = ""
    mce: str = ""

    def __post_init__(self) -> None:
        """Reject a combination no destination has."""
        for field_name in ("site", "env", "mce"):
            value = getattr(self, field_name)
            if field_name in _REQUIRED[self.kind] and not value:
                raise InvalidClusterIdError(f"a {self.kind} cluster needs a {field_name}")
            if field_name in _FORBIDDEN[self.kind] and value:
                raise InvalidClusterIdError(f"a {self.kind} cluster has no {field_name}")
            if value:
                check_segment(value, field_name)
        check_segment(self.name, "cluster name")
        if self.kind is ClusterKind.HUB and self.name != HUB_NAME:
            raise InvalidClusterIdError(f"the hub is named {HUB_NAME}")
        if self.kind is ClusterKind.MCE and self.name != self.mce:
            raise InvalidClusterIdError("an MCE hub is named after its MCE")
        if self.kind in (ClusterKind.HOSTED, ClusterKind.UPI) and self.name == IN_CLUSTER:
            raise InvalidClusterIdError(f"{IN_CLUSTER} is not a cluster name")

    @classmethod
    def hub(cls) -> ClusterRef:
        """The prod-hub management cluster."""
        return cls(ClusterKind.HUB, HUB_NAME)

    @classmethod
    def mce_hub(cls, site: str, env: str, mce: str) -> ClusterRef:
        """An MCE hub itself (its ``in-cluster`` folder)."""
        return cls(ClusterKind.MCE, mce, site=site, env=env, mce=mce)

    @classmethod
    def hosted(cls, site: str, env: str, mce: str, name: str) -> ClusterRef:
        """A hosted cluster of an MCE."""
        return cls(ClusterKind.HOSTED, name, site=site, env=env, mce=mce)

    @classmethod
    def upi(cls, site: str, env: str, name: str) -> ClusterRef:
        """A standalone (UPI) cluster."""
        return cls(ClusterKind.UPI, name, site=site, env=env)

    @classmethod
    def parse(cls, text: str) -> ClusterRef:
        """The ref an :attr:`id` names. Raises ``InvalidClusterIdError``."""
        if text == HUB_ID:
            return cls.hub()
        kind_text, _, rest = text.partition(_SEPARATOR)
        parts = rest.split(_SEPARATOR)
        try:
            kind = ClusterKind(kind_text)
        except ValueError:
            raise InvalidClusterIdError(f"not a cluster id: {text!r}") from None
        shapes = {ClusterKind.MCE: 3, ClusterKind.HOSTED: 4, ClusterKind.UPI: 3}
        if kind is ClusterKind.HUB or len(parts) != shapes[kind]:
            raise InvalidClusterIdError(f"not a cluster id: {text!r}")
        if kind is ClusterKind.MCE:
            return cls.mce_hub(*parts)
        if kind is ClusterKind.HOSTED:
            return cls.hosted(*parts)
        return cls.upi(*parts)

    @property
    def id(self) -> str:
        """The stable, URL-safe identity used by the API."""
        if self.kind is ClusterKind.HUB:
            return HUB_ID
        parts = {
            ClusterKind.MCE: (self.site, self.env, self.mce),
            ClusterKind.HOSTED: (self.site, self.env, self.mce, self.name),
            ClusterKind.UPI: (self.site, self.env, self.name),
        }[self.kind]
        return _SEPARATOR.join((str(self.kind), *parts))

    @property
    def argo_cluster(self) -> str:
        """The leaf Application's destination name: ``in-cluster`` for hubs, else the cluster."""
        return IN_CLUSTER if self.kind in (ClusterKind.HUB, ClusterKind.MCE) else self.name

    @property
    def argo_instance(self) -> str:
        """The Argo CD that holds this cluster's leaf apps (the MCE's own Argo for MCEs and HCs)."""
        if self.kind is ClusterKind.HUB:
            return HUB_NAME
        if self.kind is ClusterKind.UPI:
            return f"{HUB_NAME}-upi"
        return self.mce

    @property
    def defaults_scope(self) -> DefaultsScope:
        """The fleet-defaults folder whose charts reach this kind of destination."""
        return _SCOPE_OF[self.kind]

    @property
    def exclusion_key(self) -> str | None:
        """The name ``exclusions.yaml`` lists to opt this destination out (none for the hub)."""
        if self.kind is ClusterKind.HUB:
            return None
        return self.mce if self.kind is ClusterKind.MCE else self.name

    @property
    def env_allowed(self) -> bool:
        """Whether the env is one the platform accepts (the hub has none and needs none)."""
        return self.kind is ClusterKind.HUB or self.env in ALLOWED_ENVS

    def __str__(self) -> str:
        """The id."""
        return self.id


def env_from_name(name: str) -> str:
    """The env the convention ``ocp4-<env>-<name>-<site>[-<seq>]`` puts in a name, or ``""``."""
    parts = name.split("-")
    if len(parts) >= 3 and parts[0] == "ocp4" and parts[1] in ALLOWED_ENVS:
        return parts[1]
    return ""
