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
from wingman_core.domain.merge_request import MergeRequest, MergeRequestRef, MRState
from wingman_core.domain.users import User
from wingman_day1.domain.addons import (
    Day2InstallRequest,
    Day2InstallResult,
    InstalledAddon,
    RequestedAddon,
)
from wingman_day1.domain.auth import Identity
from wingman_day1.domain.changes import ClusterChange, ProvisionResult, SpecChange
from wingman_day1.domain.machines import (
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.rollout import RolloutOutcome, RolloutTrigger
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
    """Applies a cluster change. Today: a commit and a merge request (ADR-0017).

    One change is one cluster file, so each cluster's change is reviewed,
    merged or rejected on its own; importing several clusters into a flavor
    is one change each (ADR-0044).
    """

    async def apply(self, change: ClusterChange) -> ProvisionResult:
        """Propose ``change``; raises Git errors as they come (never retried)."""
        ...


class RolloutMergeRequests(Protocol):
    """Day1 MRs that move a cluster to a flavor version, on a branch that names them (ADR-0044).

    The branch is ``mr_conventions.rollout_branch(flavor, version, cluster)``:
    a second run, or a second replica, finds the branch or its MR instead of
    opening another. Nothing is retried (ADR-0006).
    """

    async def branch_exists(self, branch: str) -> bool:
        """Whether ``branch`` exists in the day1 project."""
        ...

    async def open(self, change: ClusterChange, *, branch: str) -> MergeRequest:
        """Commit ``change`` on the new branch ``branch`` and open its MR (labelled ``rollout``)."""
        ...

    async def open_for_branch(self, change: ClusterChange, *, branch: str) -> MergeRequest:
        """Open the MR of ``branch``, which an earlier run committed to; no new commit."""
        ...

    async def supersede(self, old: MergeRequestRef, *, note: str) -> None:
        """Comment ``note`` on the open MR ``old``, then close it."""
        ...


class RolloutEvents(Protocol):
    """Counts what flavor rollouts do (``wingman_rollout_*``, docs/ops/metrics.md)."""

    def run(self, trigger: RolloutTrigger) -> None:
        """A run started."""
        ...

    def merge_request(self, outcome: RolloutOutcome) -> None:
        """A run did ``outcome`` with one cluster's MR."""
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

    async def infra_env_agents(
        self, mce: str, *, infra_envs: Sequence[str], namespace: str | None
    ) -> list[AgentObservation]:
        """The Agents of these InfraEnvs, in ``namespace`` or the whole hub, sorted by name."""
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


class Day2Installs(Protocol):
    """Day2 opening add-on install MRs for a flavor's rollout (ADR-0044).

    Day1 never writes a day2 repo itself: it asks the day2 service, which
    opens its MRs as for any request (one per team). Raises
    ``Day2UnavailableError`` when day2 does not answer, or answers with a
    server error; a request day2 may have acted on is never resent (the next
    rollout run reads ``open_installs`` first).
    """

    async def open_installs(self, cluster: ClusterRef) -> list[Day2InstallRequest]:
        """Day2's open Wingman MRs that install add-ons on ``cluster``."""
        ...

    async def install(
        self, cluster: ClusterRef, addons: Sequence[RequestedAddon], *, message: str
    ) -> Day2InstallResult:
        """Ask day2 to install ``addons`` on ``cluster``: an MR per team; refusals in ``failed``."""
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
