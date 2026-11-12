"""Proposing changes as merge requests: the ``ClusterProvisioner`` Wingman uses today.

Each change is exactly one commit on a new branch cut from the project's
default branch, plus one merge request back into it (ADR-0017):

- branch ``platform/<user>/<action>-<resource>-<UTC stamp>``, title
  ``[Wingman/Day1] Create cluster <name> from spec <spec>`` and the
  description footer, all from ``wingman_core.domain.mr_conventions``
  (ADR-0007);
- labels ``wingman``, the repository's label (``day1``/``specs``) and the action;
- the commit is authored by the requesting user;
- an update or delete carries the ``last_commit_id`` it was read at (ADR-0006).

Nothing is retried; nothing force-pushes. CI and the allocate-segment
workflow then add their own commits to the branch. Opening an MR clears the
repository's cached MR lists before the API answers.

When the ``create-cluster`` workflow exists, a second ``ClusterProvisioner``
that starts it replaces :class:`GitClusterProvisioner` in ``main.py``; the use
cases do not change.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import FileChange, commit_author
from wingman_core.domain.merge_request import MergeRequest, MergeRequestRef, NewMergeRequest
from wingman_core.domain.mr_conventions import (
    ROLLOUT_LABEL,
    WINGMAN_LABEL,
    MRMetadata,
    Repo,
    ResourceType,
    Verb,
    branch_name,
    mr_description,
    mr_title,
)
from wingman_core.domain.users import User
from wingman_core.ports.clock import Clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_day1.domain import paths
from wingman_day1.domain.changes import (
    ClusterAction,
    ClusterChange,
    ProvisionResult,
    SpecAction,
    SpecChange,
)
from wingman_day1.infrastructure.repositories import CachedRepository


class MergeRequestWriter:
    """Opens one-commit merge requests in one project."""

    def __init__(
        self,
        gitlab: GitLabPort,
        repository: CachedRepository,
        *,
        repo: Repo,
        label: str,
        clock: Clock,
    ) -> None:
        """``repo`` goes into titles and footers, ``label`` onto every MR."""
        self._gitlab = gitlab
        self._repository = repository
        self._repo = repo
        self._label = label
        self._clock = clock

    async def open(
        self,
        *,
        requested_by: User,
        verb: Verb,
        resource_type: ResourceType,
        resource_name: str,
        action: str,
        changes: Sequence[FileChange],
        summary: str,
        commit_message: str,
        title_extra: str = "",
    ) -> MergeRequest:
        """Commit ``changes`` on a new branch and open the MR; returns it."""
        branch = branch_name(
            username=requested_by.username,
            action=f"{action}-{resource_type}",
            resource=resource_name,
            at=self._clock(),
        )
        await self.commit(
            branch=branch,
            requested_by=requested_by,
            changes=changes,
            commit_message=commit_message,
        )
        return await self.open_merge_request(
            branch=branch,
            requested_by=requested_by,
            verb=verb,
            resource_type=resource_type,
            resource_name=resource_name,
            action=action,
            summary=summary,
            title_extra=title_extra,
        )

    async def commit(
        self,
        *,
        branch: str,
        requested_by: User,
        changes: Sequence[FileChange],
        commit_message: str,
    ) -> None:
        """Commit ``changes`` on the new branch ``branch``, cut from the default branch."""
        project = await self._repository.project()
        await self._gitlab.commit(
            project.id,
            branch=branch,
            start_branch=project.default_branch,
            message=commit_message,
            changes=changes,
            author=commit_author(requested_by),
        )

    async def open_merge_request(
        self,
        *,
        branch: str,
        requested_by: User,
        verb: Verb,
        resource_type: ResourceType,
        resource_name: str,
        action: str,
        summary: str,
        title_extra: str = "",
        extra_labels: Sequence[str] = (),
    ) -> MergeRequest:
        """Open the MR of ``branch`` into the default branch, with the title and footer."""
        project = await self._repository.project()
        try:
            return await self._gitlab.create_merge_request(
                project.id,
                NewMergeRequest(
                    source_branch=branch,
                    target_branch=project.default_branch,
                    title=mr_title(self._repo, verb, resource_type, resource_name, title_extra),
                    description=mr_description(
                        summary,
                        MRMetadata(
                            author=requested_by.username,
                            action=action,
                            resource_type=resource_type,
                            resource_name=resource_name,
                            repo=self._repo,
                        ),
                    ),
                    labels=(WINGMAN_LABEL, self._label, action, *extra_labels),
                ),
            )
        finally:
            self._repository.forget_merge_requests()


_CLUSTER_VERBS: Final = {
    ClusterAction.CREATE: Verb.CREATE,
    ClusterAction.MODIFY: Verb.MODIFY,
    ClusterAction.DELETE: Verb.DELETE,
    ClusterAction.SYNC: Verb.SYNC,
    ClusterAction.IMPORT: Verb.IMPORT,
}


class GitClusterProvisioner:
    """``ClusterProvisioner``: a cluster change becomes a merge request in the day1 repo."""

    def __init__(self, writer: MergeRequestWriter) -> None:
        """Open MRs through ``writer`` (the day1 project's)."""
        self._writer = writer

    async def apply(self, change: ClusterChange) -> ProvisionResult:
        """See ClusterProvisioner.apply."""
        merge_request = await self._writer.open(
            requested_by=change.requested_by,
            verb=_CLUSTER_VERBS[change.action],
            resource_type=ResourceType.CLUSTER,
            resource_name=change.cluster.name,
            action=str(change.action),
            changes=[_file_change(change)],
            summary=change.summary,
            commit_message=_commit_message(change),
            title_extra=_title_extra(change),
        )
        return ProvisionResult(merge_request)


class GitRolloutMergeRequests:
    """``RolloutMergeRequests``: a cluster's sync MR on the branch its rollout names (ADR-0044)."""

    def __init__(
        self, gitlab: GitLabPort, repository: CachedRepository, writer: MergeRequestWriter
    ) -> None:
        """Act in ``repository``'s project (day1's), opening MRs through ``writer``."""
        self._gitlab = gitlab
        self._repository = repository
        self._writer = writer

    async def branch_exists(self, branch: str) -> bool:
        """See RolloutMergeRequests.branch_exists."""
        project = await self._repository.project()
        try:
            await self._gitlab.get_branch(project.id, branch)
        except NotFoundError:
            return False
        return True

    async def open(self, change: ClusterChange, *, branch: str) -> MergeRequest:
        """See RolloutMergeRequests.open: one commit on ``branch``, then its MR."""
        await self._writer.commit(
            branch=branch,
            requested_by=change.requested_by,
            changes=[_file_change(change)],
            commit_message=_commit_message(change),
        )
        return await self.open_for_branch(change, branch=branch)

    async def open_for_branch(self, change: ClusterChange, *, branch: str) -> MergeRequest:
        """See RolloutMergeRequests.open_for_branch."""
        return await self._writer.open_merge_request(
            branch=branch,
            requested_by=change.requested_by,
            verb=_CLUSTER_VERBS[change.action],
            resource_type=ResourceType.CLUSTER,
            resource_name=change.cluster.name,
            action=str(change.action),
            summary=change.summary,
            title_extra=_title_extra(change),
            extra_labels=(ROLLOUT_LABEL,),
        )

    async def supersede(self, old: MergeRequestRef, *, note: str) -> None:
        """See RolloutMergeRequests.supersede: the comment first, so a closed MR always says why."""
        try:
            await self._gitlab.comment_on_merge_request(old, note)
            await self._gitlab.close_merge_request(old)
        finally:
            self._repository.forget_merge_requests()


def _commit_message(change: ClusterChange) -> str:
    ref = change.cluster
    extra = _title_extra(change)
    spec_line = f"\nSpec: {change.spec_name} v{change.spec_version}" if change.spec_name else ""
    return (
        f"{_CLUSTER_VERBS[change.action]} cluster {ref.name}{' ' + extra if extra else ''}\n\n"
        f"Site: {ref.site}, MCE: {ref.mce}{spec_line}\n"
        f"Requested-by: {change.requested_by.username}"
    )


def _title_extra(change: ClusterChange) -> str:
    if change.action is ClusterAction.CREATE and change.spec_name:
        return f"from spec {change.spec_name}"
    if change.action is ClusterAction.SYNC and change.spec_name:
        return f"to spec {change.spec_name} v{change.spec_version}"
    if change.action is ClusterAction.IMPORT:
        return f"into spec {change.spec_name} v{change.spec_version}"
    return ""


def _file_change(change: ClusterChange) -> FileChange:
    path = change.cluster.path
    if change.action is ClusterAction.DELETE:
        return FileChange.delete(path, last_commit_id=change.last_commit_id)
    content = change.content or ""
    if change.action is ClusterAction.CREATE:
        return FileChange.create(path, content)
    return FileChange.update(path, content, last_commit_id=change.last_commit_id)


_SPEC_VERBS: Final = {
    SpecAction.CREATE: Verb.CREATE,
    SpecAction.UPDATE: Verb.UPDATE,
    SpecAction.DELETE: Verb.DELETE,
}


class GitSpecChanges:
    """``SpecChanges``: a spec change becomes a merge request in the specs project."""

    def __init__(self, writer: MergeRequestWriter, *, specs_root: str) -> None:
        """Open MRs through ``writer`` (the specs project's); specs live under ``specs_root``."""
        self._writer = writer
        self._specs_root = specs_root

    async def apply(self, change: SpecChange) -> ProvisionResult:
        """See SpecChanges.apply."""
        path = paths.spec_file(self._specs_root, change.name)
        if change.action is SpecAction.DELETE:
            file_change = FileChange.delete(path, last_commit_id=change.last_commit_id)
        elif change.action is SpecAction.CREATE:
            file_change = FileChange.create(path, change.content or "")
        else:
            file_change = FileChange.update(
                path, change.content or "", last_commit_id=change.last_commit_id
            )
        verb = _SPEC_VERBS[change.action]
        merge_request = await self._writer.open(
            requested_by=change.requested_by,
            verb=verb,
            resource_type=ResourceType.SPEC,
            resource_name=change.name,
            action=str(change.action),
            changes=[file_change],
            summary=change.summary,
            commit_message=(
                f"{verb} spec {change.name} v{change.version}\n\n"
                f"Requested-by: {change.requested_by.username}"
            ),
            title_extra=f"to v{change.version}" if change.action is SpecAction.UPDATE else "",
        )
        return ProvisionResult(merge_request)
