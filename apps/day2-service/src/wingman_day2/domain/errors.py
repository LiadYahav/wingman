"""Errors the day2 rules raise. The API layer maps each one to an RFC 9457 problem."""

from __future__ import annotations

from collections.abc import Mapping


class Day2Error(Exception):
    """Base class: a human ``detail`` plus structured ``details`` for clients."""

    def __init__(self, detail: str, *, details: Mapping[str, object] | None = None) -> None:
        """Keep ``detail`` for people and ``details`` for clients."""
        super().__init__(detail)
        self.detail = detail
        self.details: dict[str, object] = dict(details or {})


class InvalidClusterIdError(Day2Error):
    """A cluster id or name that cannot name a day2 destination."""


class UnknownTeamError(Day2Error):
    """No project of that name in the sigs group."""


class UnknownClusterError(Day2Error):
    """No destination with that id or name in day1 or any team repo."""


class AmbiguousClusterError(Day2Error):
    """A bare cluster name matches more than one destination; use its id."""


class UnknownChartError(Day2Error):
    """The team has no ``operators/<chart>/`` and the request gave no ``repourl``."""


class ChartNotInstalledError(Day2Error):
    """The chart is not deployed to that cluster by that team."""


class ChartAlreadyInstalledError(Day2Error):
    """The chart folder exists already, or a fleet default deploys the chart there (XOR rule)."""


class ChangeRefusedError(Day2Error):
    """The change would break a platform rule; ``details['rule']`` names it."""


class TeamReadOnlyError(Day2Error):
    """The team has not given Wingman's GitLab account write access to its project."""
