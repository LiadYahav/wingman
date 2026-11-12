"""InMemoryGitLab: a GitLabPort with real semantics and no network.

It models what Wingman depends on, not all of GitLab: projects in groups,
branches, commits with full file trees, ``last_commit_id`` revision checks,
merge requests with per-project numbers, merges that change the target
branch, and conflicts. The contract suite runs the same tests against this
and against a real GitLab, so a behaviour asserted here is a behaviour GitLab
has (ADR-0005). It is not a mock: there is nothing to configure per test,
only state to seed.
"""

from __future__ import annotations

import difflib
import hashlib
import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from wingman_core.domain.errors import (
    AlreadyExistsError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    RevisionConflictError,
)
from wingman_core.domain.git import (
    Branch,
    ChangeKind,
    Commit,
    CommitAuthor,
    EntryKind,
    FileChange,
    FileContent,
    FileDiff,
    Project,
    RepoArchive,
    RepoPath,
    TreeEntry,
)
from wingman_core.domain.merge_request import (
    MergeRequest,
    MergeRequestRef,
    MRState,
    NewMergeRequest,
)
from wingman_core.ports.clock import Clock, system_clock


@dataclass(frozen=True, slots=True)
class _CommitRecord:
    id: str
    parents: tuple[str, ...]
    files: Mapping[str, str]
    file_commits: Mapping[str, str]
    title: str
    message: str
    authored_at: datetime
    sequence: int
    author: CommitAuthor | None = None


@dataclass(slots=True)
class _MergeRequestRecord:
    iid: int
    request: NewMergeRequest
    state: MRState
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    approvals: set[str] = field(default_factory=set)
    final_diff: list[FileDiff] | None = None
    """Frozen when the MR stops being open; its source branch may be deleted."""
    notes: list[str] = field(default_factory=list)
    """Comments, oldest first."""


@dataclass(slots=True)
class _ProjectRecord:
    project: Project
    branches: dict[str, str] = field(default_factory=dict)
    commits: dict[str, _CommitRecord] = field(default_factory=dict)
    merge_requests: dict[int, _MergeRequestRecord] = field(default_factory=dict)
    next_iid: int = 1


