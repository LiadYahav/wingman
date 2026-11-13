"""The Server Scan area: server-scan's pages, read through day1 (ADR-0048).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until
RBAC). With ``SERVER_SCAN_URL`` empty every route answers 501; server-scan
failing or refusing the token is 502. The contract:
``docs/notes/2026-11-13-server-scan-area-api.md``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from wingman_core.web.auth import AdminUser
from wingman_day1.api.conditional import conditional_json, weak_etag
from wingman_day1.api.deps import ServerScan
from wingman_day1.api.v1.server_scan_schemas import SitesOut
from wingman_day1.api.v1.server_scan_servers_schemas import ServerRowsOut
from wingman_day1.domain.server_scan_servers import FleetRows

router = APIRouter(prefix="/api/day1/server-scan", tags=["server-scan"])


@router.get("/sites")
async def server_scan_sites(service: ServerScan, user: AdminUser) -> SitesOut:
    """Every configured site and the fleet, as server-scan counts them, in its shape."""
    return SitesOut.of(await service.sites())


class EncodedFleet:
    """The last fleet's answer, encoded once and answered while the cache holds that fleet.

    The rows (about 2 MB for 3,000 servers) come from the one cached read of
    server-scan, the same object until it changes (ADR-0048), so polling pages
    cost neither an encode nor a hash until then.
    """

    def __init__(self) -> None:
        """Nothing encoded yet."""
        self._fleet: FleetRows | None = None
        self._body = b""
        self._etag = ""

    def of(self, fleet: FleetRows) -> tuple[bytes, str]:
        """``fleet``'s answer and its weak ETag."""
        if fleet is not self._fleet:
            self._body = ServerRowsOut.of(fleet).model_dump_json().encode()
            self._etag = weak_etag(self._body)
            self._fleet = fleet
        return self._body, self._etag


_ENCODED = EncodedFleet()


@router.get("/servers", response_model=ServerRowsOut)
async def server_scan_servers(request: Request, service: ServerScan, user: AdminUser) -> Response:
    """The fleet as server-scan's rows; ``304`` when the ``If-None-Match`` is current."""
    body, etag = _ENCODED.of(await service.servers())
    return conditional_json(request, body, etag)
