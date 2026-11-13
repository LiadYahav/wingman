"""The Servers page's response bodies (docs/notes/2026-11-13-server-scan-area-api.md §8.3).

In server-scan's own shapes (``ServerRow``, ``MaintenanceFlag``,
``ReservationFlag`` and ``ServerRowsResponse`` in its
``backend/app/api/v1/schemas.py`` at 92146d3), so server-scan's TypeScript
types and pure functions apply as they are (ADR-0048, decision 18 of the
single-pane plan).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from wingman_day1.domain.server_scan_servers import FleetRows
from wingman_day1.domain.servers import ServerRow


class MaintenanceFlagOut(BaseModel):
    """A row's maintenance: whether, why, and who (as server-scan records the actor)."""

    enabled: bool
    reason: str | None
    created_by: str | None


class ReservationFlagOut(BaseModel):
    """A row's install lock; every field null when it is not held."""

    held: bool
    holder: str | None
    mce_cluster: str | None
    infra_env: str | None
    expires_at: datetime | None


class ServerRowOut(BaseModel):
    """One server, every field server-scan's row has."""

    id: str
    name: str
    vendor: str | None
    model: str | None
    site_id: str | None
    source_provider: str | None
    installation_type: str | None
    health: str
    maintenance: MaintenanceFlagOut
    reservation: ReservationFlagOut
    openshift_state: str
    cluster_name: str | None
    mce_name: str | None
    openshift_reported_name: str | None
    contested_with: str | None
    profile_template_name: str | None
    last_seen_at: datetime | None
    stale: bool
    reachable: bool
    serial: str | None
    bmc_host: str | None
    macs: list[str]

    @classmethod
    def of(cls, row: ServerRow) -> ServerRowOut:
        """From the domain."""
        return cls(
            id=row.id,
            name=row.name,
            vendor=row.vendor,
            model=row.model,
            site_id=row.site,
            source_provider=row.source_provider,
            installation_type=row.installation_type,
            health=row.health,
            maintenance=MaintenanceFlagOut(
                enabled=row.maintenance,
                reason=row.maintenance_reason,
                created_by=row.maintenance_by,
            ),
            reservation=ReservationFlagOut(
                held=row.reserved_by is not None,
                holder=row.reserved_by,
                mce_cluster=row.reserved_for_mce,
                infra_env=row.reserved_for_infra_env,
                expires_at=row.reserved_until,
            ),
            openshift_state=row.state,
            cluster_name=row.cluster_name,
            mce_name=row.mce,
            openshift_reported_name=row.reported_name,
            contested_with=row.contested_with,
            profile_template_name=row.profile_template,
            last_seen_at=row.last_seen_at,
            stale=row.stale,
            reachable=row.reachable,
            serial=row.serial,
            bmc_host=row.bmc_host,
            macs=list(row.macs),
        )


class ServerRowsOut(BaseModel):
    """``GET /api/day1/server-scan/servers``: server-scan's ``GET /api/v1/servers/rows``, typed."""

    items: list[ServerRowOut]
    generated_at: datetime | None

    @classmethod
    def of(cls, fleet: FleetRows) -> ServerRowsOut:
        """From the domain, in server-scan's order."""
        return cls(
            items=[ServerRowOut.of(row) for row in fleet.rows], generated_at=fleet.generated_at
        )
