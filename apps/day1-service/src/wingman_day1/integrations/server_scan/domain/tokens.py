"""Whether a call server-scan keeps for one of its roles works here (ADR-0048).

server-scan takes three shared tokens: viewer, auditor and admin. Wingman
holds the viewer token for its reads, and optionally the auditor token (a
server's History, the Events page) and the admin token (maintenance, the
Jobs page). One rule decides, for every page that needs the auditor's or
the admin's role, whether it works in this deployment.
"""

from __future__ import annotations


def token_detail(off: str, *, viewer_token: bool, token: bool) -> str | None:
    """``off``, why a call that needs ``token`` does not work here; ``None`` when it does.

    With the token the calls carry it. With no token at all server-scan runs
    with auth off (every caller is an admin there), so they need none. A
    viewer token alone means auth is on, and server-scan would refuse them.
    """
    if token or not viewer_token:
        return None
    return off
