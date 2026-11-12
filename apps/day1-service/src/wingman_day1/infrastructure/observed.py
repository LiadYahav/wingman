"""Metrics for day1's calls to systems other than GitLab (ADR-0010).

GitLab calls are counted by ``InstrumentedGitLab``. The MCE hub APIs,
OpenShift OAuth, the day2 service, server-scan, the workflows orchestrator
and segments-manager are counted here, on the same
``wingman_dependency_*`` families, with an ``operation`` from a fixed enum
(listed in ``docs/ops/metrics.md``) and an ``outcome`` derived from the
day1 domain error the adapter raised.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum

from wingman_core.observability.metrics import Dependency, Outcome, WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    Day2UnavailableError,
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    IdentityError,
    IdentityUnavailableError,
    ProvisionAlreadyRunningError,
    ProvisionRefusedError,
    SegmentsManagerUnavailableError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)

Timer = Callable[[], float]


class HubOperation(StrEnum):
    """Calls to an MCE hub's Kubernetes API (``dependency="kubernetes"``)."""

    GET_HOSTED_CLUSTER = "get_hosted_cluster"
    LIST_NODE_POOLS = "list_node_pools"
    LIST_INFRA_ENVS = "list_infra_envs"
    LIST_MACHINES = "list_machines"
    LIST_MACHINE_SETS = "list_machine_sets"
    LIST_AGENT_MACHINES = "list_agent_machines"
    LIST_AGENTS = "list_agents"
    LIST_NODES = "list_nodes"
    """One page of the hub's nodes (placement's free pods, ADR-0050)."""
    LIST_PODS = "list_pods"
    """One page of the hub's non-terminal pods, as Table rows (ADR-0050)."""


class OAuthOperation(StrEnum):
    """Calls to OpenShift OAuth and the user API (``dependency="openshift_oauth"``)."""

    DISCOVER = "discover"
    EXCHANGE_CODE = "exchange_code"
    GET_USER = "get_user"


class Day2Operation(StrEnum):
    """Calls to the day2 service (``dependency="day2"``)."""

    LIST_INSTALLED_ADDONS = "list_installed_addons"


class ServerScanOperation(StrEnum):
    """Calls to server-scan (``dependency="server_scan"``)."""

    LIST_SERVER_ROWS = "list_server_rows"
    GET_SERVER = "get_server"


class SegmentsManagerOperation(StrEnum):
    """Calls to segments-manager (``dependency="segments_manager"``)."""

    GET_SEGMENT = "get_segment"


class WorkflowsOperation(StrEnum):
    """Calls to the workflows orchestrator (``dependency="workflows"``)."""

    LIST_RUNS = "list_runs"
    GET_RUN = "get_run"
    START_UNINSTALL = "start_uninstall"
    START_PROVISION = "start_provision"


_OUTCOME_OF: tuple[tuple[type[Exception], Outcome], ...] = (
    (HubObjectNotFoundError, Outcome.NOT_FOUND),
    (HubDeniedError, Outcome.DENIED),
    (HubUnavailableError, Outcome.UNAVAILABLE),
    (Day2UnavailableError, Outcome.UNAVAILABLE),
    (HubNotConfiguredError, Outcome.REJECTED),
    (IdentityUnavailableError, Outcome.UNAVAILABLE),
    (IdentityError, Outcome.DENIED),
    (ServerNotFoundError, Outcome.NOT_FOUND),
    (ServerScanDeniedError, Outcome.DENIED),
    (ServerScanUnavailableError, Outcome.UNAVAILABLE),
    (UninstallAlreadyRunningError, Outcome.CONFLICT),
    (ProvisionAlreadyRunningError, Outcome.CONFLICT),
    (ProvisionRefusedError, Outcome.REJECTED),
    (AmbiguousStartError, Outcome.AMBIGUOUS),
    (WorkflowRefusedError, Outcome.REJECTED),
    (WorkflowsUnavailableError, Outcome.UNAVAILABLE),
    (SegmentsManagerUnavailableError, Outcome.UNAVAILABLE),
)


def outcome_of(error: BaseException | None) -> Outcome:
    """The outcome label for a call that raised ``error`` (``None``: it succeeded)."""
    if error is None:
        return Outcome.OK
    for error_type, outcome in _OUTCOME_OF:
        if isinstance(error, error_type):
            return outcome
    return Outcome.ERROR


class Observer:
    """Times and counts calls to one dependency; a no-op without metrics."""

    def __init__(
        self,
        dependency: Dependency,
        metrics: WingmanMetrics | None,
        *,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Record calls to ``dependency`` on ``metrics``; ``timer`` is injectable for tests."""
        self._dependency = dependency
        self._metrics = metrics
        self._timer = timer

    async def call[T](self, operation: StrEnum, call: Awaitable[T]) -> T:
        """Await ``call``, recording its duration and outcome under ``operation``."""
        start = self._timer()
        error: BaseException | None = None
        try:
            return await call
        except BaseException as exc:
            error = exc
            raise
        finally:
            if self._metrics is not None:
                self._metrics.observe_dependency(
                    self._dependency, operation, outcome_of(error), self._timer() - start
                )
