"""``POST /api/webhooks/gitlab``: GitLab tells day1 a managed repo changed.

The webhook only shortens how long a cached read can be stale; correctness
never depends on it (ADR-0011). It exists only when ``GITLAB_WEBHOOK_SECRET``
is set, and checks ``X-Gitlab-Token`` in constant time: with no secret the
route answers 404 instead of accepting anyone (ADR-0009). It clears caches
through the same functions the write paths use.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header

from wingman_core.web.errors import NotFound, Unauthorized
from wingman_day1.api.deps import Context

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

PUSH = "Push Hook"
MERGE_REQUEST = "Merge Request Hook"


@router.post("/gitlab")
async def gitlab_webhook(
    context: Context,
    payload: Annotated[dict[str, Any], Body()],
    x_gitlab_token: Annotated[str | None, Header()] = None,
    x_gitlab_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Clear what a push or an MR event in the day1 or specs project made stale."""
    secret = context.webhook_secret
    if secret is None:
        raise NotFound("Not found.")
    if not x_gitlab_token or not hmac.compare_digest(x_gitlab_token.encode(), secret.encode()):
        raise Unauthorized("Invalid webhook token.")
    project = payload.get("project")
    project_id = project.get("id") if isinstance(project, dict) else None
    for reads in context.repos.values():
        if (await reads.project()).id != project_id:
            continue
        if x_gitlab_event == PUSH:
            reads.forget_files()
        elif x_gitlab_event == MERGE_REQUEST:
            reads.forget_merge_requests()
            reads.forget_files()
        return {"status": "ok"}
    return {"status": "ignored"}
