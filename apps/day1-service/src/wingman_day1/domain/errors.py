"""Errors the day1 domain and its ports raise.

They carry no HTTP status: the API layer maps each one to an RFC 9457
problem (ADR-0004). Git errors are ``wingman_core.domain.errors`` types and
are translated by the core handlers.
"""

from __future__ import annotations

from collections.abc import Sequence


class Day1Error(Exception):
    """Base class for day1 domain errors."""


class InvalidInputError(Day1Error):
    """A request is well-formed but breaks a day1 rule; ``problems`` lists each one."""

    def __init__(self, message: str, problems: Sequence[str] = ()) -> None:
        """``message`` summarizes; ``problems`` are the individual findings."""
        super().__init__(message)
        self.problems: tuple[str, ...] = tuple(problems)


class InvalidClusterFileError(InvalidInputError):
    """A cluster values file (rendered or edited) breaks the values-file contract."""


class RenderError(InvalidInputError):
    """The cluster template could not be rendered with the given inputs."""


class InvalidSpecError(InvalidInputError):
    """A spec document is not a valid ClusterSpec."""


class ResourceNotFoundError(Day1Error):
    """A site, MCE, cluster, spec or commit that the request names does not exist."""


class AlreadyInUseError(Day1Error):
    """The name is taken: a cluster or spec exists, or an open MR already creates it."""


class AmbiguousNameError(Day1Error):
    """A bare cluster name matches clusters under more than one MCE."""


class StaleError(Day1Error):
    """What the caller read has changed since: a spec version, a file, a reviewed MR."""


# ── MCE hub API (cluster status, InfraEnvs) ──────────────────────────────────


class HubError(Day1Error):
    """Base class for errors reading an MCE hub's Kubernetes API."""


class HubNotConfiguredError(HubError):
    """Wingman has no credentials (or no address) for this MCE."""


class HubObjectNotFoundError(HubError):
    """The HostedCluster (or namespace) does not exist on the hub."""


class HubDeniedError(HubError):
    """The hub refused Wingman's token (401) or its permissions (403)."""


class HubUnavailableError(HubError):
    """The hub could not be reached, timed out or answered with a server error."""


# ── Login and other services ─────────────────────────────────────────────────


class IdentityError(Day1Error):
    """A login was refused: OpenShift rejected the code or token, or the dev secret is wrong."""


class IdentityUnavailableError(IdentityError):
    """OpenShift OAuth could not be reached or answered with a server error."""


class LoginRefusedError(Day1Error):
    """The person is who they say, but no Wingman group lets them in."""


class Day2UnavailableError(Day1Error):
    """The day2 service could not answer, so addon state is unknown (never "none")."""
