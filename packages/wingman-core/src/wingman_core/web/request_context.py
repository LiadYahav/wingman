"""A request id on every request, echoed in the response and in error bodies."""

from __future__ import annotations

import re
import secrets
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER: Final = "x-request-id"
_ACCEPTABLE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Pure-ASGI middleware: reuse a sane incoming ``X-Request-ID`` or mint one.

    Pure ASGI rather than ``BaseHTTPMiddleware`` so it does not buffer
    responses, which would break the SSE status streams.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Set ``request.state.request_id`` and the response header."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(REQUEST_ID_HEADER.encode(), b"").decode()
        request_id = incoming if _ACCEPTABLE.match(incoming) else f"req_{secrets.token_hex(8)}"
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                name = REQUEST_ID_HEADER.encode()
                if not any(key.lower() == name for key, _ in headers):
                    headers.append((name, request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_id)
