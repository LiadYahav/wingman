"""Warm a new replica's cache in the background, so its first visitor does not pay (ADR-0041).

A new pod (a deploy, a restart, a scale-up) starts with an empty cache, and
its first cluster list reads every repository and every cluster's last
change. The warm-up makes those reads as the service starts. It never holds
up readiness: a request that arrives meanwhile joins the same fetches
(single-flight), and a failed warm-up is only logged, since the first real
read retries it and reports its error itself. Readiness asks GitLab only until
it has answered once (``ready_once``, ADR-0054); after that, a GitLab failure
is reported the same way, by the request that meets it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def start_warm_up(name: str, warm: Callable[[], Awaitable[object]]) -> asyncio.Task[None]:
    """Run ``warm()`` in the background; the caller cancels the task on shutdown."""

    async def run() -> None:
        started = time.perf_counter()
        try:
            await warm()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a warm-up logs any failure, never raises
            logger.warning("%s warm-up failed: %s: %s", name, type(exc).__name__, exc)
        else:
            logger.info("%s warm-up done in %.2fs", name, time.perf_counter() - started)

    return asyncio.create_task(run(), name=f"{name}-warm-up")
