"""The fake server-scan's Fetch now: which servers it cannot read now (ADR-0048, 3.46.0).

A port of the refusals in ``ServerRefreshService`` (team-redbull/server-scan's
``backend/app/application/services/server_refresh.py``, v6.5.0, its
ADR-0064): a server no vendor manager collected, and one whose manager the
API holds no connection for, are ``SERVER_REFRESH_UNSUPPORTED``, in its
words. A standalone Redfish BMC's credentials stay with its CronJob, so the
API never reads one; the fake's other collectors answer, and their servers
come back unchanged (``changed: false``), as a fake manager's do.

What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
"""

from __future__ import annotations

from typing import Final

from wingman_day1.domain.servers import ServerRow

NOT_CONNECTED: Final = frozenset({"REDFISH_STANDALONE"})
"""The collectors whose connection stays CronJob-only, so the API cannot read their servers."""


def refusal(row: ServerRow) -> str | None:
    """server-scan's words for why it cannot read ``row`` from its manager now; ``None``: it can."""
    if row.source_provider is None:
        return (
            f"server-scan: {row.name!r} was not collected by a vendor manager, so there is "
            "nothing to read it from. (fake)"
        )
    if row.source_provider in NOT_CONNECTED:
        return (
            f"server-scan: The API is not connected to the {row.source_provider} manager that "
            f"collects {row.name!r}; run its collector job instead. (fake)"
        )
    return None
