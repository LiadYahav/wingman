"""HttpArgoCd: an ArgoCD's applications, counted, for Quick Links' cards (ADR-0052).

One call per instance, ``GET <ArgoCD>/api/v1/applications`` with only the
two fields counted (``fields=items.status.sync.status,items.status.health.status``),
and the instance's read-only token as ``Authorization: Bearer``. Tokens are a
YAML file ``{<instance>: <token>}`` mounted from a Secret
(``QUICK_LINKS_ARGOCD_TOKENS_FILE``); an instance is a cluster's name for the
generated cards, or the key a links-file card names. A token never appears in
an error, a log line or an answer, and never reaches the browser.

Never raises: a failure is a reading with ``error`` (``ArgoCD refused the
token (401)``). Counted as ``dependency="argocd"``,
``operation="list_applications"``; the instance is never a label (ADR-0010).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import httpx
import yaml

from wingman_core.observability.metrics import Dependency, Outcome, WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.quick_links import ArgoCdReading, count_applications
from wingman_day1.infrastructure.link_probe import USER_AGENT, tls_context
from wingman_day1.infrastructure.observed import ArgoCdOperation, Timer

APPLICATIONS_PATH: Final = "/api/v1/applications"
FIELDS: Final = "items.status.sync.status,items.status.health.status"
DENIED: Final = frozenset({401, 403})

JSON = Any
"""A decoded JSON value; narrowed where it is read."""


class _Failure(Exception):
    """Why the counts could not be read, and the metric's outcome."""

    def __init__(self, message: str, outcome: Outcome) -> None:
        super().__init__(message)
        self.outcome = outcome


def load_argocd_tokens(path: Path) -> dict[str, str]:
    """The tokens file: a YAML mapping of instance to token. No file: no tokens.

    Raises ``ValueError`` (naming the instance, never the token) for
    anything that is not a mapping of non-empty, single-line strings.
    """
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(  # noqa: TRY004 - a bad settings file is one ValueError to start-up
            f"{path} must be a YAML mapping of ArgoCD instance to token"
        )
    tokens: dict[str, str] = {}
    for instance, token in raw.items():
        if not isinstance(instance, str) or not instance.strip():
            raise ValueError(f"{path}: every key must be an ArgoCD instance name")
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{path}: the token for {instance!r} is empty or not a string")
        if "\r" in token or "\n" in token.strip():
            raise ValueError(f"{path}: the token for {instance!r} spans more than one line")
        tokens[instance.strip()] = token.strip()
    return tokens


def application_statuses(raw: JSON) -> list[tuple[str | None, str | None]]:
    """``(sync, health)`` of each item of ArgoCD's application list; raises on another shape."""
    if not isinstance(raw, dict):
        raise TypeError("the application list is not an object")
    items = raw.get("items")
    if items is None:  # ArgoCD answers null for no applications
        return []
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    statuses: list[tuple[str | None, str | None]] = []
    for item in items:
        status = item.get("status") if isinstance(item, dict) else None
        status = status if isinstance(status, dict) else {}
        statuses.append((_status(status, "sync"), _status(status, "health")))
    return statuses


def _status(status: Mapping[str, JSON], key: str) -> str | None:
    part = status.get(key)
    value = part.get("status") if isinstance(part, dict) else None
    return value if isinstance(value, str) else None


class HttpArgoCd:
    """An ``ArgoCdApi`` for every instance that has a token, over one httpx client."""

    def __init__(
        self,
        *,
        tokens: Mapping[str, str],
        verify: bool | str = True,
        timeout_seconds: float = 3.0,
        concurrency: int = 8,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = system_clock,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Read with ``tokens`` (instance → token); ``transport`` replaces the network in tests."""
        self._tokens = dict(tokens)
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            verify=tls_context(verify),
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        self._slots = asyncio.Semaphore(concurrency)
        self._metrics = metrics
        self._clock = clock
        self._timer = timer

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def has_token(self, instance: str) -> bool:
        """See ArgoCdApi.has_token."""
        return instance in self._tokens

    async def application_counts(self, instance: str, url: str) -> ArgoCdReading:
        """See ArgoCdApi.application_counts."""
        checked_at = self._clock()
        token = self._tokens.get(instance)
        if token is None:
            return ArgoCdReading(instance, checked_at, error="no token is configured")
        async with self._slots:
            start = self._timer()
            outcome = Outcome.OK
            try:
                statuses = await self._read(url, token)
            except _Failure as exc:
                outcome = exc.outcome
                return ArgoCdReading(instance, checked_at, error=str(exc))
            finally:
                if self._metrics is not None:
                    self._metrics.observe_dependency(
                        Dependency.ARGOCD,
                        ArgoCdOperation.LIST_APPLICATIONS,
                        outcome,
                        self._timer() - start,
                    )
        return ArgoCdReading(instance, checked_at, counts=count_applications(statuses))

    async def _read(self, url: str, token: str) -> list[tuple[str | None, str | None]]:
        try:
            response = await self._client.get(
                url.rstrip("/") + APPLICATIONS_PATH,
                params={"fields": FIELDS},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException as exc:
            raise _Failure(
                f"ArgoCD did not answer within {self._timeout_seconds:g} s", Outcome.UNAVAILABLE
            ) from exc
        except httpx.TransportError as exc:
            raise _Failure(
                f"ArgoCD could not be reached ({type(exc).__name__})", Outcome.UNAVAILABLE
            ) from exc
        if response.status_code in DENIED:
            raise _Failure(f"ArgoCD refused the token ({response.status_code})", Outcome.DENIED)
        if response.status_code != 200:
            raise _Failure(f"ArgoCD answered {response.status_code}", Outcome.UNAVAILABLE)
        try:
            return application_statuses(response.json())
        except (ValueError, TypeError, AttributeError) as exc:
            raise _Failure(
                "ArgoCD answered something other than an application list", Outcome.ERROR
            ) from exc
