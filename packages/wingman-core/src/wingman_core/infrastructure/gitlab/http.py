"""Building the HTTP client the GitLab adapter uses."""

from __future__ import annotations

import httpx

from wingman_core.settings import GitLabSettings


def build_client(
    settings: GitLabSettings, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """An AsyncClient for ``<url>/api/v4`` with the token, timeouts and TLS settings.

    The token goes in the ``PRIVATE-TOKEN`` header, never the URL, so it cannot
    leak into an error message or an access log.
    """
    return httpx.AsyncClient(
        base_url=f"{str(settings.url).rstrip('/')}/api/v4",
        headers={"PRIVATE-TOKEN": settings.token.get_secret_value(), "Accept": "application/json"},
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.read_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        ),
        verify=settings.verify_tls,
        transport=transport,
        follow_redirects=False,
    )
