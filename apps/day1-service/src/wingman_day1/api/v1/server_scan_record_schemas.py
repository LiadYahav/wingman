"""A server's page's response bodies (docs/notes/2026-11-13-server-scan-area-api.md §9.4).

The record, the VM host and a History page are the domain's models of
server-scan's own shapes (``domain/server_scan_record.py``,
``server_scan_events.py``), sent as they are, so server-scan's TypeScript
applies (ADR-0048, decision 18 of the single-pane plan). The record adds
whether the maintenance toggle and History work in this deployment.
"""

from __future__ import annotations

from wingman_day1.domain.server_scan_record import ServerRecord


class ServerRecordOut(ServerRecord):
    """``GET /api/day1/server-scan/servers/{id}``: server-scan's record, typed.

    Plus whether the maintenance toggle (§8.4) and History (§9.5) work here,
    and why not.
    """

    maintenance_available: bool
    maintenance_detail: str | None
    history_available: bool
    history_detail: str | None

    @classmethod
    def of(
        cls, record: ServerRecord, *, maintenance_detail: str | None, history_detail: str | None
    ) -> ServerRecordOut:
        """The record with this deployment's two switches."""
        return cls(
            **dict(record),
            maintenance_available=maintenance_detail is None,
            maintenance_detail=maintenance_detail,
            history_available=history_detail is None,
            history_detail=history_detail,
        )
