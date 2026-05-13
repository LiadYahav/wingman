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

from .template_analyzer import analyze_template

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
                files = await self.gl.alist_files(path=self.pr.specs_root, ref=self.default_branch)
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
                content, _ = await self.gl.aread_file(path, ref=self.default_branch)
                docs = parse_multi_document(content)
                if not docs:
                    raise ValueError(f"Empty spec file: {path}")
                spec = ClusterSpec.model_validate(docs[0])
            except Exception as exc:
                logger.warning("Failed to load spec %s: %s", name, exc)
                raise

            # Inject the shared cluster template (all specs use the same .j2 file)
            template_content = await self._get_shared_template()
            if template_content:
                spec = spec.model_copy(
                    update={"spec": spec.spec.model_copy(
                        update={"day1": spec.spec.day1.model_copy(
                            update={"template": template_content}
                        )}
                    )}
                )

            return spec

        return await self.cache.get_or_fetch(f"specs:detail:{name}", _fetch, ttl=60.0)

    async def _get_shared_template(self) -> str:
        async def _fetch() -> str:
            try:
                content, _ = await self.gl.aread_file(
                    self.pr.shared_template_file, ref=self.default_branch
                )
                return content
            except NotFoundError:
                return ""
            except Exception as exc:
                logger.warning("Failed to load shared template: %s", exc)
                return ""

        return await self.cache.get_or_fetch("specs:template:shared", _fetch, ttl=300.0)

    async def get_shared_template(self) -> str:
        return await self._get_shared_template()

    # ── Create ─────────────────────────────────────────────────────────────────

    async def create_spec(self, spec: ClusterSpec, current_user: UserInfo) -> MRDetail:
        path = self.pr.spec_file(spec_name=spec.metadata.name)

        if await self.gl.afile_exists(path, ref=self.default_branch):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Spec '{spec.metadata.name}' already exists",
            )

        # Strip inline template — all specs use the shared cluster-template.j2
        spec_without_template = spec.model_copy(
            update={"spec": spec.spec.model_copy(
                update={"day1": spec.spec.day1.model_copy(update={"template": ""})}
            )}
        )
        content = dump_multi_document([spec_without_template.model_dump(by_alias=True)])

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
            await self.gl.acommit_files(
                branch=branch,
                message=commit_message,
                actions=[{"action": "create", "file_path": path, "content": content}],
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = await self.gl.acreate_mr(
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
            _, last_commit_id = await self.gl.aread_file(path, ref=self.default_branch)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Spec '{name}' not found") from exc

        # Strip inline template — all specs use the shared cluster-template.j2
        spec_without_template = spec.model_copy(
            update={"spec": spec.spec.model_copy(
                update={"day1": spec.spec.day1.model_copy(update={"template": ""})}
            )}
        )
        content = dump_multi_document([spec_without_template.model_dump(by_alias=True)])

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

        actions: list[dict[str, Any]] = [
            {"action": "update", "file_path": path, "content": content, "last_commit_id": last_commit_id},
        ]

        # Migrate: delete any legacy per-spec .j2 file if it still exists
        legacy_template_path = self.pr.spec_template_file(spec_name=name)
        if await self.gl.afile_exists(legacy_template_path, ref=self.default_branch):
            actions.append({"action": "delete", "file_path": legacy_template_path})

        try:
            await self.gl.acommit_files(
                branch=branch,
                message=commit_message,
                actions=actions,
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = await self.gl.acreate_mr(
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
            await self.gl.aread_file(path, ref=self.default_branch)
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

        template_path = self.pr.spec_template_file(spec_name=name)
        actions: list[dict[str, Any]] = [{"action": "delete", "file_path": path}]
        if await self.gl.afile_exists(template_path, ref=self.default_branch):
            actions.append({"action": "delete", "file_path": template_path})

        try:
            await self.gl.acommit_files(
                branch=branch,
                message=commit_message,
                actions=actions,
                start_branch=self.default_branch,
                author_name=current_user.username,
            )
            mr_raw = await self.gl.acreate_mr(
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

    # ── OpenShift versions ────────────────────────────────────────────────────

    async def list_openshift_versions(self) -> list[str]:
        async def _fetch() -> list[str]:
            try:
                content, _ = await self.gl.aread_file("openshift-versions.txt", ref=self.default_branch)
            except NotFoundError:
                return []
            return [
                line.strip() for line in content.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]

        return await self.cache.get_or_fetch("specs:versions", _fetch, ttl=300.0)

    # ── Template schema ────────────────────────────────────────────────────────

    async def get_template_schema(self, *, include_reserved: bool = False) -> list[dict[str, Any]]:
        """Parse the shared Jinja2 template and return a dynamic variable schema."""
        cache_key = "specs:template:schema:all" if include_reserved else "specs:template:schema"

        async def _fetch() -> list[dict[str, Any]]:
            template = await self._get_shared_template()
            if not template:
                return []
            try:
                return analyze_template(template, include_reserved=include_reserved)
            except Exception as exc:
                logger.warning("Failed to analyze template: %s", exc)
                return []

        return await self.cache.get_or_fetch(cache_key, _fetch, ttl=300.0)

    # ── Version history ───────────────────────────────────────────────────────

    async def get_spec_history(self, name: str) -> list[dict]:
        """Return commit history for a spec file."""
        path = self.pr.spec_file(spec_name=name)
        try:
            commits = await self.gl.alist_commits(ref_name=self.default_branch, path=path)
        except Exception as exc:
            logger.warning("Failed to fetch spec history for %s: %s", name, exc)
            return []
        return [self.gl.format_commit(c) for c in commits]

    async def get_spec_at_sha(self, name: str, sha: str) -> str:
        """Return raw YAML of a spec at a specific commit SHA."""
        path = self.pr.spec_file(spec_name=name)
        content, _ = await self.gl.aread_file(path, ref=sha)
        return content

    # ── Clusters that use a spec ───────────────────────────────────────────────

    async def get_spec_clusters(self, spec_name: str) -> list[dict[str, Any]]:
        """Return list of cluster names/sites/mces using this spec (from metadata files)."""
        # This requires scanning the day1 repo — caller passes cluster data
        # or the router delegates to cluster_service. Service returns spec name filter.
        # Left for router to compose from cluster_service.list_clusters()
        raise NotImplementedError("Compose via cluster_service in router")
