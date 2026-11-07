"""Day1 domain errors as RFC 9457 problems (ADR-0004).

The core handlers already cover Git errors, self-approval and unmanaged MRs;
this maps day1's own. ``details.problems`` lists every rule a request broke,
so the form can show them all at once.
"""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.web.errors import (
    AlreadyExists,
    AppError,
    DependencyUnavailable,
    Forbidden,
    NotFound,
    RevisionConflict,
    Unauthorized,
    ValidationFailed,
)
from wingman_core.web.exception_handlers import problem
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    AmbiguousNameError,
    Day1Error,
    Day2UnavailableError,
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    IdentityError,
    IdentityUnavailableError,
    InvalidInputError,
    LoginRefusedError,
    ResourceNotFoundError,
    StaleError,
)

_MAPPING: Final[tuple[tuple[type[Day1Error], type[AppError]], ...]] = (
    (InvalidInputError, ValidationFailed),
    (ResourceNotFoundError, NotFound),
    (AlreadyInUseError, AlreadyExists),
    (AmbiguousNameError, ValidationFailed),
    (StaleError, RevisionConflict),
    (HubNotConfiguredError, ValidationFailed),
    (HubObjectNotFoundError, NotFound),
    (HubDeniedError, DependencyUnavailable),
    (HubUnavailableError, DependencyUnavailable),
    (IdentityUnavailableError, DependencyUnavailable),
    (IdentityError, Unauthorized),
    (LoginRefusedError, Forbidden),
    (Day2UnavailableError, DependencyUnavailable),
)


def to_app_error(error: Day1Error) -> AppError:
    """The problem a day1 error becomes."""
    details: dict[str, object] = {}
    if isinstance(error, InvalidInputError) and error.problems:
        details["problems"] = list(error.problems)
    for domain_type, app_type in _MAPPING:
        if isinstance(error, domain_type):
            return app_type(str(error), details=details)
    return AppError(str(error), details=details)


def register_day1_error_handlers(app: FastAPI) -> None:
    """Route day1 errors (and invalid repo paths from user input) through the problem shape."""

    @app.exception_handler(Day1Error)
    async def handle_day1_error(request: Request, exc: Day1Error) -> JSONResponse:
        error = to_app_error(exc)
        return problem(
            request,
            status=error.status,
            code=error.code,
            detail=error.detail,
            details=error.details,
        )

    @app.exception_handler(InvalidRepoPathError)
    async def handle_bad_path(request: Request, exc: InvalidRepoPathError) -> JSONResponse:
        error = ValidationFailed(f"not a valid name: {exc}")
        return problem(request, status=error.status, code=error.code, detail=error.detail)
