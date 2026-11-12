"""GitLabHttpAdapter: GitLabPort over GitLab's REST API v4, on httpx.AsyncClient.

Why httpx and not python-gitlab (ADR-0002): python-gitlab is synchronous, so
the old client wrapped every call in a thread, had no timeout, and any call a
developer forgot to wrap blocked the event loop (health checks timed out).
This adapter is natively async, has a timeout on every request, and returns
domain types instead of dicts.

Retry policy (ADR-0006): a read is retried on 429, 502, 503, 504 and on
transport errors, with backoff. A write is never retried: a commit or a merge
that timed out may have happened, so the adapter raises AmbiguousWriteError
and the caller re-reads.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import re
import tarfile
import zlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final
from urllib.parse import quote

import httpx

from wingman_core.domain.errors import (
    AlreadyExistsError,
    AmbiguousWriteError,
    GitError,
    GitUnavailableError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    PermissionDeniedError,
    RevisionConflictError,
)
from wingman_core.domain.git import (
    AccessLevel,
    Branch,
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

Sleep = Callable[[float], Awaitable[None]]

_PAGE_SIZE: Final = 100
_RETRYABLE_STATUS: Final = frozenset({429, 502, 503, 504})
_MERGE_CHECKING: Final = frozenset({"checking", "unchecked", "preparing", "approvals_syncing"})
_MAX_RETRY_AFTER_SECONDS: Final = 10.0
_MOVED_PROJECT: Final = re.compile(r"/api/v4/projects/([0-9]+)$")

JSON = Any
"""A decoded GitLab JSON value; narrowed by the parsers below."""


class GitLabHttpAdapter:
    """A GitLabPort for one GitLab instance and one access token."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        sleep: Sleep = asyncio.sleep,
        read_attempts: int = 3,
        backoff_seconds: float = 0.25,
        merge_wait_attempts: int = 20,
    ) -> None:
        """Wrap a client whose ``base_url`` is ``<gitlab>/api/v4`` and that sends the token.

        Build the client with :func:`wingman_core.infrastructure.gitlab.http.build_client`.
        """
        if read_attempts < 1:
            raise ValueError("read_attempts must be at least 1")
        self._client = client
        self._sleep = sleep
        self._read_attempts = read_attempts
        self._backoff = backoff_seconds
        self._merge_wait_attempts = merge_wait_attempts
        self._account_id: int | None = None

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── Projects and files ──────────────────────────────────────────────────

    async def get_project(self, project: int | str) -> Project:
        """See GitLabPort.get_project.

        GitLab answers a renamed or moved project's old path with a 301 to
        ``/api/v4/projects/<id>``; that one redirect is followed. Others are not:
        GitLab's redirect for a file read through an old path appends the
        extension again (``values.yaml.yaml``) and so leads to a wrong 404, and
        every other read here takes the project id.
        """
        response = await self._read("GET", f"/projects/{_id(project)}", {}, follow_moved=True)
        return _project(response.json())

    async def list_group_projects(self, group: str) -> list[Project]:
        """See GitLabPort.list_group_projects."""
        raw = await self._get_pages(
            f"/groups/{_id(group)}/projects",
            {"include_subgroups": "false", "order_by": "path", "sort": "asc", "archived": "false"},
        )
        return sorted((_project(p) for p in raw), key=lambda p: p.path_with_namespace)

    async def access_level(self, project_id: int) -> AccessLevel:
        """See GitLabPort.access_level: ``GET /projects/:id``, plus its group shares.

        ``permissions.project_access`` is a direct project membership;
        ``permissions.group_access`` the highest membership in the project's
        group or a group above it. Either is ``null`` when the account has
        none, and neither counts a share. Each of ``shared_with_groups`` that
        could raise the level is read as the account's own role in that group
        (``GET /groups/:id/members/all/:user_id``, inherited roles included),
        capped by the share's ``group_access_level``.
        """
        raw = await self._get(f"/projects/{project_id}")
        permissions = raw.get("permissions") or {}
        level = max(
            AccessLevel.of((permissions.get(key) or {}).get("access_level"))
            for key in ("project_access", "group_access")
        )
        shares = sorted(
            (
                (AccessLevel.of(share.get("group_access_level")), int(share["group_id"]))
                for share in raw.get("shared_with_groups") or []
            ),
            reverse=True,
        )
        for cap, group_id in shares:
            if cap <= level:
                break
            level = max(level, min(cap, await self._group_role(group_id)))
        return level

    async def _group_role(self, group_id: int) -> AccessLevel:
        """This account's role in a group, inherited ones included; NONE without one."""
        try:
            raw = await self._get(f"/groups/{group_id}/members/all/{await self._user_id()}")
        except NotFoundError:
            return AccessLevel.NONE
        return AccessLevel.of(raw.get("access_level"))

    async def _user_id(self) -> int:
        """The token's user (``GET /user``), read once: a token's user never changes."""
        if self._account_id is None:
            self._account_id = int((await self._get("/user"))["id"])
        return self._account_id

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        """See GitLabPort.read_file."""
        if path.is_root:
            raise InvalidRequestError("read_file needs a file path, not the repository root")
        raw = await self._get(
            f"/projects/{project_id}/repository/files/{quote(str(path), safe='')}", {"ref": ref}
        )
        try:
            content = base64.b64decode(raw["content"], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise InvalidRequestError(f"{path} at {ref} is not UTF-8 text") from exc
        return FileContent(
            path=path, ref=ref, content=content, last_commit_id=raw["last_commit_id"]
        )

    async def list_tree(
        self, project_id: int, path: RepoPath, ref: str, *, recursive: bool = False
    ) -> list[TreeEntry]:
        """See GitLabPort.list_tree."""
        params = {"ref": ref, "recursive": "true" if recursive else "false"}
        if not path.is_root:
            params["path"] = str(path)
        raw = await self._get_pages(f"/projects/{project_id}/repository/tree", params)
        if not raw and not path.is_root:
            # GitLab answers 200 [] for a path that does not exist; the port says NotFound.
            raise NotFoundError(f"tree {path} not found at {ref}")
        entries = [
            TreeEntry(RepoPath(e["path"]), EntryKind(e["type"]))
            for e in raw
            if e["type"] in ("blob", "tree")
        ]
        return sorted(entries, key=lambda e: e.path)

    # ── Branches and commits ────────────────────────────────────────────────

    async def list_branches(self, project_id: int) -> list[Branch]:
        """See GitLabPort.list_branches."""
        raw = await self._get_pages(f"/projects/{project_id}/repository/branches", {})
        return sorted((Branch(b["name"], b["commit"]["id"]) for b in raw), key=lambda b: b.name)

    async def get_branch(self, project_id: int, name: str) -> Branch:
        """See GitLabPort.get_branch."""
        raw = await self._get(f"/projects/{project_id}/repository/branches/{quote(name, safe='')}")
        return Branch(raw["name"], raw["commit"]["id"])

    async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
        """See GitLabPort.read_archive: ``/repository/archive.tar.gz?sha=``, read in memory."""
        response = await self._read(
            "GET",
            f"/projects/{project_id}/repository/archive.tar.gz",
            {"sha": sha},
            headers={"Accept": "application/gzip"},
        )
        if len(response.content) > max_bytes:
            raise InvalidRequestError(f"the archive of {sha[:8]} is larger than {max_bytes} bytes")
        return _archive(response.content, sha, max_bytes=max_bytes)

    async def create_branch(self, project_id: int, name: str, ref: str) -> Branch:
        """See GitLabPort.create_branch."""
        raw = await self._write(
            "POST", f"/projects/{project_id}/repository/branches", {"branch": name, "ref": ref}
        )
        return Branch(raw["name"], raw["commit"]["id"])

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
        if not changes:
            raise InvalidRequestError("a commit needs at least one change")
        body: dict[str, JSON] = {
            "branch": branch,
            "commit_message": message,
            "actions": [_action(change) for change in changes],
        }
        if start_branch is not None:
            body["start_branch"] = start_branch
        if author is not None:
            body["author_name"] = author.name
            body["author_email"] = author.email
        return _commit(
            await self._write("POST", f"/projects/{project_id}/repository/commits", body)
        )

    async def list_commits(
        self, project_id: int, *, ref: str, path: RepoPath | None = None, limit: int = 50
    ) -> list[Commit]:
        """See GitLabPort.list_commits."""
        params = {"ref_name": ref}
        if path is not None and not path.is_root:
            params["path"] = str(path)
        raw = await self._get_pages(
            f"/projects/{project_id}/repository/commits", params, limit=limit
        )
        return [_commit(c) for c in raw]

    async def get_commit(self, project_id: int, sha: str) -> Commit:
        """See GitLabPort.get_commit."""
        return _commit(
            await self._get(f"/projects/{project_id}/repository/commits/{quote(sha, safe='')}")
        )

    async def commit_diff(self, project_id: int, sha: str) -> list[FileDiff]:
        """See GitLabPort.commit_diff."""
        raw = await self._get_pages(
            f"/projects/{project_id}/repository/commits/{quote(sha, safe='')}/diff", {}
        )
        return sorted((_file_diff(d) for d in raw), key=lambda d: d.new_path)

    # ── Merge requests ──────────────────────────────────────────────────────

    async def create_merge_request(self, project_id: int, request: NewMergeRequest) -> MergeRequest:
        """See GitLabPort.create_merge_request."""
        body = {
            "source_branch": request.source_branch,
            "target_branch": request.target_branch,
            "title": request.title,
            "description": request.description,
            "labels": ",".join(request.labels),
            "remove_source_branch": request.remove_source_branch,
        }
        return _merge_request(
            await self._write("POST", f"/projects/{project_id}/merge_requests", body)
        )

    async def get_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.get_merge_request."""
        return _merge_request(await self._get(_mr_path(ref)))

    async def list_merge_requests(
        self,
        project_id: int,
        *,
        state: MRState | None = MRState.OPENED,
        labels: Sequence[str] = (),
        limit: int = 100,
    ) -> list[MergeRequest]:
        """See GitLabPort.list_merge_requests."""
        params = {
            "state": "all" if state is None else str(state),
            "order_by": "created_at",
            "sort": "desc",
        }
        if labels:
            params["labels"] = ",".join(labels)
        raw = await self._get_pages(f"/projects/{project_id}/merge_requests", params, limit=limit)
        return [_merge_request(m) for m in raw]

    async def merge_request_diff(self, ref: MergeRequestRef) -> list[FileDiff]:
        """See GitLabPort.merge_request_diff.

        GitLab computes an MR's stored diff in a background job, so right
        after an MR opens (or its branch moves) ``/diffs`` is empty or stale.
        For an open MR this compares target...source instead, which is
        synchronous and current. A merged or closed MR may have lost its
        source branch, so it uses the stored diff.
        """
        mr = await self._get(_mr_path(ref))
        if mr["state"] == MRState.OPENED:
            compare = await self._get(
                f"/projects/{ref.project_id}/repository/compare",
                {"from": mr["target_branch"], "to": mr["source_branch"], "straight": "false"},
            )
            raw = compare["diffs"]
        else:
            raw = await self._get_pages(f"{_mr_path(ref)}/diffs", {})
        return sorted((_file_diff(d) for d in raw), key=lambda d: d.new_path)

    async def approve_merge_request(self, ref: MergeRequestRef) -> None:
        """See GitLabPort.approve_merge_request."""
        await self._write("POST", f"{_mr_path(ref)}/approve", {})

    async def merge_merge_request(
        self, ref: MergeRequestRef, *, sha: str | None = None
    ) -> MergeRequest:
        """See GitLabPort.merge_merge_request.

        GitLab checks mergeability in the background after an MR opens or its
        branch moves; until it finishes, a merge is refused with 405 even for a
        clean MR. This waits (bounded) for the check before merging, so
        "approve and merge" right after "open" works.

        GitLab also updates an MR's ``sha`` in the background after a push to
        its branch, so the MR may report an older head than the branch has.
        With ``sha``, the branch head itself is compared first: a different
        head means the branch moved since review, ``RevisionConflictError``
        at once (even while the MR still reports the reviewed one). A matching
        head while the MR lags is GitLab catching up: wait for it.
        """
        for attempt in range(self._merge_wait_attempts):
            current = await self._get(_mr_path(ref))
            waiting = current.get("detailed_merge_status") in _MERGE_CHECKING
            if sha is not None and current.get("state") == MRState.OPENED:
                branch = quote(current["source_branch"], safe="")
                head = await self._get(f"/projects/{ref.project_id}/repository/branches/{branch}")
                if head["commit"]["id"] != sha:
                    raise RevisionConflictError(
                        f"merge request {ref}: source branch is at {head['commit']['id'][:8]}, "
                        f"not the reviewed {sha[:8]}"
                    )
                waiting = waiting or current.get("sha") != sha
            if not waiting:
                break
            await self._sleep(min(self._backoff * 2**attempt, 2.0))
        body: dict[str, JSON] = {}
        if sha is not None:
            body["sha"] = sha
        return _merge_request(
            await self._write("PUT", f"{_mr_path(ref)}/merge", body, merging=True)
        )

    async def close_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.close_merge_request."""
        current = await self.get_merge_request(ref)
        if current.state is not MRState.OPENED:
            raise NotMergeableError(f"merge request {ref} is {current.state}")
        return _merge_request(await self._write("PUT", _mr_path(ref), {"state_event": "close"}))

    # ── HTTP ────────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: Mapping[str, str] | None = None) -> JSON:
        response = await self._read("GET", path, params or {})
        return response.json()

    async def _get_pages(
        self, path: str, params: Mapping[str, str], *, limit: int | None = None
    ) -> list[JSON]:
        """Follow GitLab's offset pagination (``X-Next-Page``) up to ``limit`` items."""
        items: list[JSON] = []
        page = "1"
        while page:
            response = await self._read(
                "GET", path, {**params, "per_page": str(_PAGE_SIZE), "page": page}
            )
            items.extend(response.json())
            if limit is not None and len(items) >= limit:
                return items[:limit]
            page = response.headers.get("x-next-page", "")
        return items

    async def _read(
        self,
        method: str,
        path: str,
        params: Mapping[str, str],
        *,
        follow_moved: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Send a read, retrying transient failures.

        With ``follow_moved``, a 301 for a renamed or moved project is followed
        once (see :meth:`get_project`).
        """
        for attempt in range(1, self._read_attempts + 1):
            last = attempt == self._read_attempts
            try:
                response = await self._client.request(method, path, params=params, headers=headers)
                moved = _moved_project(response) if follow_moved else None
                if moved is not None:
                    response = await self._client.request(method, moved)
            except httpx.TransportError as exc:
                if last:
                    raise GitUnavailableError(
                        f"GitLab unreachable on {method} {path}: {type(exc).__name__}"
                    ) from exc
                await self._sleep(self._backoff * 2 ** (attempt - 1))
                continue
            if response.status_code in _RETRYABLE_STATUS and not last:
                await self._sleep(_retry_delay(response, self._backoff * 2 ** (attempt - 1)))
                continue
            if response.is_success:
                return response
            raise _error(response, writing=False)
        raise AssertionError(
            "unreachable: the last attempt always returns or raises"
        )  # pragma: no cover

    async def _write(
        self, method: str, path: str, body: Mapping[str, JSON], *, merging: bool = False
    ) -> JSON:
        """Send a write exactly once (ADR-0006)."""
        try:
            response = await self._client.request(method, path, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise GitUnavailableError(
                f"GitLab unreachable on {method} {path}: {type(exc).__name__}"
            ) from exc
        except httpx.TransportError as exc:
            raise AmbiguousWriteError(
                f"{method} {path} failed after it was sent ({type(exc).__name__}); "
                "re-read before retrying"
            ) from exc
        if response.is_success:
            return response.json()
        raise _error(response, writing=True, merging=merging)


# ── Mapping GitLab responses to domain types ─────────────────────────────────


def _id(project: int | str) -> str:
    return str(project) if isinstance(project, int) else quote(project.strip("/"), safe="")


def _mr_path(ref: MergeRequestRef) -> str:
    return f"/projects/{ref.project_id}/merge_requests/{ref.iid}"


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _project(raw: JSON) -> Project:
    return Project(
        id=raw["id"],
        path_with_namespace=raw["path_with_namespace"],
        default_branch=raw.get("default_branch") or "main",
        web_url=raw["web_url"],
    )


def _commit(raw: JSON) -> Commit:
    authored_at = _time(raw.get("authored_date") or raw.get("created_at"))
    if authored_at is None:
        raise InvalidRequestError(f"commit {raw.get('id')} has no date")
    return Commit(
        id=raw["id"],
        short_id=raw["short_id"],
        title=raw["title"],
        message=raw["message"],
        author_name=raw["author_name"],
        author_email=raw["author_email"],
        authored_at=authored_at,
        web_url=raw["web_url"],
        parent_ids=tuple(raw.get("parent_ids") or ()),
    )


def _file_diff(raw: JSON) -> FileDiff:
    return FileDiff(
        old_path=RepoPath(raw["old_path"]),
        new_path=RepoPath(raw["new_path"]),
        new_file=raw["new_file"],
        deleted_file=raw["deleted_file"],
        renamed_file=raw["renamed_file"],
        diff=raw["diff"],
    )


def _merge_request(raw: JSON) -> MergeRequest:
    created_at = _time(raw["created_at"])
    updated_at = _time(raw["updated_at"])
    if created_at is None or updated_at is None:
        raise InvalidRequestError(f"merge request {raw.get('iid')} has no timestamps")
    return MergeRequest(
        ref=MergeRequestRef(raw["project_id"], raw["iid"]),
        title=raw["title"],
        description=raw.get("description") or "",
        state=MRState(raw["state"]),
        source_branch=raw["source_branch"],
        target_branch=raw["target_branch"],
        author_username=raw["author"]["username"],
        labels=tuple(sorted(raw.get("labels") or ())),
        web_url=raw["web_url"],
        created_at=created_at,
        updated_at=updated_at,
        merged_at=_time(raw.get("merged_at")),
        sha=raw.get("sha") or "",
        has_conflicts=bool(raw.get("has_conflicts")),
    )


def _action(change: FileChange) -> dict[str, JSON]:
    action: dict[str, JSON] = {"action": str(change.kind), "file_path": str(change.path)}
    if change.content is not None:
        action["content"] = change.content
        action["encoding"] = "text"
    if change.previous_path is not None:
        action["previous_path"] = str(change.previous_path)
    if change.last_commit_id is not None:
        action["last_commit_id"] = change.last_commit_id
    return action


# ── Mapping GitLab errors to domain errors ───────────────────────────────────


def _message(response: httpx.Response) -> str:
    """GitLab's error text; its ``message`` may be a string, a list or a dict."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    raw = body.get("message", body.get("error", body)) if isinstance(body, dict) else body
    if isinstance(raw, dict):
        return "; ".join(f"{k}: {v}" for k, v in raw.items())
    if isinstance(raw, list):
        return "; ".join(str(item) for item in raw)
    return str(raw)


def _retry_delay(response: httpx.Response, default: float) -> float:
    try:
        return min(float(response.headers.get("retry-after", default)), _MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return default


def _archive(data: bytes, sha: str, *, max_bytes: int) -> RepoArchive:
    """The files of a GitLab ``archive.tar.gz``, without its top folder (``<project>-<sha>/``).

    Nothing touches the disk. Directories and anything that is not a file or a
    symlink are skipped, and reading stops once the files pass ``max_bytes``.
    """
    files: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar:
                path = member.name.partition("/")[2]
                if not path:
                    continue
                if member.issym():
                    files[path] = member.linkname.encode()
                elif member.isfile():
                    total += member.size
                    if total > max_bytes:
                        raise InvalidRequestError(
                            f"the archive of {sha[:8]} is larger than {max_bytes} bytes"
                        )
                    extracted = tar.extractfile(member)
                    files[path] = extracted.read() if extracted is not None else b""
    except (tarfile.TarError, OSError, EOFError, zlib.error) as exc:
        raise InvalidRequestError(f"the archive of {sha[:8]} is not a readable tar.gz") from exc
    return RepoArchive(sha, files)


def _moved_project(response: httpx.Response) -> str | None:
    """``/projects/<id>`` when a 301 answers for a renamed or moved project, else ``None``.

    Only the id is taken from the ``Location``; the request goes to this
    client's own GitLab, so the token never travels to a host a response names
    (behind a proxy GitLab may also name its external URL there).
    """
    if response.status_code != 301:
        return None
    found = _MOVED_PROJECT.search(httpx.URL(response.headers.get("location", "")).path)
    return f"/projects/{found[1]}" if found else None


def _error(response: httpx.Response, *, writing: bool, merging: bool = False) -> GitError:
    status = response.status_code
    if response.is_redirect:
        where = f"{response.request.method} {response.request.url.path}: {status}"
        return InvalidRequestError(
            f"{where} to {response.headers.get('location', '?')}: GitLab moved this project "
            "or group (renamed or transferred); point the setting or repourl at its new path"
        )
    message = _message(response)
    text = message.lower()
    where = f"{response.request.method} {response.request.url.path}: {status} {message}"
    if status == 404:
        return NotFoundError(where)
    if status in (401, 403):
        return PermissionDeniedError(where)
    if merging and status in (405, 406, 422):
        return NotMergeableError(where)
    if status == 409:
        if "already exists" in text:
            return AlreadyExistsError(where)
        return RevisionConflictError(where)
    if status == 400:
        if "already exists" in text:
            return AlreadyExistsError(where)
        if "changed since" in text or "has been updated" in text:
            return RevisionConflictError(where)
        if "doesn't exist" in text or "does not exist" in text or "on a branch" in text:
            return NotFoundError(where)
        return InvalidRequestError(where)
    if status >= 500 or status == 429:
        return AmbiguousWriteError(where) if writing else GitUnavailableError(where)
    return InvalidRequestError(where)
