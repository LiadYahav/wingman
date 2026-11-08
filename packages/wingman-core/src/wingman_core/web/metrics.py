"""HTTP request metrics and the ``/metrics`` endpoint.

``/metrics`` sits at the root of each service's own port, outside ``/api``.
The web app's nginx only proxies ``/api/*``, so the endpoint is reachable by
Prometheus inside the cluster and never through the public Route.
"""

from __future__ import annotations

import time
from typing import Final

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from wingman_core.observability.metrics import UNMATCHED_ROUTE, WingmanMetrics

METRICS_PATH: Final = "/metrics"


class MetricsMiddleware:
    """Pure-ASGI middleware recording ``wingman_http_*`` per route template."""

    def __init__(self, app: ASGIApp, metrics: WingmanMetrics) -> None:
        """Wrap ``app``."""
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Time the request; label it with the route the router matched."""
        if scope["type"] != "http" or scope["path"] == METRICS_PATH:
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            # The router writes the matched route into the shared scope.
            route = scope.get("route")
            template = getattr(route, "path", None) or UNMATCHED_ROUTE
            self.metrics.observe_http(
                method=scope["method"],
                route=template,
                status=status,
                seconds=time.perf_counter() - start,
            )


def install_metrics(app: FastAPI, metrics: WingmanMetrics) -> None:
    """Add the middleware and the ``/metrics`` route (left out of OpenAPI)."""
    app.add_middleware(MetricsMiddleware, metrics=metrics)

    @app.get(METRICS_PATH, include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(content=generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)
