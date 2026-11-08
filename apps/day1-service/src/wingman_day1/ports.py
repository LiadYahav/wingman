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
from wingman_day1.domain.changes import ClusterChange, ProvisionResult, SpecChange
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.domain.workflows import WorkflowRun


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
    """An MCE hub's Kubernetes API: HostedClusters, NodePools, InfraEnvs.

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
