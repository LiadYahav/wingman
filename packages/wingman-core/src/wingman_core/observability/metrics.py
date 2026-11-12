"""The metric catalogue. Names and labels are a contract (docs/ops/metrics.md).

Rules, from herzi and server-scan:

- Every name starts with ``wingman_``. Dashboards and alerts depend on the
  names, so a rename is a breaking change.
- Every label value comes from a ``StrEnum`` or a fixed set; anything else is
  recorded as ``other``. Unbounded values (cluster, team, user, MR number,
  path) are never labels: one series per value would grow without end.
- The registry is passed in, never global, so each app and each test has its
  own and nothing leaks between them.
- Outcomes an alert watches are created at zero up front, so "no failures"
  is a 0 rather than an absent series.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from wingman_core.domain.errors import (
    AlreadyExistsError,
    AmbiguousWriteError,
    GitUnavailableError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    PermissionDeniedError,
    RevisionConflictError,
)

OTHER: Final = "other"
UNMATCHED_ROUTE: Final = "<unmatched>"

_HTTP_METHODS: Final = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_LATENCY_BUCKETS: Final = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class Dependency(StrEnum):
    """An external system a service calls."""

    GITLAB = "gitlab"
    KUBERNETES = "kubernetes"
    OPENSHIFT_OAUTH = "openshift_oauth"
    DAY2 = "day2"
    SERVER_SCAN = "server_scan"
    WORKFLOWS = "workflows"
    SEGMENTS_MANAGER = "segments_manager"
    LINK_CHECK = "link_check"
    """Quick Links' status checks: any URL on the page, never a label (ADR-0052)."""
    ARGOCD = "argocd"
    """An ArgoCD's applications, for Quick Links' counts (ADR-0052)."""


class PlacementDecision(StrEnum):
    """How a create came out of day1's MCE placement check (ADR-0050)."""

    PICKED = "picked"
    """Wingman's pick."""
    OVERRIDE = "override"
    """An admin's other choice, with a reason."""
    REFUSED = "refused"
    """An MCE that fails a check, an override without a reason, or a stale pick."""


class Outcome(StrEnum):
    """How a dependency call ended."""

    OK = "ok"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    CONFLICT = "conflict"
    NOT_MERGEABLE = "not_mergeable"
    DENIED = "denied"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


ALERTED_OUTCOMES: Final = (Outcome.OK, Outcome.DENIED, Outcome.UNAVAILABLE, Outcome.AMBIGUOUS)
"""Outcomes the alert rules use; their series exist from start-up."""

_OUTCOME_OF: Final[tuple[tuple[type[Exception], Outcome], ...]] = (
    (NotFoundError, Outcome.NOT_FOUND),
    (AlreadyExistsError, Outcome.ALREADY_EXISTS),
    (RevisionConflictError, Outcome.CONFLICT),
    (NotMergeableError, Outcome.NOT_MERGEABLE),
    (PermissionDeniedError, Outcome.DENIED),
    (InvalidRequestError, Outcome.REJECTED),
    (GitUnavailableError, Outcome.UNAVAILABLE),
    (AmbiguousWriteError, Outcome.AMBIGUOUS),
)


class GitLabOperation(StrEnum):
    """One GitLabPort method; the ``operation`` label of GitLab calls."""

    GET_PROJECT = "get_project"
    LIST_GROUP_PROJECTS = "list_group_projects"
    ACCESS_LEVEL = "access_level"
    READ_FILE = "read_file"
    LIST_TREE = "list_tree"
    LIST_BRANCHES = "list_branches"
    GET_BRANCH = "get_branch"
    READ_ARCHIVE = "read_archive"
    CREATE_BRANCH = "create_branch"
    COMMIT = "commit"
    LIST_COMMITS = "list_commits"
    GET_COMMIT = "get_commit"
    COMMIT_DIFF = "commit_diff"
    CREATE_MERGE_REQUEST = "create_merge_request"
    GET_MERGE_REQUEST = "get_merge_request"
    LIST_MERGE_REQUESTS = "list_merge_requests"
    MERGE_REQUEST_DIFF = "merge_request_diff"
    APPROVE_MERGE_REQUEST = "approve_merge_request"
    MERGE_MERGE_REQUEST = "merge_merge_request"
    CLOSE_MERGE_REQUEST = "close_merge_request"


def outcome_of(error: BaseException | None) -> Outcome:
    """The outcome label for a call that raised ``error`` (``None``: it succeeded)."""
    if error is None:
        return Outcome.OK
    for error_type, outcome in _OUTCOME_OF:
        if isinstance(error, error_type):
            return outcome
    return Outcome.ERROR


def method_label(method: str) -> str:
    """An HTTP method, or ``other`` for anything non-standard."""
    upper = method.upper()
    return upper if upper in _HTTP_METHODS else OTHER


def status_class(status: int) -> str:
    """``2xx`` .. ``5xx``; ``other`` outside 100-599."""
    return f"{status // 100}xx" if 100 <= status <= 599 else OTHER


class WingmanMetrics:
    """Every collector a service exports, registered on one registry."""

    def __init__(
        self, registry: CollectorRegistry, *, component: str, version: str, commit: str
    ) -> None:
        """Register the catalogue on ``registry`` and set the build info."""
        self.registry = registry
        self.build_info = Gauge(
            "wingman_build_info",
            "Always 1; the labels say which build is running.",
            ["component", "version", "commit"],
            registry=registry,
        )
        self.build_info.labels(component=component, version=version, commit=commit).set(1)
        self.http_requests = Counter(
            "wingman_http_requests_total",
            "HTTP requests served, by route template and status class.",
            ["method", "route", "status_class"],
            registry=registry,
        )
        self.http_request_duration = Histogram(
            "wingman_http_request_duration_seconds",
            "Time to serve an HTTP request, by route template.",
            ["method", "route"],
            buckets=_LATENCY_BUCKETS,
            registry=registry,
        )
        self.dependency_requests = Counter(
            "wingman_dependency_requests_total",
            "Calls to an external system, by operation and outcome.",
            ["dependency", "operation", "outcome"],
            registry=registry,
        )
        self.dependency_request_duration = Histogram(
            "wingman_dependency_request_duration_seconds",
            "Time spent in a call to an external system, retries included.",
            ["dependency", "operation"],
            buckets=_LATENCY_BUCKETS,
            registry=registry,
        )
        self.placement_decisions = Counter(
            "wingman_placement_decisions_total",
            "Creates that passed or failed day1's MCE placement check, by decision.",
            ["decision"],
            registry=registry,
        )
        for operation in GitLabOperation:
            for outcome in ALERTED_OUTCOMES:
                self.dependency_requests.labels(Dependency.GITLAB, operation, outcome)

    def observe_http(self, *, method: str, route: str, status: int, seconds: float) -> None:
        """Record one served request. ``route`` must be a template, never a raw path."""
        label = method_label(method)
        self.http_requests.labels(label, route, status_class(status)).inc()
        self.http_request_duration.labels(label, route).observe(seconds)

    def observe_placement(self, decision: str) -> None:
        """Count one create's placement decision; anything but a ``PlacementDecision`` is other."""
        values = {d.value for d in PlacementDecision}
        self.placement_decisions.labels(decision if decision in values else OTHER).inc()

    def observe_dependency(
        self, dependency: Dependency, operation: StrEnum, outcome: Outcome, seconds: float
    ) -> None:
        """Record one call to an external system."""
        self.dependency_requests.labels(dependency, operation, outcome).inc()
        self.dependency_request_duration.labels(dependency, operation).observe(seconds)
