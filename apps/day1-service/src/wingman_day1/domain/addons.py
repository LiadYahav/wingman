"""Day2 addons as day1 sees them: what a spec asks for, what was requested, what is installed.

Day1 never writes day2 repos (ADR-0016). At create it records the spec's
addons, with the override values the user chose, in the cluster file's
header (see :mod:`wingman_day1.domain.cluster_file`), so they are not lost;
drift reports each missing addon with those values, and day2 installs it.
A version other than the spec's is reported, not drift (ADR-0025).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class AddonKey:
    """An addon is ``<team>/<name>``: the team's day2 repo and the chart."""

    team: str
    name: str

    def __str__(self) -> str:
        """``team/name``."""
        return f"{self.team}/{self.name}"


@dataclass(frozen=True, slots=True)
class RequestedAddon:
    """An addon the spec asked for at create, with the user's override values."""

    team: str
    name: str
    version: str
    override_values: Mapping[str, object] = field(default_factory=dict)

    @property
    def key(self) -> AddonKey:
        """``team/name``."""
        return AddonKey(self.team, self.name)


@dataclass(frozen=True, slots=True)
class InstalledAddon:
    """An addon day2 reports as installed on a cluster."""

    team: str
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class Day2InstallRequest:
    """An open day2 merge request that installs add-ons on a cluster (one team's)."""

    team: str
    iid: int
    title: str
    web_url: str
    charts: tuple[str, ...]
    """The charts it installs, as its title names them."""


@dataclass(frozen=True, slots=True)
class Day2InstallResult:
    """What asking day2 to install add-ons on a cluster opened: one MR per team, or why not."""

    opened: tuple[Day2InstallRequest, ...]
    failed: tuple[str, ...]
    """One line per team (or for the whole request) whose MR did not open, and why."""


class AddonDriftReason(StrEnum):
    """Why a spec addon counts as drifted. Only a missing addon does (ADR-0025)."""

    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class AddonDrift:
    """A spec addon the cluster does not have; day2 can install it."""

    team: str
    name: str
    reason: AddonDriftReason
    expected_version: str
    override_values: Mapping[str, object] = field(default_factory=dict)
    """What the user asked for at create, so installing it later keeps their values."""


@dataclass(frozen=True, slots=True)
class VersionDifference:
    """A spec addon installed at a version other than the spec names.

    Reported, never fixed (ADR-0025): the cluster follows its team's default
    revision, and moving one cluster to another version is an emergency pin,
    a deliberate day2 action (ADR-0022), not drift repair.
    """

    team: str
    name: str
    spec_version: str
    installed_version: str


@dataclass(frozen=True, slots=True)
class AddonComparison:
    """A spec's addons against what a cluster has installed."""

    missing: tuple[AddonDrift, ...] = ()
    version_differences: tuple[VersionDifference, ...] = ()


def compare_addons(
    expected: Iterable[RequestedAddon],
    installed: Iterable[InstalledAddon],
    *,
    requested: Iterable[RequestedAddon] = (),
) -> AddonComparison:
    """Spec addons that are missing, and those installed at another version.

    Extra installed addons are fine. An addon is matched by ``team/name``:
    two teams may ship charts with the same name.
    """
    installed_by_key = {AddonKey(a.team, a.name): a for a in installed}
    overrides = {r.key: r.override_values for r in requested}
    missing: list[AddonDrift] = []
    differences: list[VersionDifference] = []
    for addon in expected:
        found = installed_by_key.get(addon.key)
        if found is None:
            missing.append(
                AddonDrift(
                    addon.team,
                    addon.name,
                    AddonDriftReason.MISSING,
                    addon.version,
                    overrides.get(addon.key, {}),
                )
            )
        elif found.version != addon.version:
            differences.append(
                VersionDifference(addon.team, addon.name, addon.version, found.version)
            )
    return AddonComparison(tuple(missing), tuple(differences))