class InMemoryGitLab:
    """A GitLabPort backed by dictionaries. Not thread-safe; one event loop only."""

    def __init__(
        self,
        *,
        clock: Clock = system_clock,
        username: str = "wingman-bot",
        email: str = "wingman-bot@example.invalid",
        base_url: str = "http://gitlab.fake",
    ) -> None:
        """Start empty; add projects with :meth:`create_project`."""
        self._clock = clock
        self._username = username
        self._email = email
        self._base_url = base_url.rstrip("/")
        self._projects: dict[int, _ProjectRecord] = {}
        self._by_path: dict[str, int] = {}
        self._moved: dict[str, int] = {}
        """Old paths of renamed projects; GitLab keeps them as redirects."""
        self._ids = itertools.count(1)
        self._sequence = itertools.count(1)

    # ── Seeding (not part of the port) ──────────────────────────────────────

    def create_project(
        self,
        path_with_namespace: str,
        files: Mapping[str, str] | None = None,
        *,
        default_branch: str = "main",
        message: str = "Initial commit",
    ) -> Project:
        """Create a project whose default branch holds ``files`` in one commit."""
        if path_with_namespace in self._by_path:
            raise AlreadyExistsError(f"project {path_with_namespace} already exists")
        project_id = next(self._ids)
        project = Project(
            id=project_id,
            path_with_namespace=path_with_namespace,
            default_branch=default_branch,
            web_url=f"{self._base_url}/{path_with_namespace}",
        )
        record = _ProjectRecord(project=project)
        self._projects[project_id] = record
        self._by_path[path_with_namespace] = project_id
        tree = {str(RepoPath(path)): content for path, content in (files or {}).items()}
        root = self._new_commit(record, parents=(), files=tree, origins=(), message=message)
        record.branches[default_branch] = root.id
        return project

    def create_project_branch(
        self, project_id: int, branch: str, files: Mapping[str, str]
    ) -> Branch:
        """Create ``branch`` off the default branch with exactly ``files``, in one commit."""
        record = self._project(project_id)
        if branch in record.branches:
            raise AlreadyExistsError(f"branch {branch} already exists")
        base = record.commits[record.branches[record.project.default_branch]]
        tree = {str(RepoPath(path)): content for path, content in files.items()}
        commit = self._new_commit(
            record, parents=(base.id,), files=tree, origins=(base,), message=f"Release {branch}"
        )
        record.branches[branch] = commit.id
        return Branch(branch, commit.id)

    def rename_project(self, project_id: int, path_with_namespace: str) -> Project:
        """Move a project to a new path; the old one keeps finding it, as in GitLab."""
        record = self._project(project_id)
        if path_with_namespace in self._by_path:
            raise AlreadyExistsError(f"project {path_with_namespace} already exists")
        old = record.project.path_with_namespace
        del self._by_path[old]
        self._moved[old] = project_id
        self._moved.pop(path_with_namespace, None)
        self._by_path[path_with_namespace] = project_id
        record.project = replace(
            record.project,
            path_with_namespace=path_with_namespace,
            web_url=f"{self._base_url}/{path_with_namespace}",
        )
        return record.project

    def snapshot(self, project_id: int, ref: str) -> dict[str, str]:
        """Every file at ``ref`` as ``{path: content}``; for assertions in tests."""
        record = self._project(project_id)
        return dict(self._resolve(record, ref).files)

    def notes(self, ref: MergeRequestRef) -> list[str]:
        """The comments on a merge request, oldest first; for assertions in tests."""
        return list(self._mr(self._project(ref.project_id), ref.iid).notes)

    # ── Port: projects and files ────────────────────────────────────────────

    async def get_project(self, project: int | str) -> Project:
        """See GitLabPort.get_project."""
        if isinstance(project, str):
            found = self._by_path.get(project, self._moved.get(project))
            if found is None:
                raise NotFoundError(f"project {project} not found")
            project = found
        return self._project(project).project

    async def list_group_projects(self, group: str) -> list[Project]:
        """See GitLabPort.list_group_projects."""
        prefix = f"{group.strip('/')}/"
        found = [
            record.project
            for path, project_id in self._by_path.items()
            if path.startswith(prefix) and "/" not in path[len(prefix) :]
            for record in (self._projects[project_id],)
        ]
        if not found and not any(path.startswith(prefix) for path in self._by_path):
            raise NotFoundError(f"group {group} not found")
        return sorted(found, key=lambda p: p.path_with_namespace)

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        """See GitLabPort.read_file."""
        commit = self._resolve(self._project(project_id), ref)
        key = str(path)
        if key not in commit.files:
            raise NotFoundError(f"file {key} not found at {ref}")
        return FileContent(
            path=path, ref=ref, content=commit.files[key], last_commit_id=commit.file_commits[key]
        )

    async def list_tree(
        self, project_id: int, path: RepoPath, ref: str, *, recursive: bool = False
    ) -> list[TreeEntry]:
        """See GitLabPort.list_tree."""
        commit = self._resolve(self._project(project_id), ref)
        prefix = "" if path.is_root else f"{path}/"
        below = [file for file in commit.files if file.startswith(prefix)]
        if not path.is_root and not below:
            raise NotFoundError(f"tree {path} not found at {ref}")
        entries: dict[str, EntryKind] = {}
        for file in below:
            parts = file[len(prefix) :].split("/")
            depth = len(parts) if recursive else 1
            for i in range(1, min(depth, len(parts)) + 1):
                kind = EntryKind.FILE if i == len(parts) else EntryKind.DIRECTORY
                entries[prefix + "/".join(parts[:i])] = kind
        return [TreeEntry(RepoPath(p), kind) for p, kind in sorted(entries.items())]

    # ── Port: branches and commits ──────────────────────────────────────────

    async def list_branches(self, project_id: int) -> list[Branch]:
        """See GitLabPort.list_branches."""
        record = self._project(project_id)
        return [Branch(name, commit_id) for name, commit_id in sorted(record.branches.items())]

    async def get_branch(self, project_id: int, name: str) -> Branch:
        """See GitLabPort.get_branch."""
        record = self._project(project_id)
        if name not in record.branches:
            raise NotFoundError(f"branch {name} not found")
        return Branch(name, record.branches[name])

    async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
        """See GitLabPort.read_archive."""
        commit = self._resolve(self._project(project_id), sha)
        archive = RepoArchive(commit.id, {p: c.encode() for p, c in commit.files.items()})
        if archive.size > max_bytes:
            raise InvalidRequestError(f"the archive of {sha[:8]} is larger than {max_bytes} bytes")
        return archive

    async def create_branch(self, project_id: int, name: str, ref: str) -> Branch:
        """See GitLabPort.create_branch."""
        record = self._project(project_id)
        if name in record.branches:
            raise AlreadyExistsError(f"branch {name} already exists")
        record.branches[name] = self._resolve(record, ref).id
        return Branch(name, record.branches[name])

    async def commit(
        self,
        project_id: int,
        *,
        branch: str,
        message: str,
        changes: Sequence[FileChange],
        start_branch: str | None = None,
        author: CommitAuthor | None = None,
    ) -> Commit:
        """See GitLabPort.commit."""
        record = self._project(project_id)
        if not changes:
            raise InvalidRequestError("a commit needs at least one change")
        if start_branch is not None and branch not in record.branches:
            base = self._resolve(record, start_branch)
        elif branch in record.branches:
            base = record.commits[record.branches[branch]]
        else:
            raise NotFoundError(f"branch {branch} not found")
        files = dict(base.files)
        for change in changes:
            _apply(files, base.file_commits, change, self._file_commits_at(record))
        commit = self._new_commit(
            record,
            parents=(base.id,),
            files=files,
            origins=(base,),
            message=message,
            author=author,
        )
        record.branches[branch] = commit.id
        return self._commit_dto(record, commit)

    async def list_commits(
        self, project_id: int, *, ref: str, path: RepoPath | None = None, limit: int = 50
    ) -> list[Commit]:
        """See GitLabPort.list_commits."""
        record = self._project(project_id)
        reachable = self._ancestors(record, self._resolve(record, ref).id)
        commits = sorted(
            (record.commits[c] for c in reachable),
            key=lambda c: (c.authored_at, c.sequence),
            reverse=True,
        )
        if path is not None:
            commits = [c for c in commits if self._touches(record, c, path)]
        return [self._commit_dto(record, c) for c in commits[:limit]]

    async def get_commit(self, project_id: int, sha: str) -> Commit:
        """See GitLabPort.get_commit."""
        record = self._project(project_id)
        return self._commit_dto(record, self._commit_by_sha(record, sha))

    async def commit_diff(self, project_id: int, sha: str) -> list[FileDiff]:
        """See GitLabPort.commit_diff."""
        record = self._project(project_id)
        commit = self._commit_by_sha(record, sha)
        parent = record.commits[commit.parents[0]].files if commit.parents else {}
        return _diff(parent, commit.files)

    # ── Port: merge requests ────────────────────────────────────────────────

    async def create_merge_request(self, project_id: int, request: NewMergeRequest) -> MergeRequest:
        """See GitLabPort.create_merge_request."""
        record = self._project(project_id)
        for branch in (request.source_branch, request.target_branch):
            if branch not in record.branches:
                raise NotFoundError(f"branch {branch} not found")
        for existing in record.merge_requests.values():
            if (
                existing.state is MRState.OPENED
                and existing.request.source_branch == request.source_branch
                and existing.request.target_branch == request.target_branch
            ):
                raise AlreadyExistsError(
                    f"an open merge request already exists for {request.source_branch}: "
                    f"!{existing.iid}"
                )
        now = self._clock()
        mr = _MergeRequestRecord(
            iid=record.next_iid,
            request=request,
            state=MRState.OPENED,
            created_at=now,
            updated_at=now,
        )
        record.merge_requests[mr.iid] = mr
        record.next_iid += 1
        return self._mr_dto(record, mr)

    async def get_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.get_merge_request."""
        record = self._project(ref.project_id)
        return self._mr_dto(record, self._mr(record, ref.iid))

    async def list_merge_requests(
        self,
        project_id: int,
        *,
        state: MRState | None = MRState.OPENED,
        labels: Sequence[str] = (),
        limit: int = 100,
    ) -> list[MergeRequest]:
        """See GitLabPort.list_merge_requests."""
        record = self._project(project_id)
        matching = [
            mr
            for mr in record.merge_requests.values()
            if (state is None or mr.state is state) and set(labels) <= set(mr.request.labels)
        ]
        matching.sort(key=lambda mr: (mr.created_at, mr.iid), reverse=True)
        return [self._mr_dto(record, mr) for mr in matching[:limit]]

    async def merge_request_diff(self, ref: MergeRequestRef) -> list[FileDiff]:
        """See GitLabPort.merge_request_diff."""
        record = self._project(ref.project_id)
        mr = self._mr(record, ref.iid)
        if mr.final_diff is not None:
            return list(mr.final_diff)
        return self._open_diff(record, mr)

    def _open_diff(self, record: _ProjectRecord, mr: _MergeRequestRecord) -> list[FileDiff]:
        source = self._branch_head(record, mr.request.source_branch)
        target = self._branch_head(record, mr.request.target_branch)
        return _diff(self._merge_base(record, target, source).files, source.files)

    async def approve_merge_request(self, ref: MergeRequestRef) -> None:
        """See GitLabPort.approve_merge_request."""
        record = self._project(ref.project_id)
        mr = self._mr(record, ref.iid)
        if mr.state is not MRState.OPENED:
            raise NotMergeableError(f"merge request !{ref.iid} is {mr.state}")
        mr.approvals.add(self._username)

    async def merge_merge_request(
        self, ref: MergeRequestRef, *, sha: str | None = None
    ) -> MergeRequest:
        """See GitLabPort.merge_merge_request."""
        record = self._project(ref.project_id)
        mr = self._mr(record, ref.iid)
        if mr.state is not MRState.OPENED:
            raise NotMergeableError(f"merge request !{ref.iid} is {mr.state}")
        source = self._branch_head(record, mr.request.source_branch)
        if sha is not None and sha != source.id:
            raise RevisionConflictError(f"source branch moved: expected {sha}, is {source.id}")
        target = self._branch_head(record, mr.request.target_branch)
        merged = self._three_way(record, target, source)
        if merged is None:
            raise NotMergeableError(f"merge request !{ref.iid} has conflicts")
        mr.final_diff = self._open_diff(record, mr)
        commit = self._new_commit(
            record,
            parents=(target.id, source.id),
            files=merged,
            origins=(target, source),
            message=f"Merge branch '{mr.request.source_branch}' into '{mr.request.target_branch}'",
        )
        record.branches[mr.request.target_branch] = commit.id
        now = self._clock()
        mr.state, mr.merged_at, mr.updated_at = MRState.MERGED, now, now
        if mr.request.remove_source_branch:
            del record.branches[mr.request.source_branch]
        return self._mr_dto(record, mr, sha=source.id)

    async def close_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.close_merge_request."""
        record = self._project(ref.project_id)
        mr = self._mr(record, ref.iid)
        if mr.state is not MRState.OPENED:
            raise NotMergeableError(f"merge request !{ref.iid} is {mr.state}")
        mr.final_diff = self._open_diff(record, mr)
        mr.state, mr.updated_at = MRState.CLOSED, self._clock()
        return self._mr_dto(record, mr)

    async def comment_on_merge_request(self, ref: MergeRequestRef, body: str) -> None:
        """See GitLabPort.comment_on_merge_request."""
        mr = self._mr(self._project(ref.project_id), ref.iid)
        if not body.strip():
            raise InvalidRequestError("a comment needs a body")
        mr.notes.append(body)

    # ── Internals ───────────────────────────────────────────────────────────

    def _project(self, project_id: int) -> _ProjectRecord:
        if project_id not in self._projects:
            raise NotFoundError(f"project {project_id} not found")
        return self._projects[project_id]

    def _resolve(self, record: _ProjectRecord, ref: str) -> _CommitRecord:
        if ref in record.branches:
            return record.commits[record.branches[ref]]
        return self._commit_by_sha(record, ref)

    def _file_commits_at(self, record: _ProjectRecord) -> Callable[[str], Mapping[str, str] | None]:
        """Each file's last change as of a commit; ``None`` for a commit GitLab cannot find."""

        def at(sha: str) -> Mapping[str, str] | None:
            try:
                return self._commit_by_sha(record, sha).file_commits
            except NotFoundError:
                return None

        return at

    def _commit_by_sha(self, record: _ProjectRecord, sha: str) -> _CommitRecord:
        if len(sha) >= 7:
            matches = [c for cid, c in record.commits.items() if cid.startswith(sha)]
            if len(matches) == 1:
                return matches[0]
        raise NotFoundError(f"ref {sha} not found")

    def _branch_head(self, record: _ProjectRecord, branch: str) -> _CommitRecord:
        if branch not in record.branches:
            raise NotFoundError(f"branch {branch} not found")
        return record.commits[record.branches[branch]]

    def _mr(self, record: _ProjectRecord, iid: int) -> _MergeRequestRecord:
        if iid not in record.merge_requests:
            raise NotFoundError(f"merge request !{iid} not found")
        return record.merge_requests[iid]

    def _new_commit(
        self,
        record: _ProjectRecord,
        *,
        parents: tuple[str, ...],
        files: Mapping[str, str],
        origins: Sequence[_CommitRecord],
        message: str,
        author: CommitAuthor | None = None,
    ) -> _CommitRecord:
        """Record a commit. A file identical to one in ``origins`` keeps that file's last commit."""
        sequence = next(self._sequence)
        commit_id = hashlib.sha1(
            f"fake-commit-{sequence}".encode(), usedforsecurity=False
        ).hexdigest()
        file_commits: dict[str, str] = {}
        for path, content in files.items():
            origin = next((o for o in origins if o.files.get(path) == content), None)
            file_commits[path] = origin.file_commits[path] if origin else commit_id
        commit = _CommitRecord(
            id=commit_id,
            parents=parents,
            files=dict(files),
            file_commits=file_commits,
            title=message.splitlines()[0] if message else "",
            message=message,
            authored_at=self._clock(),
            sequence=sequence,
            author=author,
        )
        record.commits[commit_id] = commit
        return commit

    def _commit_dto(self, record: _ProjectRecord, commit: _CommitRecord) -> Commit:
        return Commit(
            id=commit.id,
            short_id=commit.id[:8],
            title=commit.title,
            message=commit.message,
            author_name=commit.author.name if commit.author else self._username,
            author_email=commit.author.email if commit.author else self._email,
            authored_at=commit.authored_at,
            web_url=f"{record.project.web_url}/-/commit/{commit.id}",
            parent_ids=commit.parents,
        )

    def _mr_dto(
        self, record: _ProjectRecord, mr: _MergeRequestRecord, *, sha: str | None = None
    ) -> MergeRequest:
        request = mr.request
        has_conflicts = False
        if mr.state is MRState.OPENED:
            source = self._branch_head(record, request.source_branch)
            target = self._branch_head(record, request.target_branch)
            has_conflicts = self._three_way(record, target, source) is None
            sha = source.id
        return MergeRequest(
            ref=MergeRequestRef(record.project.id, mr.iid),
            title=request.title,
            description=request.description,
            state=mr.state,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            author_username=self._username,
            labels=tuple(sorted(request.labels)),
            web_url=f"{record.project.web_url}/-/merge_requests/{mr.iid}",
            created_at=mr.created_at,
            updated_at=mr.updated_at,
            merged_at=mr.merged_at,
            sha=sha or "",
            has_conflicts=has_conflicts,
        )

    def _ancestors(self, record: _ProjectRecord, commit_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [commit_id]
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(record.commits[current].parents)
        return seen

    def _merge_base(
        self, record: _ProjectRecord, target: _CommitRecord, source: _CommitRecord
    ) -> _CommitRecord:
        common = self._ancestors(record, target.id) & self._ancestors(record, source.id)
        return max((record.commits[c] for c in common), key=lambda c: c.sequence)

    def _three_way(
        self, record: _ProjectRecord, target: _CommitRecord, source: _CommitRecord
    ) -> dict[str, str] | None:
        """Apply what ``source`` changed since the merge base onto ``target``; None on conflict."""
        base = self._merge_base(record, target, source).files
        merged = dict(target.files)
        for path in set(base) | set(source.files):
            ours, theirs, ancestor = target.files.get(path), source.files.get(path), base.get(path)
            if theirs == ancestor:
                continue
            if ours != ancestor and ours != theirs:
                return None
            if theirs is None:
                merged.pop(path, None)
            else:
                merged[path] = theirs
        return merged

    def _touches(self, record: _ProjectRecord, commit: _CommitRecord, path: RepoPath) -> bool:
        """Whether ``git log -- <path>`` lists ``commit``.

        Git's default history simplification skips a merge whose ``path`` is
        identical to any one parent's, so after an MR merges, a file's history
        starts with the branch commit that changed it, not the merge commit,
        and agrees with the file's ``last_commit_id``.
        """
        parents = [record.commits[p].files for p in commit.parents] or [{}]
        return all(_changed_within(parent, commit.files, path) for parent in parents)


def _changed_within(before: Mapping[str, str], after: Mapping[str, str], path: RepoPath) -> bool:
    """Whether any file at or under ``path`` differs between two trees."""
    return any(
        before.get(p) != after.get(p) and RepoPath(p).is_within(path)
        for p in set(before) | set(after)
    )


def _changed_since(
    key: str, file_commits: Mapping[str, str], then: Mapping[str, str] | None
) -> bool:
    """GitLab's ``last_commit_id`` check (``Files::BaseService#file_has_changed?``).

    The file's last change on the branch must be its last change as of the
    commit the caller names. So any commit the file was read at works as the
    guard, not only the file's own last commit. A commit GitLab cannot find,
    or one without the file, passes.
    """
    if then is None or key not in then:
        return False
    return file_commits.get(key) != then[key]


def _apply(
    files: dict[str, str],
    file_commits: Mapping[str, str],
    change: FileChange,
    file_commits_at: Callable[[str], Mapping[str, str] | None],
) -> None:
    """Apply one change in place, with GitLab's failure modes."""
    key = str(change.path)
    if change.kind is ChangeKind.CREATE:
        if key in files:
            raise AlreadyExistsError(f"a file with this name already exists: {key}")
        files[key] = change.content or ""
        return
    if change.kind is ChangeKind.MOVE:
        old = str(change.previous_path)
        if old not in files:
            raise NotFoundError(f"a file with this name doesn't exist: {old}")
        if key in files:
            raise AlreadyExistsError(f"a file with this name already exists: {key}")
        content = files.pop(old)
        files[key] = content if change.content is None else change.content
        return
    if key not in files:
        raise NotFoundError(f"a file with this name doesn't exist: {key}")
    if change.last_commit_id is not None and _changed_since(
        key, file_commits, file_commits_at(change.last_commit_id)
    ):
        raise RevisionConflictError(f"{key} has changed since {change.last_commit_id[:8]}")
    if change.kind is ChangeKind.DELETE:
        del files[key]
    else:
        files[key] = change.content or ""


def _diff(old: Mapping[str, str], new: Mapping[str, str]) -> list[FileDiff]:
    """Per-file unified diffs between two trees, sorted by path; renames are not detected."""
    diffs: list[FileDiff] = []
    for path in sorted(set(old) | set(new)):
        before, after = old.get(path), new.get(path)
        if before == after:
            continue
        lines = difflib.unified_diff(
            (before or "").splitlines(keepends=True), (after or "").splitlines(keepends=True), n=3
        )
        body = "".join(itertools.islice(lines, 2, None))
        repo_path = RepoPath(path)
        diffs.append(
            FileDiff(
                old_path=repo_path,
                new_path=repo_path,
                new_file=before is None,
                deleted_file=after is None,
                renamed_file=False,
                diff=body,
            )
        )
    return diffs
