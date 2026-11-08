"""Errors a Git hosting backend can raise, independent of which backend it is.

Both the GitLab HTTP adapter and the in-memory fake raise exactly these, so
application code never sees an HTTP status or a backend-specific exception.
The web layer maps each one to an RFC 9457 problem (ADR-0004).
"""

from __future__ import annotations


class GitError(Exception):
    """Base class for every error a GitLabPort implementation raises."""


class NotFoundError(GitError):
    """The project, ref, file or merge request does not exist."""


class AlreadyExistsError(GitError):
    """Creating something that exists: a file, a branch, or an open MR for a branch."""


class RevisionConflictError(GitError):
    """A write was based on a stale revision.

    Raised when an update carries a ``last_commit_id`` that is no longer the
    file's latest commit, and when a merge cannot apply cleanly. The caller
    must re-read and decide again; it is never retried automatically
    (ADR-0006).
    """


class NotMergeableError(GitError):
    """The merge request cannot be merged in its current state."""


class PermissionDeniedError(GitError):
    """The backend refused the credentials or the operation."""


class InvalidRequestError(GitError):
    """The backend rejected the request as malformed."""


class GitUnavailableError(GitError):
    """The backend could not be reached or answered with a server error.

    For reads this is safe to retry. For writes it is only raised when the
    request is known not to have been sent; otherwise see
    :class:`AmbiguousWriteError`.
    """


class AmbiguousWriteError(GitError):
    """A write may or may not have been applied.

    Raised when a write times out after it was sent, or the backend answers
    a write with a server error. Writes are not idempotent (a retried commit
    can commit twice), so the only safe follow-up is to re-read the state and
    let the caller decide (ADR-0006).
    """


class InvalidRepoPathError(ValueError):
    """A string is not a valid path inside a repository."""
