"""Day2 addons as day1 sees them: what a spec asks for, what was requested, what is installed.

Day1 never writes day2 repos (ADR-0016). At create it records the spec's
addons, with the override values the user chose, in the cluster file's
header (see :mod:`wingman_day1.domain.cluster_file`), so they are not lost;
drift reports each missing addon with those values, and day2 installs it.
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


class AddonDriftReason(StrEnum):
    """Why a spec addon counts as drifted."""

    MISSING = "missing"
    VERSION_MISMATCH = "version_mismatch"


@dataclass(frozen=True, slots=True)
class AddonDrift:
    """One spec addon that is not installed as the spec says."""

    team: str
    name: str
    reason: AddonDriftReason
    expected_version: str
    installed_version: str = ""
    override_values: Mapping[str, object] = field(default_factory=dict)
    """What the user asked for at create, so installing it later keeps their values."""


def addon_drift(
    expected: Iterable[RequestedAddon],
    installed: Iterable[InstalledAddon],
    *,
    requested: Iterable[RequestedAddon] = (),
) -> list[AddonDrift]:
    """Spec addons that are missing or at another version. Extra installed addons are fine.

    An addon is matched by ``team/name``: two teams may ship charts with the
    same name.
    """
    installed_by_key = {AddonKey(a.team, a.name): a for a in installed}
    overrides = {r.key: r.override_values for r in requested}
    drift: list[AddonDrift] = []
    for addon in expected:
        found = installed_by_key.get(addon.key)
        values = overrides.get(addon.key, {})
        if found is None:
            drift.append(
                AddonDrift(
                    addon.team, addon.name, AddonDriftReason.MISSING, addon.version, "", values
                )
            )
        elif found.version != addon.version:
            drift.append(
                AddonDrift(
                    addon.team,
                    addon.name,
                    AddonDriftReason.VERSION_MISMATCH,
                    addon.version,
                    found.version,
                    values,
                )
            )
    return drift
