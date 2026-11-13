"""What day1's adapters of the platform's HTTP services share: the client and JSON reading.

server-scan, segments-manager, the orchestrator's workflows, OpenShift's
OAuth, the MCE hubs and day2 are each called over httpx the same way: JSON
asked for, a timeout, and ``verify`` as ``True``/``False`` or a CA bundle
path, read when the client is built so a missing bundle stops start-up.
"""

from __future__ import annotations

import ssl
from collections.abc import Mapping
from typing import Any, Final

import httpx

JSON = Any
"""A decoded JSON value; narrowed where it is read."""

NOT_SENT: Final = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
"""Transport errors that happen before a request leaves: nothing reached the service."""


def tls_verify(verify: bool | str) -> ssl.SSLContext | bool:
    """``True``/``False``, or a context trusting the CA bundle at ``verify``."""
    if isinstance(verify, bool):
        return verify
    return ssl.create_default_context(cafile=verify)


def json_client(
    *,
    base_url: str = "",
    verify: bool | str = True,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
    headers: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    """A client at ``base_url`` (its trailing ``/`` dropped) that asks for JSON.

    ``headers`` are sent with every request too; ``transport`` replaces the
    network in tests.
    """
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout_seconds),
        verify=tls_verify(verify),
        transport=transport,
        headers={"Accept": "application/json", **(headers or {})},
    )


def required_text(raw: Mapping[str, JSON], key: str) -> str:
    """``raw[key]``, a non-empty string; anything else raises Key/ValueError."""
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is not a non-empty string")
    return value


def optional_text(raw: Mapping[str, JSON], key: str) -> str | None:
    """``raw[key]`` as a string, ``None`` when absent, null or empty; else TypeError."""
    value = raw.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value
