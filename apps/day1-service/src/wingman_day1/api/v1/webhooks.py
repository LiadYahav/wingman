"""``POST /api/webhooks/gitlab``: GitLab tells day1 a managed repo changed.

The webhook only shortens how long a cached read can be stale; correctness
never depends on it (ADR-0011). A push or merge in the specs project also
starts, in the background, the rollout of each flavor with work pending
(ADR-0044); the rollout's other triggers cover a missed hook. It exists only
when ``GITLAB_WEBHOOK_SECRET`` is set, and checks ``X-Gitlab-Token`` in
constant time: with no secret the
route answers 404 instead of accepting anyone (ADR-0009). It clears caches
through the same functions the write paths use.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header

from wingman_core.web.errors import NotFound, Unauthorized
from wingman_day1.api.deps import Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.domain.rollout import RolloutTrigger

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
    for key, reads in context.repos.items():
        if (await reads.project()).id != project_id:
            continue
        if x_gitlab_event == PUSH:
            reads.forget_files()
        elif x_gitlab_event == MERGE_REQUEST:
            reads.forget_merge_requests()
            reads.forget_files()
        if key is RepoKey.SPECS and x_gitlab_event in (PUSH, MERGE_REQUEST):
            context.rollouts.start_all(RolloutTrigger.WEBHOOK)
        return {"status": "ok"}
    return {"status": "ignored"}
