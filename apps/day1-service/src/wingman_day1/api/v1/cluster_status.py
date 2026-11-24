"""``/api/day1/clusters`` live status: one cluster's, its stream, and many at once.

What the MCE hub reports for the HostedCluster a cluster file renders, and its
NodePools (``CLUSTER_STATUS_ENABLED``; off, every route answers 501). Reads
need a session (``CurrentUser``).

``mce`` is an admin's to send (ADR-0068): it names the hub to read, and a
cluster provision-cluster has not merged yet is on no MCE in the tree. A
viewer's cluster is found by its name in the tree, whatever ``mce`` says, and
a viewer's answer names no hub: a failed read says so without the hub's words.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from wingman_core.domain.errors import GitError
from wingman_core.domain.redaction import Redactor
from wingman_core.domain.users import User
from wingman_core.web.auth import CurrentUser
from wingman_core.web.viewer import for_viewer
from wingman_day1.api.deps import Context, Day1Context, Status
from wingman_day1.api.v1.cluster_status_schemas import BulkStatusIn, ClusterLiveStatusOut
from wingman_day1.api.v1.visible import cluster_ref, redactor
from wingman_day1.domain.errors import Day1Error
from wingman_day1.domain.status import LiveStatus
from wingman_day1.domain.visibility import UNREAD_STATUS, sees_cluster

router = APIRouter(prefix="/api/day1/clusters", tags=["clusters"])

Mce = Annotated[
    str | None,
    Query(min_length=1, max_length=63, description="MCE folder (an admin's; else from the tree)"),
]


async def _mce_of(context: Day1Context, user: User, name: str, mce: str | None) -> str:
    """The hub to read: an admin's ``mce`` as sent, else the cluster's folder in the tree."""
    if user.is_admin and mce:
        return mce
    return (await cluster_ref(context, user, name, None, None)).mce


def _out(live: LiveStatus, user: User, names: Redactor) -> ClusterLiveStatusOut:
    """The answer; a viewer's error says the read failed, never what the hub said."""
    out = ClusterLiveStatusOut.of(live)
    if user.is_admin:
        return out
    hidden = out.model_copy(update={"error": UNREAD_STATUS if out.error else None})
    return for_viewer(hidden, names)


@router.post("/bulk-status")
async def bulk_status(
    body: BulkStatusIn, user: CurrentUser, status: Status, context: Context
) -> dict[str, ClusterLiveStatusOut]:
    """Live status of many clusters; each failure is in its entry's ``error``.

    An entry without ``mce`` is found in the tree, as every one of a viewer's
    is; a KV cluster a viewer names, or one the tree does not hold once, is
    left out of the answer, as an unknown one would be.
    """
    tree = await context.sites.tree()
    asked: list[tuple[str, str]] = []
    for item in body.clusters:
        if user.is_admin and item.mce:
            asked.append((item.name, item.mce))
            continue
        found = tree.find(item.name)
        if len(found) == 1 and sees_cluster(user, item.name, mce=found[0].mce):
            asked.append((item.name, found[0].mce))
    results = await status.statuses(asked)
    names = await redactor(context, user)
    return {name: _out(s, user, names) for name, s in results.items()}


@router.get("/{name}/status")
async def cluster_status(
    name: str, user: CurrentUser, status: Status, context: Context, mce: Mce = None
) -> ClusterLiveStatusOut:
    """The HostedCluster and NodePools on the MCE hub (501 when status is off)."""
    hub = await _mce_of(context, user, name, mce)
    return _out(await status.status(name, hub), user, await redactor(context, user))


@router.get("/{name}/status/stream")
async def stream_cluster_status(
    name: str, user: CurrentUser, status: Status, context: Context, mce: Mce = None
) -> StreamingResponse:
    """Server-sent events: the live status now, then every ``status_poll_seconds``."""
    hub = await _mce_of(context, user, name, mce)
    names = await redactor(context, user)

    async def events() -> AsyncIterator[str]:
        try:
            async for live in status.watch(name, hub, interval=context.status_poll_seconds):
                yield f"data: {_out(live, user, names).model_dump_json()}\n\n"
        except (Day1Error, GitError) as exc:
            error = f"{type(exc).__name__}: {exc}" if user.is_admin else UNREAD_STATUS
            yield f"data: {json.dumps({'error': error})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
