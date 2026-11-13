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


class UneditableFileError(InvalidInputError):
    """Wingman cannot change a cluster file's text safely; a person edits it by hand."""


class RenderError(InvalidInputError):
    """The cluster template could not be rendered with the given inputs."""


class InvalidSpecError(InvalidInputError):
    """A spec document is not a valid ClusterSpec."""


class InvalidNodepoolDefaultsError(InvalidInputError):
    """``nodepool-defaults.yaml`` exists but is not a valid defaults document."""


class ResourceNotFoundError(Day1Error):
    """A site, MCE, cluster, spec or commit that the request names does not exist."""


class AlreadyInUseError(Day1Error):
    """The name is taken: a cluster or spec exists, or an open MR already creates it."""


class AmbiguousNameError(Day1Error):
    """A bare cluster name matches clusters under more than one MCE."""


class StaleError(Day1Error):
    """What the caller read has changed since: a spec version, a file, a reviewed MR."""


class PlacementChangedError(StaleError):
    """The form showed one MCE as Wingman's pick, and the pick is now another (ADR-0050)."""

    def __init__(self, message: str, *, pick: str) -> None:
        """``pick`` is Wingman's pick now."""
        super().__init__(message)
        self.pick = pick


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


# ── server-scan and the workflows orchestrator (cluster nodes, ADR-0038) ─────


class ServerScanError(Day1Error):
    """Base class for errors reading server-scan, or writing a server's maintenance to it."""


class ServerScanUnavailableError(ServerScanError):
    """server-scan could not be reached or answered with an error: nodes are unknown, not none."""


class ServerScanDeniedError(ServerScanUnavailableError):
    """server-scan refused Wingman's token (401 or 403): a deployment problem.

    The viewer token on a read, the admin token on a maintenance write.
    """


class ServerScanNotConfiguredError(ServerScanError):
    """This deployment has no server-scan (``SERVER_SCAN_URL`` is empty)."""


class ServerNotFoundError(ServerScanError):
    """server-scan has no server with this id."""


class ServerScanWritesOffError(ServerScanError):
    """Maintenance writes are off here: a viewer token without server-scan's admin token."""


class ServerScanRefusedError(InvalidInputError):
    """server-scan refused a maintenance write's body (its 422); nothing changed."""


class AmbiguousServerScanWriteError(ServerScanError):
    """A maintenance write was sent but its outcome is unknown. Never retried (ADR-0006)."""


class NodeNotInClusterError(Day1Error):
    """server-scan does not place the server in the cluster the request names."""


class WorkflowsError(Day1Error):
    """Base class for errors talking to the workflows orchestrator."""


class WorkflowsNotConfiguredError(WorkflowsError):
    """This deployment has no orchestrator (``WORKFLOWS_API_URL`` is empty)."""


class WorkflowsUnavailableError(WorkflowsError):
    """The orchestrator could not be reached or answered with an error; nothing was started."""


class WorkflowRefusedError(WorkflowsUnavailableError):
    """The orchestrator refused the request as invalid (a 4xx); nothing was started."""


class UninstallAlreadyRunningError(WorkflowsError):
    """The orchestrator already runs an uninstall of this server (its 409)."""


class AmbiguousStartError(WorkflowsError):
    """A start was sent but its outcome is unknown: the run may exist. Never retried (ADR-0006)."""


class ProvisionAlreadyRunningError(AlreadyInUseError):
    """The orchestrator already runs a provision of this cluster (its 409, ADR-0042)."""


class ProvisionRefusedError(InvalidInputError):
    """The orchestrator refused the name or the file of a provision (its 422); nothing started."""


class UpgradeAlreadyRunningError(WorkflowsError):
    """The cluster already has an open upgrade-cluster run (the orchestrator's 409, ADR-0055)."""


class UpgradeRefusedError(InvalidInputError):
    """The orchestrator refused an upgrade's body (its 422); nothing started."""


class UpgradeDecisionRefusedError(WorkflowsError):
    """The run was not waiting for that decision (its validator's 409); the message is its words."""


class UpgradeTargetsRefusedError(WorkflowsError):
    """The workflow cannot use the cluster's file or the upgrade rules (its 409 to the targets)."""


class AmbiguousDecisionError(WorkflowsError):
    """A decision was sent but its outcome is unknown: it may have landed. Never retried."""


class AddServerAlreadyRunningError(WorkflowsError):
    """The orchestrator's 409 to adding servers: a named one installing, or every slot busy."""


class AddServerRefusedError(InvalidInputError):
    """The orchestrator refused a request to add servers (its 422); nothing started (ADR-0057)."""


# ── segments-manager (a cluster's EPG, checked against Git; ADR-0039) ────────


class SegmentsManagerUnavailableError(Day1Error):
    """segments-manager could not be reached or answered with an error: the EPG is unknown."""
