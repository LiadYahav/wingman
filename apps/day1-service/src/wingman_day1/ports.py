"""The interfaces day1's use cases need from the outside world (ADR-0001).

Each has an adapter in ``wingman_day1.infrastructure`` and a fake used by
tests and by ``WINGMAN_GIT_BACKEND=fake``. GitLab itself is
``wingman_core.ports.gitlab.GitLabPort``; :class:`RepoReads` is the cached
read side of one project on top of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from wingman_core.domain.git import Commit, FileContent, FileDiff, Project, RepoPath, TreeEntry
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.users import User
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.auth import Identity
from wingman_day1.domain.changes import ClusterChange, ImportChange, ProvisionResult, SpecChange
from wingman_day1.domain.machines import (
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.quick_links import ArgoCdReading, LinkReading
from wingman_day1.domain.servers import RunSummary, ServerDetail, ServerRow
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.domain.workflows import ProvisionRun, WorkflowRun


class RepoReads(Protocol):
    """Cached reads of one GitLab project (ADR-0011).

    Reads without a ``ref`` are at the project's default branch. Every method
    raises the ``wingman_core.domain.errors`` types; a missing file or
    directory is ``NotFoundError``.
    """

    async def project(self) -> Project:
        """The project, including its default branch."""
        ...

    async def tree(self, path: RepoPath, *, recursive: bool = False) -> list[TreeEntry]:
        """Entries under ``path`` at the default branch."""
        ...

    async def read(self, path: RepoPath, *, ref: str | None = None) -> FileContent:
        """A file's content and the commit it was read at (its ``last_commit_id``)."""
        ...

    async def last_change(self, path: RepoPath) -> Commit | None:
        """The newest commit that changed ``path``, as of the commit files are read at.

        A read's ``last_commit_id`` is that commit, not the file's own last
        change (ADR-0035); this is the file's own, for "changed by, at".
        """
        ...

    async def changed_since(self, path: RepoPath, commit_id: str) -> bool:
        """Whether ``path`` changed on the default branch after ``commit_id``.

        GitLab's own write guard asks the same (ADR-0035). An unknown commit
        counts as changed: Wingman asks for a reload rather than guess.
        """
        ...

    async def history(self, path: RepoPath, *, limit: int = 50) -> list[Commit]:
        """Commits on the default branch that changed ``path``, newest first."""
        ...

    async def commits(self, *, limit: int) -> list[Commit]:
        """The newest commits on the default branch."""
        ...

    async def commit(self, sha: str) -> Commit:
        """One commit (immutable, so cached for its key's TTL)."""
        ...

    async def commit_diff(self, sha: str) -> list[FileDiff]:
        """What one commit changed."""
        ...

    async def merge_requests(
        self, *, state: MRState | None, labels: Sequence[str] = (), limit: int = 100
    ) -> list[MergeRequest]:
        """Merge requests, newest first."""
        ...

    async def merge_request_diff(self, merge_request: MergeRequest) -> list[FileDiff]:
        """What an open merge request changes, at its head ``sha``.

        GitLab computes an MR's stored diff in the background, so a new MR's
        may be empty for a moment.
        """
        ...

    def forget_files(self) -> None:
        """Drop cached files, trees and history: the default branch (or a branch) moved."""
        ...

    def forget_merge_requests(self) -> None:
        """Drop cached merge-request lists: one was opened, updated, merged or closed."""
        ...


class ClusterProvisioner(Protocol):
    """Applies a cluster change. Today: a commit and a merge request (ADR-0017)."""

    async def apply(self, change: ClusterChange) -> ProvisionResult:
        """Propose ``change``; raises Git errors as they come (never retried)."""
        ...

    async def link(self, change: ImportChange) -> ProvisionResult:
        """Propose linking several cluster files to a flavor in one commit (ADR-0037)."""
        ...


class ClusterDeleteWorkflow(Protocol):
    """The delete-cluster workflow (ADR-0033). Not built yet: no adapter exists.

    It owns the ordered teardown: drain, remove the cluster's files, wait for
    ArgoCD to prune, wait for the released nodes to be wiped, delete the DHCP
    scope, and release the segment last.
    """

    async def latest_run(self, ref: ClusterRef) -> WorkflowRun | None:
        """The newest run for ``ref``, or ``None`` when it never ran."""
        ...

    async def start(self, ref: ClusterRef, *, requested_by: User) -> WorkflowRun:
        """Start a run for ``ref``; the orchestrator refuses a second one while one runs."""
        ...


class SpecChanges(Protocol):
    """Applies a spec change as a merge request in the specs project."""

    async def apply(self, change: SpecChange) -> ProvisionResult:
        """Propose ``change``; raises Git errors as they come (never retried)."""
        ...


