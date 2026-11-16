"""Every router of the day1 API, in the order ``main`` mounts them.

A new area adds its router here, not to the composition root; the server-scan
area and the nodepool catalogues are one entry each (``server_scan_area``,
``nodepool_catalogs``).
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from wingman_day1.api.v1 import approvals as approvals_api
from wingman_day1.api.v1 import audit as audit_api
from wingman_day1.api.v1 import auth as auth_api
from wingman_day1.api.v1 import clusters as clusters_api
from wingman_day1.api.v1 import inventory as inventory_api
from wingman_day1.api.v1 import placement as placement_api
from wingman_day1.api.v1 import quick_links as quick_links_api
from wingman_day1.api.v1 import scale as scale_api
from wingman_day1.api.v1 import segments as segments_api
from wingman_day1.api.v1 import sites as sites_api
from wingman_day1.api.v1 import specs as specs_api
from wingman_day1.api.v1 import upgrades as upgrades_api
from wingman_day1.api.v1 import webhooks as webhooks_api
from wingman_day1.api.v1.nodepool_catalogs import ROUTERS as NODEPOOL_CATALOG_ROUTERS
from wingman_day1.api.v1.server_scan_area import ROUTERS as SERVER_SCAN_ROUTERS

ROUTERS: Final[tuple[APIRouter, ...]] = (
    auth_api.router,
    clusters_api.router,
    sites_api.sites_router,
    sites_api.mces_router,
    specs_api.router,
    *NODEPOOL_CATALOG_ROUTERS,
    placement_api.router,
    quick_links_api.router,
    inventory_api.router,
    segments_api.router,
    *SERVER_SCAN_ROUTERS,
    upgrades_api.router,
    scale_api.router,
    approvals_api.router,
    audit_api.router,
    webhooks_api.router,
)
