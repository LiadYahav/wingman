"""The Server Scan area's guards: a call server-scan keeps for a role, off here (ADR-0048).

Each page that needs server-scan's auditor or admin token is given a
``detail`` at start-up (``domain.server_scan_tokens.token_detail``): why it
cannot work in this deployment, or ``None``. These raise it before any call
goes out, as the route's ``501 FEATURE_DISABLED`` naming the setting.
"""

from __future__ import annotations

from wingman_day1.domain.errors import ServerScanAuditOffError, ServerScanWritesOffError


def audited(detail: str | None) -> None:
    """The audit trail's guard (History, Events): the auditor token's ``detail``."""
    if detail is not None:
        raise ServerScanAuditOffError(detail)


def admin_only(detail: str | None) -> None:
    """The admin token's guard (maintenance, Jobs): its ``detail``."""
    if detail is not None:
        raise ServerScanWritesOffError(detail)
