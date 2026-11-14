"""server-scan's hardware catalog for the Confs page (ADR-0048's 3.29.0 amendment).

``GET /api/v1/confs`` with the viewer token (server-scan serves it to any
authenticated caller): every conf, unpaged, in server-scan's natural
``conf_id`` order, and the ids it could not read. Read strictly into the
domain's model of server-scan's shape (``domain/server_scan_confs.py``): an
answer that does not fit is "unavailable", never a blank.
"""

from __future__ import annotations

from typing import Final

import httpx

from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.infrastructure.server_scan_record import check, fetch, parsed

CONFS_PATH: Final = "/api/v1/confs"


async def read_confs(client: httpx.AsyncClient) -> ConfList:
    """Every conf server-scan can read, and the ids of those it cannot."""
    what = "listing confs"
    response = await fetch(client, CONFS_PATH, what=what)
    check(response, what=what)
    return parsed(ConfList, response, "malformed confs")
