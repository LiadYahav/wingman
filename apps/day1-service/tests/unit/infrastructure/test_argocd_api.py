"""HttpArgoCd: an ArgoCD's applications, counted, with a read-only token (ADR-0052)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.infrastructure.argocd_api import (
    FIELDS,
    HttpArgoCd,
    application_statuses,
    load_argocd_tokens,
)

URL = "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal"
TOKEN = "argocd-read-only-token-value"
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def item(sync: str | None, health: str | None) -> dict[str, Any]:
    return {"status": {"sync": {"status": sync}, "health": {"status": health}}}


def argocd(handler: Handler, *, metrics: WingmanMetrics | None = None, **kw: object) -> HttpArgoCd:
    return HttpArgoCd(
        tokens={"hub-prod": TOKEN},
        transport=httpx.MockTransport(handler),
        metrics=metrics,
        clock=lambda: NOW,
        **kw,  # ty: ignore[invalid-argument-type]
    )


def answering(status: int, body: object = None, seen: list[httpx.Request] | None = None) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)

    return handler


async def test_it_counts_the_applications_by_sync_and_health() -> None:
    seen: list[httpx.Request] = []
    body = {
        "items": [
            item("Synced", "Healthy"),
            item("Synced", "Healthy"),
            item("OutOfSync", "Degraded"),
            item("OutOfSync", "Missing"),
            item("Synced", "Progressing"),
        ]
    }
    reading = await argocd(answering(200, body, seen)).application_counts("hub-prod", URL + "/")
    assert reading.error is None
    assert reading.checked_at == NOW
    counts = reading.counts
    assert counts is not None
    assert counts.applications == 5
    assert (counts.sync.synced, counts.sync.out_of_sync) == (3, 2)
    assert (counts.health.healthy, counts.health.degraded, counts.health.missing) == (2, 1, 1)
    assert counts.health.progressing == 1
    request = seen[0]
    assert str(request.url).startswith(f"{URL}/api/v1/applications?")
    assert request.url.params["fields"] == FIELDS
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("body", [{"items": None}, {"items": []}, {"metadata": {}}])
async def test_no_applications_is_zero(body: object) -> None:
    reading = await argocd(answering(200, body)).application_counts("hub-prod", URL)
    assert reading.counts is not None
    assert reading.counts.applications == 0


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, "ArgoCD refused the token (401)"),
        (403, "ArgoCD refused the token (403)"),
        (404, "ArgoCD answered 404"),
        (503, "ArgoCD answered 503"),
    ],
)
async def test_a_refusal_or_an_error_is_the_reading_s_error(status: int, error: str) -> None:
    reading = await argocd(answering(status, {"error": "x"})).application_counts("hub-prod", URL)
    assert (reading.counts, reading.error) == (None, error)


async def test_an_unexpected_answer_is_an_error() -> None:
    reading = await argocd(answering(200, ["not", "a", "list"])).application_counts("hub-prod", URL)
    assert reading.error == "ArgoCD answered something other than an application list"

    async def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>")

    reading = await argocd(html).application_counts("hub-prod", URL)
    assert reading.error == "ArgoCD answered something other than an application list"


async def test_no_answer_or_no_connection_is_an_error() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    reading = await argocd(slow, timeout_seconds=3).application_counts("hub-prod", URL)
    assert reading.error == "ArgoCD did not answer within 3 s"
    reading = await argocd(refused).application_counts("hub-prod", URL)
    assert reading.error == "ArgoCD could not be reached (ConnectError)"


async def test_an_instance_without_a_token_is_never_called() -> None:
    seen: list[httpx.Request] = []
    client = argocd(answering(200, {"items": []}, seen))
    assert client.has_token("hub-prod")
    assert not client.has_token("other")
    reading = await client.application_counts("other", URL)
    assert reading.error == "no token is configured"
    assert seen == []


async def test_the_token_never_appears_in_an_error() -> None:
    async def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=request.headers["authorization"])

    reading = await argocd(echo).application_counts("hub-prod", URL)
    assert TOKEN not in (reading.error or "")


async def test_reads_are_counted_without_the_instance_as_a_label() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    await argocd(answering(200, {"items": []}), metrics=metrics).application_counts("hub-prod", URL)
    await argocd(answering(401), metrics=metrics).application_counts("hub-prod", URL)

    def count(outcome: str) -> float | None:
        return metrics.registry.get_sample_value(
            "wingman_dependency_requests_total",
            {"dependency": "argocd", "operation": "list_applications", "outcome": outcome},
        )

    assert (count("ok"), count("denied")) == (1, 1)


async def test_at_most_concurrency_reads_run_at_once() -> None:
    running = most = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        running -= 1
        return httpx.Response(200, json={"items": []})

    client = argocd(handler, concurrency=2)
    await asyncio.gather(*(client.application_counts("hub-prod", URL) for _ in range(6)))
    assert most == 2


def test_application_statuses_tolerate_missing_parts() -> None:
    assert application_statuses({"items": [{}, {"status": None}, item("Synced", None)]}) == [
        (None, None),
        (None, None),
        ("Synced", None),
    ]
    with pytest.raises(TypeError):
        application_statuses({"items": {"a": 1}})


def test_the_tokens_file(tmp_path: Path) -> None:
    assert load_argocd_tokens(tmp_path / "missing") == {}
    path = tmp_path / "tokens"
    path.write_text("hub-prod: abc\nmain: ' def '\n", encoding="utf-8")
    assert load_argocd_tokens(path) == {"hub-prod": "abc", "main": "def"}
    path.write_text("", encoding="utf-8")
    assert load_argocd_tokens(path) == {}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("- a\n", "must be a YAML mapping"),
        ("hub-prod: ''\n", "the token for 'hub-prod' is empty"),
        ("hub-prod: [secret-value]\n", "the token for 'hub-prod' is empty or not a string"),
        ("hub-prod: |\n  line-one\n  line-two\n", "spans more than one line"),
        ("1: secret-value\n", "every key must be an ArgoCD instance name"),
    ],
)
def test_a_bad_tokens_file_stops_start_up_without_the_token(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "tokens"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message) as raised:
        load_argocd_tokens(path)
    assert "secret-value" not in str(raised.value)
    assert "line-one" not in str(raised.value)
