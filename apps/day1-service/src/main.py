"""Wingman Day1 Service — cluster provisioning and spec management."""

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
from .routers import approvals, audit, auth, clusters, sites, specs, webhooks

logging.basicConfig(level=get_settings().LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup and shutdown lifecycle."""
    from .dependencies import (  # noqa: PLC0415
        get_cache,
        get_gitlab_day1,
        get_gitlab_specs,
        get_path_resolver,
    )
    from .services.approval_service import ApprovalService  # noqa: PLC0415
    from .services.cluster_service import ClusterService  # noqa: PLC0415
    from .services.spec_service import SpecService  # noqa: PLC0415

    settings = get_settings()
    cache = get_cache()
    logger.info("Day1 Service starting on port %d", settings.SERVICE_PORT)

    # Background cache pre-warmer: keeps main data endpoints warm
    async def cache_warmer() -> None:
        # Wait a bit on startup before first warm
        logger.info("Day1 cache warmer starting in 5 seconds...")
        await asyncio.sleep(5)
        while True:
            try:
                logger.info("Day1 cache pre-warm: refreshing cluster list, specs, approvals")
                # Manually construct services (can't use FastAPI Depends outside request)
                gl_day1 = get_gitlab_day1()
                gl_specs = get_gitlab_specs()
                path_resolver = get_path_resolver()

                cluster_svc = ClusterService(
                    gitlab_day1=gl_day1,
                    path_resolver=path_resolver,
                    cache=cache,
                    default_branch=settings.GITLAB_DEFAULT_BRANCH,
                    cluster_file_suffix=settings.DAY1_CLUSTER_FILE_SUFFIX,
                )
                spec_svc = SpecService(
                    gitlab_specs=gl_specs,
                    path_resolver=path_resolver,
                    cache=cache,
                    default_branch=settings.GITLAB_DEFAULT_BRANCH,
                )
                approval_svc = ApprovalService(
                    gitlab_day1=gl_day1,
                    gitlab_specs=gl_specs,
                    cache=cache,
                    cache_ttl=settings.CACHE_APPROVALS_TTL,
                )

                # Pre-warm main data (fire and forget, errors logged but not raised)
                results = await asyncio.gather(
                    cluster_svc.list_clusters(),
                    spec_svc.list_specs(),
                    approval_svc.list_open_mrs(),
                    return_exceptions=True,
                )
                # Log any errors from the gather
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.warning("Day1 cache pre-warm task %d failed: %s", i, result)
                logger.info("Day1 cache pre-warm complete")
            except Exception as exc:
                logger.warning("Cache pre-warm error: %s", exc)
            # Sleep for the configured interval (e.g., 60s)
            await asyncio.sleep(settings.CACHE_BACKGROUND_REFRESH_SECONDS)

    task = asyncio.create_task(cache_warmer(), name="cache-warmer")

    yield

    task.cancel()
    logger.info("Day1 Service shutting down")


app = FastAPI(
    title="Wingman Day1 Service",
    description="Cluster provisioning, spec management, and approval workflows",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tightened in production via env / helm values
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clusters.router)
app.include_router(sites.router)
app.include_router(specs.router)
app.include_router(approvals.router)
app.include_router(audit.router)
app.include_router(webhooks.router)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/day1/cache/stats")
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
