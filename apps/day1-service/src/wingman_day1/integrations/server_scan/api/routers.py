"""The Server Scan area's routers, all under ``/api/day1/server-scan`` (ADR-0048).

One router per page or resource, each with its own module; ``main`` mounts
them as one entry, so a page adds its router here, not to the composition
root.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from wingman_day1.integrations.server_scan.api import area, jobs, skill

ROUTERS: Final[tuple[APIRouter, ...]] = (
    area.router,
    jobs.router,
    skill.router,
)
