"""A server's page's response bodies (docs/notes/2026-11-13-server-scan-area-api.md §9.4).

The record, the VM host and a History page are the domain's models of
server-scan's own shapes (``domain/record.py``,
``events.py``), sent as they are, so server-scan's TypeScript
applies (ADR-0048, decision 18 of the single-pane plan). The record adds
whether the maintenance toggle, Fetch now and History work in this
deployment; Fetch now answers it too.

What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
"""

from __future__ import annotations

from wingman_day1.integrations.server_scan.domain.record import ServerRecord
from wingman_day1.integrations.server_scan.domain.servers import server_type_of


class ServerRecordOut(ServerRecord):
    """``GET /api/day1/server-scan/servers/{id}``: server-scan's record, typed.

    Plus whether the maintenance toggle (§8.4), Fetch now (§9.9: on at all,
    and working) and History (§9.5) work here, and why not. ``server_type`` is server-scan's, or its
    rule over the vendor when an older server-scan did not send it.
    """

    server_type: str
    maintenance_available: bool
    maintenance_detail: str | None
    refresh_enabled: bool
    refresh_available: bool
    refresh_detail: str | None
    history_available: bool
    history_detail: str | None

    @classmethod
    def of(
        cls,
        record: ServerRecord,
        *,
        maintenance_detail: str | None,
        history_detail: str | None,
        refresh_detail: str | None = None,
        refresh_enabled: bool = False,
    ) -> ServerRecordOut:
        """The record with this deployment's three switches."""
        kind = record.server_type or server_type_of(record.identity.vendor)
        return cls(
            **dict(record.model_copy(update={"server_type": kind})),
            maintenance_available=maintenance_detail is None,
            maintenance_detail=maintenance_detail,
            refresh_enabled=refresh_enabled,
            refresh_available=refresh_enabled and refresh_detail is None,
            refresh_detail=refresh_detail,
            history_available=history_detail is None,
            history_detail=history_detail,
        )
