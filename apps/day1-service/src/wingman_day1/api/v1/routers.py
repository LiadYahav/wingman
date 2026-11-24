"""Every router of the day1 API, in the order ``main`` mounts them.

A new area adds its router here, not to the composition root; the nodepool
catalogues are one entry (``nodepool_catalogs``).
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from wingman_day1.api.v1 import agent_labels as agent_labels_api
from wingman_day1.api.v1 import approvals as approvals_api
from wingman_day1.api.v1 import audit as audit_api
from wingman_day1.api.v1 import auth as auth_api
from wingman_day1.api.v1 import cluster_status as cluster_status_api
from wingman_day1.api.v1 import clusters as clusters_api
from wingman_day1.api.v1 import inventory as inventory_api
from wingman_day1.api.v1 import kv_clusters as kv_clusters_api
from wingman_day1.api.v1 import placement as placement_api
from wingman_day1.api.v1 import platforms as platforms_api
from wingman_day1.api.v1 import quick_links as quick_links_api
from wingman_day1.api.v1 import scale as scale_api
from wingman_day1.api.v1 import sites as sites_api
from wingman_day1.api.v1 import specs as specs_api
from wingman_day1.api.v1 import upgrades as upgrades_api
from wingman_day1.api.v1 import webhooks as webhooks_api
from wingman_day1.api.v1.nodepool_catalogs import ROUTERS as NODEPOOL_CATALOG_ROUTERS

ROUTERS: Final[tuple[APIRouter, ...]] = (
    auth_api.router,
    clusters_api.router,
    cluster_status_api.router,
    sites_api.sites_router,
    sites_api.mces_router,
    kv_clusters_api.router,
    specs_api.router,
    *NODEPOOL_CATALOG_ROUTERS,
    placement_api.router,
    quick_links_api.router,
    platforms_api.router,
    inventory_api.router,
    upgrades_api.router,
    scale_api.router,
    agent_labels_api.router,
    approvals_api.router,
    audit_api.router,
    webhooks_api.router,
)
