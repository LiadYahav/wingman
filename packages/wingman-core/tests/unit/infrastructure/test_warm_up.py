"""start_warm_up: runs in the background, logs a failure, never raises (ADR-0041)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from wingman_core.infrastructure.warm_up import start_warm_up


async def test_a_warm_up_runs_in_the_background() -> None:
    done = asyncio.Event()

    async def warm() -> None:
        done.set()

    await start_warm_up("svc", warm)
    assert done.is_set()


async def test_a_failed_warm_up_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    async def warm() -> None:
        raise RuntimeError("GitLab down")

    with caplog.at_level(logging.WARNING):
        await start_warm_up("svc", warm)
    assert "svc warm-up failed: RuntimeError: GitLab down" in caplog.text


async def test_a_warm_up_is_cancelled_on_shutdown() -> None:
    started = asyncio.Event()

    async def warm() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = start_warm_up("svc", warm)
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
