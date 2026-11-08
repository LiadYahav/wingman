"""Exception handlers: the one place error bodies are built (ADR-0004)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from wingman_core.application.approvals import SelfApprovalError, UnmanagedProjectError
from wingman_core.domain.errors import GitError
from wingman_core.web.errors import (
    AppError,
    ErrorCode,
    NotFound,
    SelfApproval,
    from_git_error,
)
from wingman_core.web.request_context import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)

PROBLEM_JSON: Final = "application/problem+json"

_HTTP_CODES: Final = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    422: ErrorCode.VALIDATION_ERROR,
}


def problem(
    request: Request,
    *,
    status: int,
    code: ErrorCode,
    detail: str,
    details: Mapping[str, object] | None = None,
    title: str | None = None,
) -> JSONResponse:
    """An RFC 9457 response with Wingman's extension members.

    The request id header is set here as well as by RequestIdMiddleware:
    Starlette runs the catch-all ``Exception`` handler outside every user
    middleware, so a 500 would otherwise leave without it.
    """
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_JSON,
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        content={
            "type": f"/problems/{code.slug}",
            "title": title or code.title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
            "code": code.value,
            "request_id": request_id,
            "details": dict(details or {}),
        },
    )


def app_error_response(request: Request, error: AppError) -> JSONResponse:
    """The problem for ``error``. A 5xx is logged: a dependency failed, and someone should know."""
    if error.status >= 500:
        logger.warning("%s on %s: %s", error.code, request.url.path, error.detail)
    return problem(
        request, status=error.status, code=error.code, detail=error.detail, details=error.details
    )


def register_domain_errors[E: Exception](
    app: FastAPI, base: type[E], to_app_error: Callable[[E], AppError]
) -> None:
    """Render a service's own errors (``base`` and its subclasses) the way core renders its own.

    ``to_app_error`` maps one to the problem it becomes; the response then
    takes the same path as an ``AppError`` raised anywhere, logging included.
    """

    @app.exception_handler(base)
    async def handle_domain_error(request: Request, exc: E) -> JSONResponse:
        return app_error_response(request, to_app_error(exc))


def register_exception_handlers(app: FastAPI) -> None:
    """Route every exception, ours and the framework's, through :func:`problem`."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return app_error_response(request, exc)

    @app.exception_handler(GitError)
    async def handle_git_error(request: Request, exc: GitError) -> JSONResponse:
        return await handle_app_error(request, from_git_error(exc))

    @app.exception_handler(SelfApprovalError)
    async def handle_self_approval(request: Request, exc: SelfApprovalError) -> JSONResponse:
        return await handle_app_error(request, SelfApproval(str(exc)))

    @app.exception_handler(UnmanagedProjectError)
    async def handle_unmanaged(request: Request, exc: UnmanagedProjectError) -> JSONResponse:
        return await handle_app_error(request, NotFound(str(exc)))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return problem(
            request,
            status=422,
            code=ErrorCode.VALIDATION_ERROR,
            detail="The request is not valid.",
            details={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return problem(request, status=exc.status_code, code=code, detail=str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return problem(
            request,
            status=500,
            code=ErrorCode.INTERNAL_ERROR,
            detail="An unexpected error occurred. Quote the request id when reporting it.",
        )
