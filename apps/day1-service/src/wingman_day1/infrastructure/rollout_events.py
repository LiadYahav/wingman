"""MetricRolloutEvents: what flavor rollouts do, counted (``wingman_rollout_*``, ADR-0010).

Labels are only the run's trigger and the MR's outcome, both fixed sets: never
a flavor, a version or a cluster (docs/ops/metrics.md).
"""

from __future__ import annotations

from wingman_core.observability.metrics import (
    RolloutOutcome as MetricOutcome,
)
from wingman_core.observability.metrics import (
    RolloutTrigger as MetricTrigger,
)
from wingman_core.observability.metrics import (
    WingmanMetrics,
)
from wingman_day1.domain.rollout import RolloutOutcome, RolloutTrigger


class MetricRolloutEvents:
    """``RolloutEvents`` on the service's metrics; with none, it counts nothing."""

    def __init__(self, metrics: WingmanMetrics | None) -> None:
        """Count on ``metrics``."""
        self._metrics = metrics

    def run(self, trigger: RolloutTrigger) -> None:
        """See RolloutEvents.run."""
        if self._metrics is not None:
            self._metrics.observe_rollout_run(MetricTrigger(trigger.value))

    def merge_request(self, outcome: RolloutOutcome) -> None:
        """See RolloutEvents.merge_request."""
        if self._metrics is not None:
            self._metrics.observe_rollout_merge_request(MetricOutcome(outcome.value))
