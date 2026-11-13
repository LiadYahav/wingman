"""The fake server-scan's sites: its rows counted by server-scan's own rules (ADR-0048).

A port of ``_pivot``, ``_accumulate`` and ``_empty_*`` in
``backend/app/api/v1/sites.py`` (team-redbull/server-scan at 92146d3), so the
demo's Sites cards agree with the fake fleet's servers:

- every configured site, in the catalog's order, then ``unassigned``; a site
  with no servers is listed at 0;
- a server whose site is ``None`` or no longer configured counts as
  ``unassigned``; an unknown health as ``UNKNOWN``; an unknown or missing
  installation type as ``UNCLASSIFIED``; an unknown state as ``AVAILABLE``;
  an unknown vendor is counted in the total but in no vendor entry, so every
  slice adds up to the fleet.

The catalog is server-scan's ``INVENTORY_SITES`` (``code:Display Name``); the
fake fleet's is the ``sites`` list of ``dev/fleet-fixtures/servers.yaml``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.server_scan_sites import (
    Breakdown,
    FleetSites,
    FleetSummary,
    SiteStats,
    VendorCount,
)
from wingman_day1.domain.servers import ServerRow

VENDORS: Final = ("dell", "cisco", "hp", "standalone", "kubevirt")
HEALTH: Final = ("UNKNOWN", "HEALTHY", "WARNING", "MAJOR", "CRITICAL")
INSTALLATION_TYPES: Final = ("HOSTED_CLUSTER", "MCE", "UPI", "UNCLASSIFIED")
OPENSHIFT_STATES: Final = ("AVAILABLE", "INSTALLED", "INSTALLED_TO_INVENTORY")
UNASSIGNED: Final = "unassigned"

SiteName = tuple[str, str]
"""One catalog entry: the site code in server names, and the name the UI shows."""


@dataclass(slots=True)
class _Counts:
    """A breakdown being counted (server-scan builds its mutable models the same way)."""

    total: int = 0
    vendors: dict[str, int] = field(default_factory=lambda: dict.fromkeys(VENDORS, 0))
    health: dict[str, int] = field(default_factory=lambda: dict.fromkeys(HEALTH, 0))
    in_maintenance: int = 0

    def add(self, row: ServerRow) -> None:
        self.total += 1
        if row.maintenance:
            self.in_maintenance += 1
        self.health[row.health if row.health in self.health else "UNKNOWN"] += 1
        if row.vendor in self.vendors:
            self.vendors[row.vendor] += 1

    def freeze(self) -> Breakdown:
        return Breakdown(
            total=self.total,
            by_vendor=tuple(VendorCount(vendor=v, count=n) for v, n in self.vendors.items()),
            by_health=dict(self.health),
            in_maintenance=self.in_maintenance,
        )


@dataclass(slots=True)
class _Sliced:
    """A site or the fleet being counted, with its per-type and per-state slices."""

    counts: _Counts = field(default_factory=_Counts)
    types: dict[str, _Counts] = field(
        default_factory=lambda: {name: _Counts() for name in INSTALLATION_TYPES}
    )
    states: dict[str, _Counts] = field(
        default_factory=lambda: {name: _Counts() for name in OPENSHIFT_STATES}
    )

    def add(self, row: ServerRow) -> None:
        self.counts.add(row)
        self.types[
            row.installation_type if row.installation_type in self.types else "UNCLASSIFIED"
        ].add(row)
        self.states[row.state if row.state in self.states else "AVAILABLE"].add(row)

    def freeze(self) -> FleetSummary:
        counts = self.counts.freeze()
        return FleetSummary(
            total=counts.total,
            by_vendor=counts.by_vendor,
            by_health=counts.by_health,
            in_maintenance=counts.in_maintenance,
            by_installation_type={name: c.freeze() for name, c in self.types.items()},
            by_openshift_state={name: c.freeze() for name, c in self.states.items()},
        )


def count_sites(rows: Iterable[ServerRow], catalog: Sequence[SiteName]) -> FleetSites:
    """``GET /api/v1/sites`` for ``rows``, over ``catalog`` (server-scan's ``_pivot``)."""
    names = dict(catalog)
    names[UNASSIGNED] = "Unassigned"
    sites = {code: _Sliced() for code in names}
    fleet = _Sliced()
    for row in rows:
        site = row.site if row.site in sites else UNASSIGNED
        sites[site].add(row)
        fleet.add(row)
    return FleetSites(
        sites=tuple(_site(code, names[code], sliced) for code, sliced in sites.items()),
        fleet=fleet.freeze(),
    )


def catalog_of(rows: Iterable[ServerRow]) -> tuple[SiteName, ...]:
    """The rows' own sites, sorted, named as server-scan names a code it has no name for."""
    codes = sorted({row.site for row in rows if row.site and row.site != UNASSIGNED})
    return tuple((code, title_case(code)) for code in codes)


def title_case(code: str) -> str:
    """``bat-yam`` is ``Bat Yam`` (server-scan's ``_title_case``)."""
    return " ".join(part.capitalize() for part in code.split("-") if part)


def load_site_catalog(path: Path) -> tuple[SiteName, ...]:
    """The fixture's ``sites``: ``[{code, name}]``, server-scan's ``INVENTORY_SITES``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = raw.get("sites") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise TypeError(f"{path}: expected a 'sites' list")
    catalog: list[SiteName] = []
    for entry in entries:
        code, name = str(entry["code"]), entry.get("name")
        catalog.append((code, str(name) if name else title_case(code)))
    return tuple(catalog)


def _site(code: str, name: str, sliced: _Sliced) -> SiteStats:
    summary = sliced.freeze()
    return SiteStats(
        site_id=code,
        name=name,
        total=summary.total,
        by_vendor=summary.by_vendor,
        by_health=summary.by_health,
        in_maintenance=summary.in_maintenance,
        by_installation_type=summary.by_installation_type,
        by_openshift_state=summary.by_openshift_state,
    )
