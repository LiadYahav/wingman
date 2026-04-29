"""Cluster spec service — CRUD for specs stored in the specs GitLab repo."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import ClusterSpec, MRDetail, UserInfo
from wingman_shared.mr_conventions import (
    make_branch_name,
    make_mr_description,
    make_mr_title,
    parse_mr_to_detail,
)
from wingman_shared.path_resolver import PathResolver
from wingman_shared.yaml_utils import dump_multi_document, parse_multi_document

logger = logging.getLogger(__name__)


class SpecService:
    """CRUD for cluster specs stored in the specs GitLab repo."""

    def __init__(
        self,
        gitlab_specs: GitLabClient,
        path_resolver: PathResolver,
        cache: CacheManager,
        default_branch: str = "main",
    ) -> None:
        self.gl = gitlab_specs
        self.pr = path_resolver
        self.cache = cache
        self.default_branch = default_branch

    # ── Listing ────────────────────────────────────────────────────────────────

    async def list_specs(self) -> list[ClusterSpec]:
        async def _fetch() -> list[ClusterSpec]:
            try:
                files = self.gl.list_files(path=self.pr.specs_root, ref=self.default_branch)
            except NotFoundError:
                return []
            except GitLabError as exc:
                logger.error("Failed to list specs: %s", exc)
                return []

            specs: list[ClusterSpec] = []
            for fname in files:
                if not fname.endswith(".yaml"):
                    continue
                spec_name = fname[:-5]  # strip .yaml
                try:
                    spec = await self._load_spec(spec_name)
                    specs.append(spec)
                except Exception as exc:
                    logger.warning("Failed to load spec %s: %s", spec_name, exc)

            return specs

        return await self.cache.get_or_fetch("specs:list", _fetch, ttl=60.0)

    async def get_spec(self, name: str) -> ClusterSpec:
        try:
            return await self._load_spec(name)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Spec '{name}' not found") from exc

    async def _load_spec(self, name: str) -> ClusterSpec:
        async def _fetch() -> ClusterSpec:
            path = self.pr.spec_file(spec_name=name)
            try:
                content, _ = self.gl.read_file(path, ref=self.default_branch)
                docs = parse_multi_document(content)
                if not docs:
                    raise ValueError(f"Empty spec file: {path}")
                return ClusterSpec.model_validate(docs[0])
            except Exception as exc:
                logger.warning("Failed to load spec %s: %s", name, exc)
                raise

        return await self.cache.get_or_fetch(f"specs:detail:{name}", _fetch, ttl=60.0)

    # ── Create ─────────────────────────────────────────────────────────────────

    async def create_spec(self, spec: ClusterSpec, current_user: UserInfo) -> MRDetail:
        path = self.pr.spec_file(spec_name=spec.metadata.name)

        if self.gl.file_exists(path, ref=self.default_branch):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Spec '{spec.metadata.name}' already exists",
            )

        content = dump_multi_document([spec.model_dump(by_alias=True)])
        branch = make_branch_name(current_user.username, "create-spec", spec.metadata.name)
        mr_title = make_mr_title("Specs", "Create", "spec", spec.metadata.name)
        mr_description = make_mr_description(
            f"Creating cluster spec **{spec.metadata.name}** v{spec.metadata.version}.\n"
            f"Defines {len(spec.spec.day1.variables)} day1 variables and "
            f"{len(spec.spec.day2.addons) if spec.spec.day2 else 0} day2 addons.",
            username=current_user.username,
            action="create",
            resource_type="spec",
            resource_name=spec.metadata.name,
            repo="Specs",
        )
        commit_message = (
            f"Create spec {spec.metadata.name} v{spec.metadata.version}\n\n"
            f"{spec.metadata.description or ''}"
        ).strip()

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[{"action": "create", "file_path": path, "content": content}],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "specs", "create"],
            )
        except GitLabError as exc:
            logger.error("Failed to create spec MR: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to create spec") from exc

        self.cache.invalidate("specs:list")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Update ─────────────────────────────────────────────────────────────────

    async def update_spec(self, name: str, spec: ClusterSpec, current_user: UserInfo) -> MRDetail:
        path = self.pr.spec_file(spec_name=name)

        try:
            _, last_commit_id = self.gl.read_file(path, ref=self.default_branch)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Spec '{name}' not found") from exc

        content = dump_multi_document([spec.model_dump(by_alias=True)])
        branch = make_branch_name(current_user.username, "update-spec", name)
        mr_title = make_mr_title("Specs", "Update", "spec", name, f"to v{spec.metadata.version}")
        mr_description = make_mr_description(
            f"Updating cluster spec **{name}** to v{spec.metadata.version}.",
            username=current_user.username,
            action="update",
            resource_type="spec",
            resource_name=name,
            repo="Specs",
        )
        commit_message = (
            f"Update spec {name} to v{spec.metadata.version}\n\n{spec.metadata.description or ''}"
        ).strip()

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[
                    {
                        "action": "update",
                        "file_path": path,
                        "content": content,
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
                labels=["wingman", "specs", "update"],
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to update spec") from exc

        self.cache.invalidate("specs:list")
        self.cache.invalidate(f"specs:detail:{name}")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Delete ─────────────────────────────────────────────────────────────────

    async def delete_spec(self, name: str, current_user: UserInfo) -> MRDetail:
        path = self.pr.spec_file(spec_name=name)

        try:
            self.gl.read_file(path, ref=self.default_branch)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Spec '{name}' not found") from exc

        branch = make_branch_name(current_user.username, "delete-spec", name)
        mr_title = make_mr_title("Specs", "Delete", "spec", name)
        mr_description = make_mr_description(
            f"Deleting cluster spec **{name}**. This will not affect clusters already created from this spec.",
            username=current_user.username,
            action="delete",
            resource_type="spec",
            resource_name=name,
            repo="Specs",
        )
        commit_message = f"Delete spec {name}\n\nSpec file removed from specs catalog."

        try:
            self.gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[{"action": "delete", "file_path": path}],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = self.gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "specs", "delete"],
            )
        except GitLabError as exc:
            raise HTTPException(status_code=500, detail="Failed to delete spec") from exc

        self.cache.invalidate("specs:list")
        self.cache.invalidate(f"specs:detail:{name}")
        self.cache.invalidate("approvals:day1:list")

        return parse_mr_to_detail(mr_raw)

    # ── Clusters that use a spec ───────────────────────────────────────────────

    async def get_spec_clusters(self, spec_name: str) -> list[dict[str, Any]]:
        """Return list of cluster names/sites/mces using this spec (from metadata files)."""
        # This requires scanning the day1 repo — caller passes cluster data
        # or the router delegates to cluster_service. Service returns spec name filter.
        # Left for router to compose from cluster_service.list_clusters()
        raise NotImplementedError("Compose via cluster_service in router")