class HubApi(Protocol):
    """An MCE hub's Kubernetes API, read only.

    HostedClusters, NodePools and InfraEnvs, each cluster's Machines,
    MachineSets, AgentMachines and Agents (ADR-0038), and the hub's own nodes
    and how many pods each runs, for placement's free pods (ADR-0050).

    Raises ``HubNotConfiguredError``, ``HubObjectNotFoundError``,
    ``HubDeniedError`` or ``HubUnavailableError`` (``wingman_day1.domain.errors``).
    """

    async def hosted_cluster(
        self, mce: str, *, namespace: str, name: str
    ) -> HostedClusterObservation:
        """One HostedCluster."""
        ...

    async def node_pools(self, mce: str, *, namespace: str) -> list[NodePoolObservation]:
        """Every NodePool in a namespace, sorted by name."""
        ...

    async def infra_envs(self, mce: str, *, namespace: str | None) -> list[str]:
        """InfraEnv names in ``namespace`` (or the whole hub), sorted."""
        ...

    async def machines(self, mce: str, *, namespace: str) -> list[MachineObservation]:
        """CAPI Machines in a cluster's control-plane namespace, sorted by name."""
        ...

    async def machine_sets(self, mce: str, *, namespace: str) -> list[MachineSetObservation]:
        """CAPI MachineSets in a cluster's control-plane namespace, sorted by name."""
        ...

    async def agent_machines(self, mce: str, *, namespace: str) -> list[AgentMachineObservation]:
        """AgentMachines in a cluster's control-plane namespace, sorted by name."""
        ...

    async def agents(self, mce: str, *, namespace: str) -> list[AgentObservation]:
        """Agents in a HostedCluster's agent namespace, sorted by name."""
        ...

    async def nodes(self, mce: str) -> list[NodeObservation]:
        """The hub cluster's own nodes, sorted by name."""
        ...

    async def pods_per_node(self, mce: str) -> dict[str, int]:
        """How many pods that are not ``Succeeded`` or ``Failed`` each node runs.

        Across every namespace; a pod not bound to a node yet counts for none.
        """
        ...


class IdentityProvider(Protocol):
    """OpenShift OAuth: where to send the browser, and who came back."""

    async def authorize_url(self) -> str:
        """The URL the login page redirects to."""
        ...

    async def identify(self, code: str) -> Identity:
        """Exchange an authorization code and read the user. Raises ``IdentityError``."""
        ...


class SessionIssuer(Protocol):
    """Issues Wingman's own session token (``wingman_core``'s SessionTokens)."""

    def issue(self, user: User) -> str:
        """A signed, short-lived token for ``user``."""
        ...


class Day2Addons(Protocol):
    """What the day2 service reports as installed. Raises ``Day2UnavailableError``."""

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """Addons installed on ``cluster``."""
        ...


class ServerInventory(Protocol):
    """server-scan: the platform's record of physical servers (read only, ADR-0038).

    Raises ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a
    refused token) when server-scan cannot answer: servers are then unknown,
    never "none".
    """

    async def rows(self) -> list[ServerRow]:
        """Every server in the fleet, as flat rows."""
        ...

    async def server(self, server_id: str) -> ServerDetail:
        """One server, read now. An unknown id is ``ServerNotFoundError``."""
        ...


class UninstallWorkflow(Protocol):
    """The orchestrator's ``uninstall-server-from-hc`` workflow (ADR-0038).

    The workflow owns the procedure and its checks; Wingman only starts a run
    and reads how it is going. Reads raise ``WorkflowsUnavailableError``.
    """

    async def runs(self) -> list[RunSummary]:
        """The newest uninstall runs of the whole fleet, newest first."""
        ...

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        """One run's status, step and error; ``None`` when the orchestrator has no such run."""
        ...

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        """Start an uninstall of one server. Never retried (ADR-0006).

        Raises ``UninstallAlreadyRunningError`` while one runs for the server,
        ``WorkflowsUnavailableError`` when nothing was started, and
        ``AmbiguousStartError`` when it was sent but the answer was lost.
        """
        ...


class ProvisionWorkflow(Protocol):
    """The orchestrator's ``provision-cluster`` workflow (ADR-0042).

    It takes the cluster file, reserves the segment, pushes the file on its
    own branch, opens the merge request, waits for the merge and registers
    the cluster in day2. Wingman starts a run and reads how it is going.
    """

    async def start(self, *, cluster: str, mce: str, content: str) -> ProvisionRun:
        """Start provisioning ``cluster`` (no ``ocp4-``) in MCE folder ``mce`` from ``content``.

        Never retried (ADR-0006). Raises ``ProvisionAlreadyRunningError``
        while a run for the cluster is going, ``ProvisionRefusedError`` for a
        name or file the orchestrator refuses, ``WorkflowsUnavailableError``
        when nothing was started, and ``AmbiguousStartError`` when it was
        sent but the answer was lost.
        """
        ...

    async def run(self, workflow_id: str) -> ProvisionRun | None:
        """One run's status, phase, merge request and error; ``None`` when there is none."""
        ...


class LinkProbe(Protocol):
    """Checks whether something answers at a URL, for Quick Links' status dots (ADR-0052)."""

    async def check(self, url: str) -> LinkReading:
        """What asking ``url`` found; never raises (a failure is a down or unknown reading)."""
        ...


class ArgoCdApi(Protocol):
    """ArgoCD instances' application lists, with a read-only token each (ADR-0052)."""

    def has_token(self, instance: str) -> bool:
        """Whether a token for ``instance`` is configured; without one it is never called."""
        ...

    async def application_counts(self, instance: str, url: str) -> ArgoCdReading:
        """The applications at ``url`` (the ArgoCD's base URL), counted. Never raises."""
        ...


class LinksFileSource(Protocol):
    """The team's links file, as text (ADR-0052)."""

    @property
    def path(self) -> str:
        """Where it is read from, for the page to name."""
        ...

    async def read(self) -> str | None:
        """Its text; ``None`` when there is no file. Raises ``LinksFileUnreadableError``."""
        ...


class SegmentLedger(Protocol):
    """segments-manager: the platform's ledger of VLAN segments (read only, ADR-0039).

    Raises ``SegmentsManagerUnavailableError`` when segments-manager cannot
    answer: the EPG is then unknown, never "none". Nothing is ever written to it.
    """

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """The segment ``cidr`` (``a.b.c.0/24``); ``None`` when segments-manager has no such one."""
        ...
