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

from wingman_core.domain.git import FileChange, commit_author
from wingman_core.domain.merge_request import MergeRequest, NewMergeRequest
from wingman_core.domain.mr_conventions import (
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
        project = await self._repository.project()
        branch = branch_name(
            username=requested_by.username,
            action=f"{action}-{resource_type}",
            resource=resource_name,
            at=self._clock(),
        )
        await self._gitlab.commit(
            project.id,
            branch=branch,
            start_branch=project.default_branch,
            message=commit_message,
            changes=changes,
            author=commit_author(requested_by),
        )
        merge_request = await self._gitlab.create_merge_request(
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
                labels=(WINGMAN_LABEL, self._label, action),
            ),
        )
        self._repository.forget_merge_requests()
        return merge_request


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
        ref = change.cluster
        verb = _CLUSTER_VERBS[change.action]
        file_change = _file_change(change)
        extra = _title_extra(change)
        spec_line = f"\nSpec: {change.spec_name} v{change.spec_version}" if change.spec_name else ""
        merge_request = await self._writer.open(
            requested_by=change.requested_by,
            verb=verb,
            resource_type=ResourceType.CLUSTER,
            resource_name=ref.name,
            action=str(change.action),
            changes=[file_change],
            summary=change.summary,
            commit_message=(
                f"{verb} cluster {ref.name}{' ' + extra if extra else ''}\n\n"
                f"Site: {ref.site}, MCE: {ref.mce}{spec_line}\n"
                f"Requested-by: {change.requested_by.username}"
            ),
            title_extra=extra,
        )
        return ProvisionResult(merge_request)


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
