"""day2 errors as RFC 9457 problems (ADR-0004), through core's single problem builder."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wingman_core.web.errors import (
    AlreadyExists,
    AppError,
    NotFound,
    ValidationFailed,
)
from wingman_core.web.exception_handlers import problem
from wingman_day2.domain.errors import (
    AmbiguousClusterError,
    ChangeRefusedError,
    ChartAlreadyInstalledError,
    ChartNotInstalledError,
    Day2Error,
    InvalidClusterIdError,
    UnknownChartError,
    UnknownClusterError,
    UnknownTeamError,
)

_MAPPING: tuple[tuple[type[Day2Error], type[AppError]], ...] = (
    (UnknownTeamError, NotFound),
    (UnknownClusterError, NotFound),
    (UnknownChartError, NotFound),
    (ChartNotInstalledError, NotFound),
    (ChartAlreadyInstalledError, AlreadyExists),
    (AmbiguousClusterError, ValidationFailed),
    (InvalidClusterIdError, ValidationFailed),
    (ChangeRefusedError, ValidationFailed),
)


def as_app_error(error: Day2Error) -> AppError:
    """The problem a day2 error becomes at the HTTP boundary."""
    for day2_type, app_type in _MAPPING:
        if isinstance(error, day2_type):
            return app_type(error.detail, details=error.details)
    return AppError(error.detail, details=error.details)


def register_day2_errors(app: FastAPI) -> None:
    """Render every ``Day2Error`` as a problem document."""

    @app.exception_handler(Day2Error)
    async def handle_day2_error(request: Request, exc: Day2Error) -> JSONResponse:
        error = as_app_error(exc)
        return problem(
            request,
            status=error.status,
            code=error.code,
            detail=error.detail,
            details=error.details,
        )
