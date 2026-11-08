"""Metrics for day1's calls to systems other than GitLab (ADR-0010).

GitLab calls are counted by ``InstrumentedGitLab``. The MCE hub APIs,
OpenShift OAuth and the day2 service are counted here, on the same
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
    Day2UnavailableError,
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    IdentityError,
    IdentityUnavailableError,
)

Timer = Callable[[], float]


class HubOperation(StrEnum):
    """Calls to an MCE hub's Kubernetes API (``dependency="kubernetes"``)."""

    GET_HOSTED_CLUSTER = "get_hosted_cluster"
    LIST_NODE_POOLS = "list_node_pools"
    LIST_INFRA_ENVS = "list_infra_envs"


class OAuthOperation(StrEnum):
    """Calls to OpenShift OAuth and the user API (``dependency="openshift_oauth"``)."""

    DISCOVER = "discover"
    EXCHANGE_CODE = "exchange_code"
    GET_USER = "get_user"


class Day2Operation(StrEnum):
    """Calls to the day2 service (``dependency="day2"``)."""

    LIST_INSTALLED_ADDONS = "list_installed_addons"


_OUTCOME_OF: tuple[tuple[type[Exception], Outcome], ...] = (
    (HubObjectNotFoundError, Outcome.NOT_FOUND),
    (HubDeniedError, Outcome.DENIED),
    (HubUnavailableError, Outcome.UNAVAILABLE),
    (Day2UnavailableError, Outcome.UNAVAILABLE),
    (HubNotConfiguredError, Outcome.REJECTED),
    (IdentityUnavailableError, Outcome.UNAVAILABLE),
    (IdentityError, Outcome.DENIED),
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
