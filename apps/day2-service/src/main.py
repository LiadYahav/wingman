"""Wingman Day2 Service — addon and operator management."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .dependencies import get_cache
from .routers import addons, approvals, audit

logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from .dependencies import (  # noqa: PLC0415
        get_cache,
        get_path_resolver,
        get_sigs_group_client,
    )
    from .services.addon_service import AddonService  # noqa: PLC0415
    from .services.approval_service import ApprovalService  # noqa: PLC0415

    settings = get_settings()
    logger.info("Day2 Service starting on port %d", settings.SERVICE_PORT)

    # Background cache pre-warmer: keeps addon catalog and approvals warm
    async def cache_warmer() -> None:
        # Wait a bit on startup before first warm
        logger.info("Day2 cache warmer starting in 5 seconds...")
        await asyncio.sleep(5)
        while True:
            try:
                logger.info("Day2 cache pre-warm: refreshing addon catalog, approvals")
                # Manually construct services (can't use FastAPI Depends outside request)
                group_client = get_sigs_group_client()
                path_resolver = get_path_resolver()
                cache = get_cache()

                addon_svc = AddonService(
                    group_client=group_client,
                    path_resolver=path_resolver,
                    cache=cache,
                    settings=settings,
                )
                approval_svc = ApprovalService(
                    group_client=group_client,
                    cache=cache,
                    cache_key_prefix="day2",
                    cache_ttl=settings.CACHE_APPROVALS_TTL,
                )

                # Pre-warm main data (fire and forget)
                results = await asyncio.gather(
                    addon_svc.list_addons(),
                    approval_svc.list_open_mrs(),
                    return_exceptions=True,
                )
                # Log any errors from the gather
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.warning("Day2 cache pre-warm task %d failed: %s", i, result)
                logger.info("Day2 cache pre-warm complete")
            except Exception as exc:
                logger.warning("Cache pre-warm error: %s", exc)
            await asyncio.sleep(settings.CACHE_BACKGROUND_REFRESH_SECONDS)

    task = asyncio.create_task(cache_warmer(), name="day2-cache-warmer")
    yield
    task.cancel()
    logger.info("Day2 Service shutting down")


app = FastAPI(
    title="Wingman Day2 Service",
    description="Addon and operator lifecycle management",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(addons.router)
app.include_router(approvals.router)
app.include_router(audit.router)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/day2/cache/stats")
async def cache_stats() -> dict:
    return get_cache().stats()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
