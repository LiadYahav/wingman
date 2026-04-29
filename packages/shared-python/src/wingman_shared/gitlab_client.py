"""GitLab API wrapper for Wingman.

Wraps python-gitlab for all repository operations needed by the platform:
- File CRUD (read, create, update, delete)
- Atomic multi-file commits
- Merge request lifecycle (create, approve, merge, reject, diff)
- Repository tree scanning (recursive directory listing)
- Branch listing (for addon version management)

IMPORTANT CONVENTIONS:
- Never constructs file paths — always receives resolved paths from PathResolver
- All writes are optimistic-locked via last_commit_id
- Project ID accepts str ("group/subgroup/project") or int (numeric) — python-gitlab
  handles both transparently
- All reads should go through the CacheManager in services, not directly here

ASYNC SUPPORT:
- All methods have async variants prefixed with 'a' (e.g., read_file -> aread_file)
- Async methods use asyncio.to_thread() to run blocking GitLab calls in thread pool
- Use async variants in FastAPI routes to avoid blocking the event loop
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import gitlab
from gitlab.exceptions import GitlabError, GitlabGetError

from .exceptions import AuthError, ConflictError, GitLabError, NotFoundError

logger = logging.getLogger(__name__)


class GitLabClient:
    """Thin wrapper around python-gitlab for Wingman operations."""

    def __init__(
        self,
        gitlab_url: str,
        access_token: str,
        project_id: str | int,
        default_branch: str = "main",
        ssl_verify: bool | str = True,
    ) -> None:
        """
        Args:
            gitlab_url: GitLab instance URL (e.g. "https://gitlab.internal")
            access_token: Personal/project access token
            project_id: Numeric ID or "group/subgroup/project" path
            default_branch: Default target branch for MRs
            ssl_verify: True, False, or path to CA bundle file
        """
        self._gl = gitlab.Gitlab(
            url=gitlab_url,
            private_token=access_token,
            ssl_verify=ssl_verify,
        )
        self._project_id = project_id
        self.default_branch = default_branch
        self._project: Any = None  # lazy-loaded

    @property
    def project(self) -> Any:
        if self._project is None:
            try:
                self._project = self._gl.projects.get(self._project_id)
            except GitlabGetError as exc:
                raise GitLabError(
                    f"Cannot access GitLab project '{self._project_id}': {exc}"
                ) from exc
        return self._project

    @property
    def project_web_url(self) -> str:
        """Get the web URL for the project (e.g. https://gitlab.com/group/project)."""
        return self.project.web_url

    def get_file_web_url(self, file_path: str, ref: str = "main") -> str:
        """Get the web URL to view a file in GitLab."""
        return f"{self.project_web_url}/-/blob/{ref}/{file_path}"

    def get_tree_web_url(self, directory_path: str = "", ref: str = "main") -> str:
        """Get the web URL to view a directory tree in GitLab."""
        if directory_path:
            return f"{self.project_web_url}/-/tree/{ref}/{directory_path}"
        return f"{self.project_web_url}/-/tree/{ref}"

    # ── File operations ────────────────────────────────────────────────────────

    def read_file(self, file_path: str, ref: str = "main") -> tuple[str, str]:
        """Read a file from the repository.

        Returns:
            (content_str, last_commit_id) — commit ID used for optimistic locking.

        Raises:
            NotFoundError: if the file does not exist at the given ref.
            GitLabError: on API errors.
        """
        try:
            f = self.project.files.get(file_path=file_path, ref=ref)
            content = f.decode().decode("utf-8")
            return content, f.last_commit_id
        except GitlabGetError as exc:
            if exc.response_code == 404:
                raise NotFoundError(f"File not found: {file_path}@{ref}") from exc
            raise GitLabError(f"Error reading {file_path}: {exc}") from exc

    def file_exists(self, file_path: str, ref: str = "main") -> bool:
        """Check if a file exists without raising on 404."""
        try:
            self.project.files.get(file_path=file_path, ref=ref)
            return True
        except GitlabGetError:
            return False

    # ── Atomic commits ────────────────────────────────────────────────────────

    def commit_files(
        self,
        branch: str,
        message: str,
        actions: list[dict[str, str]],
        start_branch: str = "main",
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, Any]:
        """Atomically commit one or more file changes to a new branch.

        Actions format (python-gitlab):
            {"action": "create"|"update"|"delete", "file_path": "...", "content": "..."}
            For "update", include "last_commit_id" for optimistic locking.

        Args:
            author_name: Real user's display name (shown in GitLab UI instead of service account)
            author_email: Real user's email — use "{username}@openshift.local" if unknown

        Returns:
            The created commit dict.

        Raises:
            ConflictError: if last_commit_id doesn't match (concurrent modification).
            GitLabError: on other API errors.
        """
        payload: dict[str, Any] = {
            "branch": branch,
            "commit_message": message,
            "start_branch": start_branch,
            "actions": actions,
        }
        # Set the real user as commit author so GitLab UI shows their identity
        if author_name:
            payload["author_name"] = author_name
            payload["author_email"] = author_email or f"{author_name}@openshift.local"

        try:
            commit = self.project.commits.create(payload)
            return commit.attributes
        except GitlabError as exc:
            if exc.response_code == 409:
                raise ConflictError(
                    "Concurrent modification detected. Please reload and retry."
                ) from exc
            if exc.response_code == 403:
                raise GitLabError(
                    f"Permission denied committing to '{self._project_id}'. "
                    f"Check that your GitLab access token has 'api' or 'write_repository' scope. "
                    f"Error: {exc}"
                ) from exc
            raise GitLabError(f"Commit failed on '{self._project_id}': {exc}") from exc

    # ── Repository tree ────────────────────────────────────────────────────────

    def list_tree(
        self,
        path: str = "",
        ref: str = "main",
        recursive: bool = False,
    ) -> list[dict[str, Any]]:
        """List files and directories at a path.

        Returns list of items with keys: id, name, type ("tree"|"blob"), path, mode.

        Raises:
            NotFoundError: if path does not exist.
            GitLabError: on API errors.
        """
        try:
            items = self.project.repository_tree(
                path=path,
                ref=ref,
                recursive=recursive,
                get_all=True,
            )
            return list(items)
        except GitlabGetError as exc:
            if exc.response_code == 404:
                raise NotFoundError(f"Path not found: {path}@{ref}") from exc
            raise GitLabError(f"Tree listing failed for {path}: {exc}") from exc

    def list_directories(self, path: str = "", ref: str = "main") -> list[str]:
        """Return names of sub-directories at path (non-recursive)."""
        try:
            items = self.list_tree(path=path, ref=ref, recursive=False)
            return [item["name"] for item in items if item["type"] == "tree"]
        except NotFoundError:
            return []

    def list_files(self, path: str = "", ref: str = "main") -> list[str]:
        """Return names of files (blobs) at path (non-recursive)."""
        try:
            items = self.list_tree(path=path, ref=ref, recursive=False)
            return [item["name"] for item in items if item["type"] == "blob"]
        except NotFoundError:
            return []

    # ── Branches ──────────────────────────────────────────────────────────────

    def list_branches(self) -> list[str]:
        """Return all branch names (used for addon version listing)."""
        try:
            branches = self.project.branches.list(get_all=True)
            return [b.name for b in branches]
        except GitlabError as exc:
            raise GitLabError(f"Failed to list branches: {exc}") from exc

    def create_branch(self, branch_name: str, ref: str = "main") -> None:
        """Create a new branch from ref."""
        try:
            self.project.branches.create({"branch": branch_name, "ref": ref})
        except GitlabError as exc:
            raise GitLabError(f"Failed to create branch {branch_name}: {exc}") from exc

    # ── Merge requests ────────────────────────────────────────────────────────

    def create_mr(
        self,
        source_branch: str,
        title: str,
        description: str = "",
        target_branch: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a merge request.

        Returns MR attributes dict (includes iid, web_url, author, etc.).
        """
        target = target_branch or self.default_branch
        try:
            mr = self.project.mergerequests.create(
                {
                    "source_branch": source_branch,
                    "target_branch": target,
                    "title": title,
                    "description": description,
                    "labels": labels or ["wingman"],
                    "remove_source_branch": True,
                }
            )
            return mr.attributes
        except GitlabError as exc:
            raise GitLabError(f"Failed to create MR: {exc}") from exc

    def get_mr(self, mr_iid: int) -> dict[str, Any]:
        """Get a merge request by IID (project-scoped ID)."""
        try:
            mr = self.project.mergerequests.get(mr_iid)
            return mr.attributes
        except GitlabGetError as exc:
            if exc.response_code == 404:
                raise NotFoundError(f"MR !{mr_iid} not found") from exc
            raise GitLabError(f"Failed to get MR !{mr_iid}: {exc}") from exc

    def list_open_mrs(self, target_branch: str = "main") -> list[dict[str, Any]]:
        """List all open merge requests targeting the given branch."""
        filters: dict[str, Any] = {"state": "opened", "target_branch": target_branch}
        try:
            mrs = self.project.mergerequests.list(**filters, get_all=True)
            return [mr.attributes for mr in mrs]
        except GitlabError as exc:
            raise GitLabError(f"Failed to list MRs: {exc}") from exc

    def list_mrs(
        self,
        state: str = "all",
        labels: list[str] | None = None,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List merge requests with pagination support."""
        filters: dict[str, Any] = {
            "state": state,
            "labels": labels or ["wingman"],
            "per_page": per_page,
            "page": page,
        }
        try:
            mrs = self.project.mergerequests.list(**filters)
            return [mr.attributes for mr in mrs]
        except GitlabError as exc:
            raise GitLabError(f"Failed to list MRs: {exc}") from exc

    def get_mr_diff(self, mr_iid: int) -> list[dict[str, Any]]:
        """Get file diffs for a merge request.

        Each item has: old_path, new_path, diff (unified diff string), new_file,
        renamed_file, deleted_file.
        """
        try:
            mr = self.project.mergerequests.get(mr_iid)
            changes = mr.changes()
            return changes.get("changes", [])
        except GitlabError as exc:
            raise GitLabError(f"Failed to get MR diff: {exc}") from exc

    def approve_mr(self, mr_iid: int) -> None:
        """Approve a merge request."""
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.approve()
        except GitlabError as exc:
            code = getattr(exc, "response_code", None)
            body = getattr(exc, "response_body", None)
            if code in (401, 403):
                raise AuthError(
                    f"Cannot approve MR !{mr_iid} on '{self._project_id}'. "
                    f"HTTP {code}: {body}. "
                    "Check: (1) token has 'api' scope, (2) Maintainer+ role, "
                    "(3) not approving your own MR, (4) approval rules allow it."
                ) from exc
            raise GitLabError(f"Failed to approve MR !{mr_iid}: {exc}") from exc

    def merge_mr(self, mr_iid: int) -> None:
        """Merge an approved merge request."""
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.merge(should_remove_source_branch=True)
        except GitlabError as exc:
            if getattr(exc, "response_code", None) in (401, 403):
                raise AuthError(
                    f"Cannot merge MR !{mr_iid} on '{self._project_id}'. "
                    "The Wingman service's GitLab access token needs: "
                    "(1) 'api' scope, and (2) Maintainer+ role on this project. "
                    f"GitLab error: {exc}"
                ) from exc
            raise GitLabError(f"Failed to merge MR !{mr_iid}: {exc}") from exc

    def close_mr(self, mr_iid: int) -> None:
        """Close (reject) a merge request without merging."""
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.state_event = "close"
            mr.save()
        except GitlabError as exc:
            raise GitLabError(f"Failed to close MR !{mr_iid}: {exc}") from exc

    # ── Commits / Audit ───────────────────────────────────────────────────────

    def list_commits(
        self,
        ref_name: str = "main",
        path: str | None = None,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List commits, optionally filtered by path.

        Args:
            path: Filter commits that touch files under this path.
        """
        filters: dict[str, Any] = {
            "ref_name": ref_name,
            "per_page": per_page,
            "page": page,
        }
        if path:
            filters["path"] = path
        try:
            commits = self.project.commits.list(**filters)
            return [c.attributes for c in commits]
        except GitlabError as exc:
            raise GitLabError(f"Failed to list commits: {exc}") from exc

    def get_commit_diff(self, sha: str) -> list[dict[str, Any]]:
        """Get file diffs for a specific commit.

        Each item has: old_path, new_path, diff (unified diff string), new_file,
        renamed_file, deleted_file.
        """
        try:
            commit = self.project.commits.get(sha)
            return list(commit.diff())
        except GitlabGetError as exc:
            if exc.response_code == 404:
                raise NotFoundError(f"Commit {sha} not found") from exc
            raise GitLabError(f"Failed to get commit diff: {exc}") from exc
        except GitlabError as exc:
            raise GitLabError(f"Failed to get commit diff: {exc}") from exc

    def get_commit(self, sha: str) -> dict:
        """Return commit metadata (author_name, authored_date, message, etc.)."""
        try:
            commit = self.project.commits.get(sha)
            return commit.attributes
        except GitlabGetError as exc:
            if exc.response_code == 404:
                raise NotFoundError(f"Commit {sha} not found") from exc
            raise GitLabError(f"Failed to get commit: {exc}") from exc
        except GitlabError as exc:
            raise GitLabError(f"Failed to get commit: {exc}") from exc

    # ── Async methods (run blocking calls in thread pool) ─────────────────────

    async def aread_file(self, file_path: str, ref: str = "main") -> tuple[str, str]:
        """Async version of read_file."""
        return await asyncio.to_thread(self.read_file, file_path, ref)

    async def afile_exists(self, file_path: str, ref: str = "main") -> bool:
        """Async version of file_exists."""
        return await asyncio.to_thread(self.file_exists, file_path, ref)

    async def alist_tree(
        self, path: str = "", ref: str = "main", recursive: bool = False
    ) -> list[dict[str, Any]]:
        """Async version of list_tree."""
        return await asyncio.to_thread(self.list_tree, path, ref, recursive)

    async def alist_directories(self, path: str = "", ref: str = "main") -> list[str]:
        """Async version of list_directories."""
        return await asyncio.to_thread(self.list_directories, path, ref)

    async def alist_files(self, path: str = "", ref: str = "main") -> list[str]:
        """Async version of list_files."""
        return await asyncio.to_thread(self.list_files, path, ref)

    async def alist_branches(self) -> list[str]:
        """Async version of list_branches."""
        return await asyncio.to_thread(self.list_branches)

    async def acommit_files(
        self,
        branch: str,
        message: str,
        actions: list[dict[str, str]],
        start_branch: str = "main",
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, Any]:
        """Async version of commit_files."""
        return await asyncio.to_thread(
            self.commit_files, branch, message, actions, start_branch, author_name, author_email
        )

    async def acreate_mr(
        self,
        source_branch: str,
        title: str,
        description: str = "",
        target_branch: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async version of create_mr."""
        return await asyncio.to_thread(
            self.create_mr, source_branch, title, description, target_branch, labels
        )

    async def aget_mr(self, mr_iid: int) -> dict[str, Any]:
        """Async version of get_mr."""
        return await asyncio.to_thread(self.get_mr, mr_iid)

    async def alist_open_mrs(self, target_branch: str = "main") -> list[dict[str, Any]]:
        """Async version of list_open_mrs."""
        return await asyncio.to_thread(self.list_open_mrs, target_branch)

    async def alist_mrs(
        self,
        state: str = "all",
        labels: list[str] | None = None,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Async version of list_mrs."""
        return await asyncio.to_thread(self.list_mrs, state, labels, per_page, page)

    async def aget_mr_diff(self, mr_iid: int) -> list[dict[str, Any]]:
        """Async version of get_mr_diff."""
        return await asyncio.to_thread(self.get_mr_diff, mr_iid)

    async def aapprove_mr(self, mr_iid: int) -> None:
        """Async version of approve_mr."""
        return await asyncio.to_thread(self.approve_mr, mr_iid)

    async def amerge_mr(self, mr_iid: int) -> None:
        """Async version of merge_mr."""
        return await asyncio.to_thread(self.merge_mr, mr_iid)

    async def aclose_mr(self, mr_iid: int) -> None:
        """Async version of close_mr."""
        return await asyncio.to_thread(self.close_mr, mr_iid)

    async def alist_commits(
        self,
        ref_name: str = "main",
        path: str | None = None,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Async version of list_commits."""
        return await asyncio.to_thread(self.list_commits, ref_name, path, per_page, page)

    async def aget_commit_diff(self, sha: str) -> list[dict[str, Any]]:
        """Async version of get_commit_diff."""
        return await asyncio.to_thread(self.get_commit_diff, sha)

    async def aget_commit(self, sha: str) -> dict:
        """Async version of get_commit."""
        return await asyncio.to_thread(self.get_commit, sha)

    async def acommit_to_branch(
        self,
        branch: str,
        message: str,
        actions: list[dict[str, str]],
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, Any]:
        """Async version of commit_to_branch."""
        return await asyncio.to_thread(
            self.commit_to_branch, branch, message, actions, author_name, author_email
        )

    def commit_to_branch(
        self,
        branch: str,
        message: str,
        actions: list[dict[str, str]],
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, Any]:
        """Commit changes to an existing branch (no start_branch — branch must exist).

        Used for pushing updates to an existing MR's source branch.
        """
        payload: dict[str, Any] = {
            "branch": branch,
            "commit_message": message,
            "actions": actions,
        }
        if author_name:
            payload["author_name"] = author_name
            payload["author_email"] = author_email or f"{author_name}@openshift.local"
        try:
            commit = self.project.commits.create(payload)
            return commit.attributes
        except GitlabError as exc:
            raise GitLabError(f"Commit to branch failed: {exc}") from exc


class GitLabGroupClient:
    """Wraps GitLab Groups API to enumerate team projects and create per-team clients.

    In the Wingman day2 architecture, `sigs` is a GitLab subgroup and each team
    inside it is a separate GitLab project.  This client handles the group-level
    view while handing out per-team GitLabClient instances.
    """

    def __init__(
        self,
        gitlab_url: str,
        access_token: str,
        group_path: str,
        default_branch: str = "main",
        ssl_verify: bool | str = True,
    ) -> None:
        self._gl = gitlab.Gitlab(
            url=gitlab_url,
            private_token=access_token,
            ssl_verify=ssl_verify,
        )
        self._group_path = group_path
        self.default_branch = default_branch
        # Stored separately so we can create per-team GitLabClient instances
        self._gitlab_url = gitlab_url
        self._access_token = access_token
        self._ssl_verify = ssl_verify
        self._group: Any = None
        self._team_clients: dict[str, GitLabClient] = {}

    @property
    def group(self) -> Any:
        if self._group is None:
            try:
                self._group = self._gl.groups.get(self._group_path)
            except GitlabGetError as exc:
                raise GitLabError(
                    f"Cannot access GitLab group '{self._group_path}': {exc}"
                ) from exc
        return self._group

    def list_project_paths(self) -> list[str]:
        """Return path names (not full paths) of all projects in this subgroup."""
        try:
            projects = self.group.projects.list(get_all=True)
            return [p.path for p in projects]
        except GitlabError as exc:
            raise GitLabError(
                f"Failed to list group projects in '{self._group_path}': {exc}"
            ) from exc

    async def alist_project_paths(self) -> list[str]:
        """Async version of list_project_paths."""
        return await asyncio.to_thread(self.list_project_paths)

    def get_project_client(self, team: str) -> GitLabClient:
        """Return (or create) a GitLabClient scoped to the given team's project."""
        if team not in self._team_clients:
            self._team_clients[team] = GitLabClient(
                gitlab_url=self._gitlab_url,
                access_token=self._access_token,
                project_id=f"{self._group_path}/{team}",
                default_branch=self.default_branch,
                ssl_verify=self._ssl_verify,
            )
        return self._team_clients[team]
