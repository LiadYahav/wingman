"""Cluster lifecycle service — reads/writes cluster files in the Day1 GitLab repo.

All file paths come from PathResolver. All reads go through CacheManager.
Every write creates a GitLab MR (never a direct commit to main).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import ConflictError, GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import (
    ClusterMetadata,
    ClusterStatus,
    MRDetail,
    UserInfo,
)
from wingman_shared.mr_conventions import (
    make_branch_name,
    make_mr_description,
    make_mr_title,
    parse_mr_to_detail,
)
from wingman_shared.path_resolver import PathResolver

logger = logging.getLogger(__name__)

_NO_SPEC = "(not linked to a cluster spec)"


def _parse_spec_comments(yaml_content: str) -> tuple[str, str]:
    """Extract specName and specVersion from leading # comments in a cluster YAML file.

    Scans lines at the top of the file until the first non-comment line.
    Returns (spec_name, spec_version) — both empty string if not found.
    """
    spec_name = ""
    spec_version = ""
    for line in yaml_content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            break
        if stripped.startswith("# specName:"):
            spec_name = stripped[len("# specName:") :].strip().strip("\"'")
        elif stripped.startswith("# specVersion:"):
            spec_version = stripped[len("# specVersion:") :].strip().strip("\"'")
    return spec_name, spec_version


def _prepend_spec_comments(yaml_content: str, spec_name: str, spec_version: str) -> str:
    """Prepend specName/specVersion comments to a cluster YAML file."""
    return f'# specName: "{spec_name}"\n# specVersion: "{spec_version}"\n{yaml_content}'


class ClusterService:
    """Provides cluster CRUD and drift operations backed by Git."""

    def __init__(
        self,
        gitlab_day1: GitLabClient,
        path_resolver: PathResolver,
        cache: CacheManager,
        default_branch: str = "main",
        cluster_file_suffix: str = ".yaml",
    ) -> None:
        self.gl = gitlab_day1
        self.pr = path_resolver
        self.cache = cache
        self.default_branch = default_branch
        self._cluster_suffix = cluster_file_suffix

    # ── Cluster listing ────────────────────────────────────────────────────────

    async def list_clusters(self) -> list[ClusterStatus]:
        """List all clusters by scanning the day1 repo tree."""

        async def _fetch() -> list[ClusterStatus]:
            return await self._scan_clusters()

        return await self.cache.get_or_fetch(
            "day1:clusters:list",
            _fetch,
            ttl=30.0,
        )

    async def _scan_clusters(self) -> list[ClusterStatus]:
        """Scan tree for all cluster YAML files inside hostedClusters/ directories."""
        try:
            items = await self.gl.alist_tree(path="", ref=self.default_branch, recursive=True)
        except NotFoundError:
            return []
        except GitLabError as exc:
            logger.error("Tree scan failed: %s", exc)
            return []

        # Match: sites/{site}/mces/{mce}/hostedClusters/{cluster}{suffix}
        # Exclude .wingman.yaml metadata files (internal Wingman bookkeeping)
        cluster_files = [
            item
            for item in items
            if item["type"] == "blob"
            and "/hostedClusters/" in item["path"]
            and item["name"].endswith(self._cluster_suffix)
            and not item["name"].endswith(".wingman.yaml")
        ]

        # Fetch all cluster statuses in parallel for better performance
        async def safe_fetch(path: str) -> ClusterStatus | None:
            try:
                return await self._file_to_cluster_status(path)
            except Exception as exc:
                logger.warning("Failed to load cluster from %s: %s", path, exc)
                return None

        results = await asyncio.gather(
            *[safe_fetch(item["path"]) for item in cluster_files],
            return_exceptions=False,  # We handle exceptions in safe_fetch
        )

        return [status for status in results if status is not None]

    async def _file_to_cluster_status(self, cluster_path: str) -> ClusterStatus | None:
        """Parse a cluster YAML file path into a ClusterStatus.

        Path format: sites/{site}/mces/{mce}/hostedClusters/{cluster}.yaml
        Site and MCE are extracted from path segments.
        Wingman metadata (.wingman.yaml) is optional — existing clusters may not have it.
        """
        parts = cluster_path.split("/")
        # Expected: ["sites", site, "mces", mce, "hostedClusters", filename]
        if len(parts) < 6:
            return None

        site = parts[1]
        mce = parts[3]
        cluster_name = parts[-1].removesuffix(self._cluster_suffix)

        metadata = await self._get_cluster_metadata(site=site, mce=mce, cluster=cluster_name)

        return ClusterStatus(
            name=cluster_name,
            site=site,
            mce=mce,
            phase="Unknown",
            spec_name=metadata.spec_name,
            spec_version=metadata.spec_version,
            created_by=metadata.created_by,
            created_at=metadata.created_at,
            is_drifted=False,
        )

    async def _get_cluster_metadata(self, *, site: str, mce: str, cluster: str) -> ClusterMetadata:
        """Derive cluster metadata from the cluster YAML file and .wingman.yaml metadata.

        - specName / specVersion: from .wingman.yaml or leading # comments in cluster YAML
        - created_by / created_at: read from the git commit that last touched the cluster file
        - variables / addonOverrides: from .wingman.yaml if present
        """
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=cluster)
        metadata_path = self.pr.day1_cluster_metadata(site=site, mce=mce, cluster=cluster)

        async def _fetch() -> ClusterMetadata:
            import yaml  # type: ignore[import-untyped]

            created_by = ""
            created_at = None
            spec_name = ""
            spec_version = ""
            variables: dict[str, Any] = {}
            addon_overrides: dict[str, dict[str, Any]] = {}

            # Try reading .wingman.yaml metadata file first
            try:
                meta_content, _ = await self.gl.aread_file(metadata_path, ref=self.default_branch)
                meta_data = yaml.safe_load(meta_content) or {}
                spec_name = meta_data.get("specName", "")
                spec_version = meta_data.get("specVersion", "")
                variables = meta_data.get("variables", {})
                addon_overrides = meta_data.get("addonOverrides", {})
            except NotFoundError:
                pass  # No metadata file, fall back to parsing comments
            except Exception as exc:
                logger.warning("Could not parse metadata file %s: %s", metadata_path, exc)

            # Read cluster file for commit info and fallback spec parsing
            try:
                content, commit_sha = await self.gl.aread_file(cluster_path, ref=self.default_branch)
                if not spec_name:  # Fall back to parsing comments if no .wingman.yaml
                    spec_name, spec_version = _parse_spec_comments(content)
                commit = self.gl.get_commit(commit_sha)
                created_by = commit.get("author_name", "")
                created_at = datetime.fromisoformat(commit["authored_date"])
            except Exception as exc:
                logger.warning("Could not read cluster file info for %s: %s", cluster_path, exc)

            return ClusterMetadata(
                site=site,
                mce=mce,
                spec_name=spec_name or _NO_SPEC,
                spec_version=spec_version,
                created_by=created_by,
                created_at=created_at,
                variables=variables,
                addon_overrides=addon_overrides,
            )

        return await self.cache.get_or_fetch(
            f"day1:clusters:metadata:{site}:{mce}:{cluster}",
            _fetch,
            ttl=30.0,
        )

    # ── Cluster detail ─────────────────────────────────────────────────────────

    async def get_cluster(self, name: str, site: str, mce: str) -> dict[str, Any]:
        """Get full cluster YAML and metadata."""
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=name)

        async def _fetch() -> dict[str, Any]:
            try:
                yaml_content, _ = await self.gl.aread_file(cluster_path, ref=self.default_branch)
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found") from exc

            # Use the shared metadata fetching logic
            metadata = await self._get_cluster_metadata(site=site, mce=mce, cluster=name)

            return {
                "name": name,
                "site": site,
                "mce": mce,
                "yaml": yaml_content,
                "metadata": metadata.model_dump(by_alias=False),
                "gitlab_url": self.gl.get_file_web_url(cluster_path, ref=self.default_branch),
            }

        return await self.cache.get_or_fetch(
            f"day1:clusters:detail:{name}",
            _fetch,
            ttl=30.0,
        )

    # ── Cluster creation ───────────────────────────────────────────────────────

    async def create_cluster(
        self,
        *,
        name: str,
        site: str,
        mce: str,
        rendered_yaml: str,
        spec_name: str,
        spec_version: str,
        variables: dict[str, Any],
        addon_overrides: dict[str, dict[str, Any]] | None = None,
        current_user: UserInfo,
    ) -> MRDetail:
        """Create a new cluster by committing files and opening an MR.

        Args:
            name: Cluster name (used as filename)
            site: Site identifier (path variable)
            mce: MCE identifier (path variable)
            rendered_yaml: Pre-rendered Jinja2 output (multi-doc YAML)
            spec_name: Name of the spec used
            spec_version: Version of the spec used
            variables: Input variables for the metadata file
            addon_overrides: Per-addon field overrides (team/name -> path -> value)
            current_user: The user creating the cluster

        Returns:
            MRDetail for the created merge request.
        """
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=name)
        metadata_path = self.pr.day1_cluster_metadata(site=site, mce=mce, cluster=name)

        # Check for name collision
        if self.gl.file_exists(cluster_path, ref=self.default_branch):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cluster '{name}' already exists",
            )

        # Embed spec metadata as comments at the top of the cluster YAML
        rendered_yaml = _prepend_spec_comments(rendered_yaml, spec_name, spec_version)

        # Build .wingman.yaml metadata file (stored variables and addon overrides)
        import yaml

        metadata_content = yaml.safe_dump(
            {
                "specName": spec_name,
                "specVersion": spec_version,
                "variables": variables,
                "addonOverrides": addon_overrides or {},
            },
            default_flow_style=False,
            allow_unicode=True,
        )

        branch = make_branch_name(current_user.username, "create-cluster", name)
        mr_title = make_mr_title("Day1", "Create", "cluster", name, f"from spec {spec_name}")
        mr_description = make_mr_description(
            f"Creating cluster **{name}** from spec `{spec_name}` v{spec_version}.\n"
            f"Site: `{site}`, MCE: `{mce}`, workers: {variables.get('worker_count', 'default')}.",
            username=current_user.username,
            action="create",
            resource_type="cluster",
            resource_name=name,
            repo="Day1",
        )
        commit_message = (
            f"Create cluster {name} from spec {spec_name} v{spec_version}\n\n"
            f"Site: {site}, MCE: {mce}\n"
            f"Variables: {', '.join(f'{k}={v}' for k, v in variables.items())}"
        )

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[
                    {"action": "create", "file_path": cluster_path, "content": rendered_yaml},
                    {"action": "create", "file_path": metadata_path, "content": metadata_content},
                ],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day1", "create"],
            )
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitLabError as exc:
            logger.error("Failed to create cluster MR: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to create cluster") from exc

        # Write-through cache invalidation
        self.cache.invalidate("day1:clusters:list")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Cluster modification ───────────────────────────────────────────────────

    async def modify_cluster(
        self,
        *,
        name: str,
        site: str,
        mce: str,
        updated_yaml: str,
        change_summary: str,
        current_user: UserInfo,
    ) -> MRDetail:
        """Modify a cluster's YAML and open an MR."""
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=name)

        try:
            _, last_commit_id = await self.gl.aread_file(cluster_path, ref=self.default_branch)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found") from exc

        branch = make_branch_name(current_user.username, "modify-cluster", name)
        mr_title = make_mr_title("Day1", "Modify", "cluster", name)
        mr_description = make_mr_description(
            change_summary,
            username=current_user.username,
            action="modify",
            resource_type="cluster",
            resource_name=name,
            repo="Day1",
        )
        commit_message = f"Modify cluster {name}\n\n{change_summary}"

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[
                    {
                        "action": "update",
                        "file_path": cluster_path,
                        "content": updated_yaml,
                        "last_commit_id": last_commit_id,
                    }
                ],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day1", "modify"],
            )
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to create modify MR") from exc

        self.cache.invalidate("day1:clusters:list")
        self.cache.invalidate(f"day1:clusters:detail:{name}")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Cluster deletion ───────────────────────────────────────────────────────

    async def delete_cluster(
        self,
        *,
        name: str,
        site: str,
        mce: str,
        current_user: UserInfo,
    ) -> MRDetail:
        """Delete a cluster by removing its files via MR."""
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=name)

        try:
            _, cluster_commit_id = await self.gl.aread_file(cluster_path, ref=self.default_branch)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found") from exc

        branch = make_branch_name(current_user.username, "delete-cluster", name)
        mr_title = make_mr_title("Day1", "Delete", "cluster", name)
        mr_description = make_mr_description(
            f"Deleting cluster **{name}** and its associated metadata from site `{site}`, MCE `{mce}`.",
            username=current_user.username,
            action="delete",
            resource_type="cluster",
            resource_name=name,
            repo="Day1",
        )
        commit_message = (
            f"Delete cluster {name}\n\nSite: {site}, MCE: {mce}\n"
            "Removes cluster YAML and wingman metadata."
        )

        actions: list[dict[str, str]] = [
            {"action": "delete", "file_path": cluster_path},
        ]

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=actions,
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day1", "delete"],
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to create delete MR") from exc

        self.cache.invalidate("day1:clusters:list")
        self.cache.invalidate(f"day1:clusters:detail:{name}")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Site/MCE management ────────────────────────────────────────────────────

    async def list_sites(self) -> list[str]:
        """List all sites by scanning the sites/ directory."""

        async def _fetch() -> list[str]:
            try:
                dirs = await self.gl.alist_directories("sites", ref=self.default_branch)
                return sorted(dirs)
            except NotFoundError:
                return []
            except GitLabError as exc:
                logger.warning("Failed to list sites: %s", exc)
                return []

        return await self.cache.get_or_fetch("day1:sites:list", _fetch, ttl=60.0)

    async def list_mces(self, site: str) -> list[str]:
        """List all MCEs for a given site."""

        async def _fetch() -> list[str]:
            try:
                dirs = await self.gl.alist_directories(f"sites/{site}/mces", ref=self.default_branch)
                return sorted(dirs)
            except NotFoundError:
                return []
            except GitLabError as exc:
                logger.warning("Failed to list MCEs for site %s: %s", site, exc)
                return []

        return await self.cache.get_or_fetch(f"day1:sites:{site}:mces", _fetch, ttl=60.0)

    async def create_site(self, site: str, current_user: UserInfo) -> MRDetail:
        """Create a new site folder structure."""
        gitkeep_path = f"sites/{site}/.gitkeep"

        if self.gl.file_exists(f"sites/{site}", ref=self.default_branch):
            raise HTTPException(status_code=409, detail=f"Site '{site}' already exists")

        branch = make_branch_name(current_user.username, "create-site", site)
        mr_title = make_mr_title("Day1", "Create", "site", site)
        mr_description = make_mr_description(
            f"Creating new site **{site}**.",
            username=current_user.username,
            action="create",
            resource_type="site",
            resource_name=site,
            repo="Day1",
        )

        try:
            self.gl.commit_files(
                branch=branch,
                message=f"Create site {site}",
                actions=[{"action": "create", "file_path": gitkeep_path, "content": ""}],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day1", "create", "site"],
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to create site") from exc

        self.cache.invalidate("day1:sites:list")
        return parse_mr_to_detail(mr_raw)

    async def create_mce(self, site: str, mce: str, current_user: UserInfo) -> MRDetail:
        """Create a new MCE folder structure within a site."""
        gitkeep_path = f"sites/{site}/mces/{mce}/hostedClusters/.gitkeep"

        if self.gl.file_exists(f"sites/{site}/mces/{mce}", ref=self.default_branch):
            raise HTTPException(status_code=409, detail=f"MCE '{mce}' already exists in site '{site}'")

        branch = make_branch_name(current_user.username, "create-mce", mce)
        mr_title = make_mr_title("Day1", "Create", "mce", mce, f"in site {site}")
        mr_description = make_mr_description(
            f"Creating new MCE **{mce}** in site **{site}**.",
            username=current_user.username,
            action="create",
            resource_type="mce",
            resource_name=mce,
            repo="Day1",
        )

        try:
            self.gl.commit_files(
                branch=branch,
                message=f"Create MCE {mce} in site {site}",
                actions=[{"action": "create", "file_path": gitkeep_path, "content": ""}],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day1", "create", "mce"],
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to create MCE") from exc

        self.cache.invalidate("day1:sites:list")
        self.cache.invalidate(f"day1:sites:{site}:mces")
        return parse_mr_to_detail(mr_raw)
