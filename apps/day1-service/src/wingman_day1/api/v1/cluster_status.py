"""``/api/day1/clusters`` live status: one cluster's, its stream, and many at once.

What the MCE hub reports for the HostedCluster a cluster file renders, and its
NodePools (``CLUSTER_STATUS_ENABLED``; off, every route answers 501). Reads
need a session (``CurrentUser``).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from wingman_core.domain.errors import GitError
from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Context, Status
from wingman_day1.api.v1.cluster_status_schemas import BulkStatusIn, ClusterLiveStatusOut
from wingman_day1.domain.errors import Day1Error
from wingman_day1.domain.visibility import require_seen, sees_cluster

router = APIRouter(prefix="/api/day1/clusters", tags=["clusters"])

RequiredMce = Annotated[str, Query(min_length=1, max_length=63, description="MCE folder")]


@router.post("/bulk-status")
async def bulk_status(
    body: BulkStatusIn, user: CurrentUser, status: Status
) -> dict[str, ClusterLiveStatusOut]:
    """Live status of many clusters; each failure is in its entry's ``error``.

    A KV cluster a viewer names is left out of the answer, as an unknown one would be.
    """
    asked = [(c.name, c.mce) for c in body.clusters if sees_cluster(user, c.name, mce=c.mce)]
    results = await status.statuses(asked)
    return {name: ClusterLiveStatusOut.of(s) for name, s in results.items()}


@router.get("/{name}/status")
async def cluster_status(
    name: str, mce: RequiredMce, user: CurrentUser, status: Status
) -> ClusterLiveStatusOut:
    """The HostedCluster and NodePools on the MCE hub (501 when status is off)."""
    require_seen(user, name, mce=mce)
    return ClusterLiveStatusOut.of(await status.status(name, mce))


@router.get("/{name}/status/stream")
async def stream_cluster_status(
    name: str, mce: RequiredMce, user: CurrentUser, status: Status, context: Context
) -> StreamingResponse:
    """Server-sent events: the live status now, then every ``status_poll_seconds``."""
    require_seen(user, name, mce=mce)

    async def events() -> AsyncIterator[str]:
        try:
            async for live in status.watch(name, mce, interval=context.status_poll_seconds):
                yield f"data: {ClusterLiveStatusOut.of(live).model_dump_json()}\n\n"
        except (Day1Error, GitError) as exc:
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
