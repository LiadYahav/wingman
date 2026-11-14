"""How the Server Scan area's writes are recorded with the person (ADR-0048).

server-scan records the token a write came with (Wingman's admin token), not
the person, so day1 logs each write with the person's name, as node
uninstall logs its starts (``node_uninstall_started``): Wingman has no other
audit store than Git, and these lines are its record. A write that was sent
and not answered is logged as unconfirmed, with what was asked.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping

from wingman_day1.domain.errors import AmbiguousServerScanWriteError

logger = logging.getLogger("wingman_day1.application.server_scan")
"""One logger for the area's writes, whichever page sends them."""


async def recorded[T](
    write: Awaitable[T],
    event: Mapping[str, str],
    *,
    done: str,
    unconfirmed: str,
    answered: Callable[[T], Mapping[str, str]],
) -> T:
    """Await ``write`` and log it with the person in ``event``.

    ``done`` (info) with ``answered``'s fields from the answer added, or
    ``unconfirmed`` (warning) when it was sent and no answer came back.
    """
    try:
        result = await write
    except AmbiguousServerScanWriteError:
        logger.warning(
            "%s: %s",
            unconfirmed.replace("_", " "),
            _fields(event),
            extra={"event": unconfirmed, "change": done, **event},
        )
        raise
    logged = {**event, **answered(result)}
    logger.info("%s: %s", done.replace("_", " "), _fields(logged), extra={"event": done, **logged})
    return result


def _fields(event: Mapping[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in event.items())
