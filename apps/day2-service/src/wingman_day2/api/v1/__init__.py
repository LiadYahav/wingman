"""``/api/day2`` v1: every router, in one place for the composition root."""

from __future__ import annotations

from fastapi import APIRouter

from wingman_day2.api.v1 import approvals, catalog, clusters

router = APIRouter()
router.include_router(catalog.router)
router.include_router(clusters.router)
router.include_router(approvals.router)
