"""The API error model: every error leaves as an RFC 9457 problem (ADR-0004).

::

    {
      "type": "/problems/revision-conflict",
      "title": "Revision Conflict",
      "status": 409,
      "detail": "sites/site1/... has changed since 1a2b3c4d",
      "instance": "/api/day1/clusters/ocp4-prod-a-site1",
      "code": "REVISION_CONFLICT",
      "request_id": "req_...",
      "details": {}
    }

``code`` is the stable, machine-matched member; ``title`` and ``detail`` are
for people and may change wording. ``ErrorCode`` is append-only: a shipped
code is never renamed or removed, because the web app matches on it.

Services raise :class:`AppError` subclasses (or let a ``GitError`` propagate,
which the handlers translate); they never raise FastAPI's ``HTTPException``.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from wingman_core.domain.errors import (
    AlreadyExistsError,
    AmbiguousWriteError,
    GitError,
    GitUnavailableError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    PermissionDeniedError,
    RevisionConflictError,
)


class ErrorCode(StrEnum):
    """Stable error identifiers. Append only; never rename or remove one."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    NOT_MERGEABLE = "NOT_MERGEABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    GIT_UNAVAILABLE = "GIT_UNAVAILABLE"
    GIT_PERMISSION_DENIED = "GIT_PERMISSION_DENIED"
    GIT_REJECTED = "GIT_REJECTED"
    AMBIGUOUS_WRITE = "AMBIGUOUS_WRITE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SELF_APPROVAL = "SELF_APPROVAL"

    @property
    def slug(self) -> str:
        """The ``type`` member's last segment, e.g. ``revision-conflict``."""
        return self.value.lower().replace("_", "-")

    @property
    def title(self) -> str:
        """The default ``title`` member, e.g. ``Revision Conflict``."""
        return self.value.replace("_", " ").title()


class AppError(Exception):
    """An error with an HTTP status and a stable code. Subclass it; don't raise it bare."""

    status: ClassVar[int] = 500
    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, detail: str, *, details: Mapping[str, object] | None = None) -> None:
        """``detail`` is shown to people; ``details`` is structured data for clients."""
        super().__init__(detail)
        self.detail = detail
        self.details: Mapping[str, object] = details or {}


class ValidationFailed(AppError):
    """The request is well-formed but its content is not acceptable."""

    status = 422
    code = ErrorCode.VALIDATION_ERROR


class NotFound(AppError):
    """The resource does not exist."""

    status = 404
    code = ErrorCode.NOT_FOUND


class AlreadyExists(AppError):
    """The resource exists already."""

    status = 409
    code = ErrorCode.ALREADY_EXISTS


class RevisionConflict(AppError):
    """The resource changed since the caller read it; re-read and decide again."""

    status = 409
    code = ErrorCode.REVISION_CONFLICT


class NotMergeable(AppError):
    """The merge request cannot be merged now."""

    status = 409
    code = ErrorCode.NOT_MERGEABLE


class Unauthorized(AppError):
    """No valid login."""

    status = 401
    code = ErrorCode.UNAUTHORIZED


class Forbidden(AppError):
    """Logged in, but the role does not allow this."""

    status = 403
    code = ErrorCode.FORBIDDEN


class GitUnavailable(AppError):
    """GitLab could not be reached; nothing was changed."""

    status = 503
    code = ErrorCode.GIT_UNAVAILABLE


class GitPermissionDenied(AppError):
    """GitLab refused Wingman's own token: a deployment problem, not the user's."""

    status = 502
    code = ErrorCode.GIT_PERMISSION_DENIED


class GitRejected(AppError):
    """GitLab rejected the request as malformed."""

    status = 502
    code = ErrorCode.GIT_REJECTED


class AmbiguousWrite(AppError):
    """A change was sent to GitLab but its outcome is unknown; check before retrying."""

    status = 504
    code = ErrorCode.AMBIGUOUS_WRITE


class SelfApproval(AppError):
    """Nobody approves a change they requested."""

    status = 403
    code = ErrorCode.SELF_APPROVAL


_GIT_ERRORS: tuple[tuple[type[GitError], type[AppError]], ...] = (
    (NotFoundError, NotFound),
    (AlreadyExistsError, AlreadyExists),
    (RevisionConflictError, RevisionConflict),
    (NotMergeableError, NotMergeable),
    (PermissionDeniedError, GitPermissionDenied),
    (InvalidRequestError, GitRejected),
    (GitUnavailableError, GitUnavailable),
    (AmbiguousWriteError, AmbiguousWrite),
)


def from_git_error(error: GitError) -> AppError:
    """The AppError a GitError becomes when it reaches the HTTP boundary."""
    for git_type, app_type in _GIT_ERRORS:
        if isinstance(error, git_type):
            return app_type(str(error))
    return AppError(str(error))
