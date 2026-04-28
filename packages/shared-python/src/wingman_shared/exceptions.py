"""Custom exceptions for the Wingman platform."""


class WingmanError(Exception):
    """Base exception for all Wingman errors."""


class GitLabError(WingmanError):
    """Error interacting with GitLab API."""


class NotFoundError(WingmanError):
    """Resource not found in Git."""


class ConflictError(WingmanError):
    """Optimistic locking conflict — resource was modified concurrently."""


class ValidationError(WingmanError):
    """Input validation failed."""


class AuthError(WingmanError):
    """Authentication or authorization failure."""


class CacheError(WingmanError):
    """Cache operation failure."""
