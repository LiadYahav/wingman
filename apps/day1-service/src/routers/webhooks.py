"""GitLab webhook receiver for cache invalidation.

Configure GitLab to send Push and Merge Request events to:
  POST https://wingman.{domain}/api/webhooks/gitlab

Set the secret token in GitLab webhook settings to match GITLAB_WEBHOOK_SECRET.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from wingman_shared.cache import CacheManager

from ..config import Settings, get_settings
from ..dependencies import get_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_webhook_secret(
    x_gitlab_token: str | None,
    secret: str,
) -> bool:
    """Verify GitLab webhook secret token."""
    if not secret:
        return True  # No secret configured — accept all (dev mode)
    if not x_gitlab_token:
        return False
    return hmac.compare_digest(x_gitlab_token, secret)


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_gitlab_token: str | None = Header(default=None),
    x_gitlab_event: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive GitLab webhook events and invalidate relevant cache entries."""
    if not _verify_webhook_secret(x_gitlab_token, settings.GITLAB_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )

    payload: dict[str, Any] = await request.json()
    event = x_gitlab_event or ""
    project_id = str(payload.get("project", {}).get("id", ""))

    logger.info("Received GitLab webhook: event=%s project=%s", event, project_id)

    if event == "Push Hook":
        _handle_push(cache, payload, project_id, settings)
    elif event == "Merge Request Hook":
        _handle_mr(cache, project_id, settings)
    else:
        logger.debug("Unhandled webhook event: %s", event)

    return {"status": "ok"}


def _handle_push(
    cache: CacheManager,
    payload: dict[str, Any],
    project_id: str,
    settings: Settings,
) -> None:
    """Invalidate cache based on which files changed in a push."""
    ref = payload.get("ref", "")
    if ref != f"refs/heads/{settings.GITLAB_DEFAULT_BRANCH}":
        logger.debug("Push to non-default branch %s, skipping cache invalidation", ref)
        return

    commits: list[dict[str, Any]] = payload.get("commits", [])
    changed_paths: set[str] = set()
    for commit in commits:
        changed_paths.update(commit.get("added", []))
        changed_paths.update(commit.get("modified", []))
        changed_paths.update(commit.get("removed", []))

    day1_id = str(settings.day1_project_id)
    specs_id = str(settings.specs_project_id)

    if project_id == day1_id:
        _invalidate_day1(cache, changed_paths)
    elif project_id == specs_id:
        logger.debug("Specs repo push — invalidating all spec cache")
        cache.invalidate_prefix("specs:")
    else:
        logger.debug("Push from unknown project %s", project_id)


def _handle_mr(
    cache: CacheManager,
    project_id: str,
    settings: Settings,
) -> None:
    """Invalidate approval caches on MR events."""
    day1_id = str(settings.day1_project_id)
    specs_id = str(settings.specs_project_id)

    if project_id in (day1_id, specs_id):
        cache.invalidate_prefix("approvals:day1")
        logger.debug("Invalidated day1 approvals cache")
    else:
        logger.debug("MR event from unknown project %s", project_id)


def _invalidate_day1(cache: CacheManager, changed_paths: set[str]) -> None:
    """Smart invalidation: only clear cache for affected clusters."""
    # Always refresh the cluster list
    cache.invalidate("day1:clusters:list")

    # Find affected cluster names from paths like
    # "sites/dc1/mces/mce1/hostedClusters/alpha.yaml"
    affected_clusters: set[str] = set()
    for path in changed_paths:
        filename = path.split("/")[-1]
        if filename.endswith(".wingman.yaml"):
            affected_clusters.add(filename.removesuffix(".wingman.yaml"))
        elif filename.endswith(".yaml"):
            affected_clusters.add(filename.removesuffix(".yaml"))

    for name in affected_clusters:
        cache.invalidate_prefix(f"day1:clusters:detail:{name}")
        cache.invalidate_prefix(f"day1:clusters:metadata:{name}")
        cache.invalidate_prefix(f"day1:clusters:drift:{name}")
        logger.debug("Invalidated cache for cluster: %s", name)

    # Also invalidate spec-related cache (specs may reference cluster counts)
    cache.invalidate_prefix("specs:")
