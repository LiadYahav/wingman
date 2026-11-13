"""Conditional GETs: a weak ``ETag`` over a JSON body, and a bodiless 304 for a current copy.

For an answer a page polls (the Server Scan area's fleet rows, ADR-0048): the
browser keeps the body with its ``ETag`` and, under ``Cache-Control:
no-cache``, asks again with ``If-None-Match``; an unchanged answer is a 304
with no body. Weak, because nginx gzips the bytes on the wire without
changing the representation, and keeps a weak validator when it does. The
rule is server-scan's own (``_weak_etag`` and ``_etag_matches`` in its
``backend/app/api/v1/servers.py`` at 92146d3).
"""

from __future__ import annotations

from hashlib import blake2b

from fastapi import Request, Response


def weak_etag(body: bytes) -> str:
    """A weak validator for ``body`` (RFC 9110 §8.8.3)."""
    return f'W/"{blake2b(body, digest_size=16).hexdigest()}"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Whether an ``If-None-Match`` header names ``etag``, compared weakly, or is ``*``."""
    if not if_none_match:
        return False
    wanted = etag.removeprefix("W/")
    return if_none_match.strip() == "*" or any(
        tag.strip().removeprefix("W/") == wanted for tag in if_none_match.split(",")
    )


def conditional_json(request: Request, body: bytes, etag: str) -> Response:
    """``body`` as JSON with its ``ETag``, or a bodiless 304 when the caller's copy is current."""
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
