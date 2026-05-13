"""Day2 addon service — browse, install, configure, and remove addons.

Manages the day2 GitLab repo structure:
  {DAY2_TEAMS_ROOT_PATH}/
  └── {team}/
      ├── operators/{addon}/values.yaml       # team defaults
      ├── operators/{addon}/{addon}.yaml       # ArgoCD metadata (contains repourl + version)
      └── mces/{mce}/{cluster}/{addon}/        # cluster overrides
              ├── values.yaml
              └── {addon}.yaml
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, cast

from fastapi import HTTPException
from pydantic import ValidationError
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient, GitLabGroupClient
from wingman_shared.models import (
    AddonArgoMetadata,
    AddonCatalogEntry,
    MergedAddonValues,
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
from wingman_shared.yaml_utils import (
    YamlParseResult,
    dump_multi_document,
    parse_multi_document,
)

from .helm_values_fetcher import HelmValuesFetcher

logger = logging.getLogger(__name__)


class AddonService:
    """Manages addon catalog browsing and cluster addon lifecycle.

    Teams are separate GitLab projects inside the sigs subgroup.
    Each operation routes to the correct per-team GitLabClient via
    GitLabGroupClient.get_project_client(team).
    """

    def __init__(
        self,
        group_client: GitLabGroupClient,
        path_resolver: PathResolver,
        cache: CacheManager,
        settings: Any,
    ) -> None:
        self.group_client = group_client
        self.pr = path_resolver
        self.cache = cache
        self.settings = settings
        self.helm_fetcher = HelmValuesFetcher(
            gitlab_url=settings.GITLAB_URL,
            access_token=settings.GITLAB_ACCESS_TOKEN,
            ssl_verify=settings.gitlab_ssl_verify,
            cache=cache,
            helm_values_ttl=settings.CACHE_HELM_VALUES_TTL,
            helm_branches_ttl=settings.CACHE_HELM_BRANCHES_TTL,
        )
        self._default_branch = settings.GITLAB_DEFAULT_BRANCH

    def _team_gl(self, team: str) -> GitLabClient:
        """Get the GitLabClient for a specific team's project."""
        return self.group_client.get_project_client(team)

    # ── Addon catalog ──────────────────────────────────────────────────────────

    async def list_teams(self) -> list[str]:
        async def _fetch() -> list[str]:
            return self.group_client.list_project_paths()

        return await self.cache.get_or_fetch(
            "day2:teams:list", _fetch, ttl=self.settings.CACHE_ADDON_CATALOG_TTL
        )

    async def list_addons(self, team: str | None = None) -> list[AddonCatalogEntry]:
        """List all addons, optionally filtered by team."""
        teams = [team] if team else await self.list_teams()
        all_addons: list[AddonCatalogEntry] = []
        for t in teams:
            addons = await self._list_team_addons(t)
            all_addons.extend(addons)
        return all_addons

    async def _list_team_addons(self, team: str) -> list[AddonCatalogEntry]:
        async def _fetch() -> list[AddonCatalogEntry]:
            try:
                gl = self._team_gl(team)
                operators_path = self.pr.day2_addon_def_dir(addon="").rstrip("/")
                addon_names = await gl.alist_directories(path=operators_path, ref=self._default_branch)
            except Exception as exc:
                logger.warning("Failed to list addons for team %s: %s", team, exc)
                return []

            entries: list[AddonCatalogEntry] = []
            for addon_name in addon_names:
                try:
                    entry = await self._load_catalog_entry(team, addon_name)
                    entries.append(entry)
                except Exception as exc:
                    logger.warning("Failed to load addon %s/%s: %s", team, addon_name, exc)
            return entries

        return await self.cache.get_or_fetch(
            f"day2:addons:list:{team}", _fetch, ttl=self.settings.CACHE_ADDON_CATALOG_TTL
        )

    async def _load_catalog_entry(self, team: str, addon_name: str) -> AddonCatalogEntry:
        async def _fetch() -> AddonCatalogEntry:
            gl = self._team_gl(team)
            values_path = self.pr.day2_addon_values(addon=addon_name)
            metadata_path = self.pr.day2_addon_argocd_metadata(addon=addon_name)

            team_values: dict[str, Any] = {}
            argocd_meta: AddonArgoMetadata | None = None
            available_versions: list[str] = []
            current_version: str = ""
            dependencies: list[str] = []

            try:
                values_content, _ = await gl.aread_file(values_path, ref=self._default_branch)
                docs = parse_multi_document(values_content)
                if docs:
                    raw = docs[0]
                    dependencies = raw.pop("dependencies", [])
                    team_values = raw
            except NotFoundError:
                pass
            except Exception as exc:
                logger.warning("Failed to parse team values %s: %s", values_path, exc)

            try:
                meta_content, _ = await gl.aread_file(metadata_path, ref=self._default_branch)
                docs = parse_multi_document(meta_content)
                if docs:
                    argocd_meta = AddonArgoMetadata.model_validate(docs[0])
                    available_versions = await self.helm_fetcher.list_versions(argocd_meta.repourl)
                    # Determine current version: use targetRevision if set, otherwise fallback
                    # to first available version or "main"
                    if argocd_meta.target_revision and argocd_meta.target_revision.strip():
                        current_version = argocd_meta.target_revision
                    elif available_versions:
                        # Use first available version (typically latest or main)
                        current_version = available_versions[0]
                    else:
                        current_version = "main"
            except (NotFoundError, ValidationError):
                pass
            except Exception as exc:
                logger.warning("Failed to parse addon metadata %s: %s", metadata_path, exc)

            return AddonCatalogEntry(
                team=team,
                name=addon_name,
                available_versions=available_versions,
                current_version=current_version,
                default_values=team_values,
                argocd_metadata=argocd_meta,
                dependencies=dependencies,
            )

        return await self.cache.get_or_fetch(
            f"day2:addons:catalog:{team}:{addon_name}",
            _fetch,
            ttl=self.settings.CACHE_ADDON_CATALOG_TTL,
        )

    async def get_addon_versions(self, team: str, addon_name: str) -> list[str]:
        """List available versions for an addon (git branches of its helm chart repo)."""
        entry = await self._load_catalog_entry(team, addon_name)
        if entry.argocd_metadata:
            return await self.helm_fetcher.list_versions(entry.argocd_metadata.repourl)
        return []

    async def get_addon_values_at_version(
        self, team: str, addon_name: str, version: str
    ) -> dict[str, Any]:
        """Fetch helm chart values.yaml for an addon at a specific version."""
        entry = await self._load_catalog_entry(team, addon_name)
        if not entry.argocd_metadata:
            return {}
        return await self.helm_fetcher.fetch_values(entry.argocd_metadata.repourl, version)

    # ── Cluster discovery (for pre-warming) ─────────────────────────────────────

    async def list_all_clusters(self) -> list[dict[str, str]]:
        """Discover all clusters across all teams by walking mces/{mce}/{cluster}/ directories.

        Returns list of {"mce": ..., "cluster": ...} dicts.
        Used by the background cache warmer to pre-warm cluster addon data.
        """
        async def _fetch() -> list[dict[str, str]]:
            clusters: list[dict[str, str]] = []
            teams = await self.list_teams()
            for team in teams:
                try:
                    gl = self._team_gl(team)
                    # List MCEs: mces/
                    mces_path = self.pr.day2_mces_root()
                    mces = await gl.alist_directories(path=mces_path, ref=self._default_branch)
                    for mce in mces:
                        # List clusters under each MCE: mces/{mce}/
                        mce_path = f"{mces_path}/{mce}"
                        cluster_names = await gl.alist_directories(path=mce_path, ref=self._default_branch)
                        for cluster in cluster_names:
                            # Avoid duplicates (same cluster may exist in multiple team repos)
                            entry = {"mce": mce, "cluster": cluster}
                            if entry not in clusters:
                                clusters.append(entry)
                except Exception as exc:
                    logger.warning("Failed to list clusters for team %s: %s", team, exc)
            return clusters

        return await self.cache.get_or_fetch(
            "day2:clusters:all", _fetch, ttl=self.settings.CACHE_ADDON_CATALOG_TTL
        )

    # ── Cluster addons ─────────────────────────────────────────────────────────

    async def list_cluster_addons(
        self, cluster_name: str, mce: str, team: str | None = None
    ) -> dict[str, Any]:
        """List installed addons for a cluster (all teams, or filtered)."""
        # Use cache for full cluster listing (no team filter)
        if team is None:
            cache_key = f"day2:cluster_addons:{mce}:{cluster_name}"
            return await self.cache.get_or_fetch(
                cache_key,
                lambda: self._fetch_cluster_addons(cluster_name, mce, None),
                ttl=self.settings.CACHE_ADDON_CATALOG_TTL,
            )
        # Team-filtered requests bypass cache (less common)
        return await self._fetch_cluster_addons(cluster_name, mce, team)

    async def _fetch_cluster_addons(
        self, cluster_name: str, mce: str, team: str | None
    ) -> dict[str, Any]:
        """Fetch installed addons for a cluster (internal, uncached)."""
        try:
            teams = [team] if team else await self.list_teams()
        except Exception as exc:
            logger.warning("Failed to list teams for cluster addons: %s", exc)
            return {"cluster": cluster_name, "mce": mce, "installed": []}

        installed: list[dict] = []

        for t in teams:
            try:
                gl = self._team_gl(t)
                addons_dir = self.pr.day2_cluster_addons_dir(mce=mce, cluster=cluster_name)
                addon_names = await gl.alist_directories(path=addons_dir, ref=self._default_branch)
            except Exception as exc:
                logger.warning("Failed to list addons for team %s cluster %s: %s", t, cluster_name, exc)
                continue

            for addon_name in addon_names:
                override_values_path = self.pr.day2_override_values(
                    mce=mce, cluster=cluster_name, addon=addon_name
                )
                override_meta_path = self.pr.day2_override_argocd_metadata(
                    mce=mce, cluster=cluster_name, addon=addon_name
                )

                override_values: dict = {}
                version = ""
                parse_errors: list[dict[str, Any]] = []

                try:
                    content, _ = await gl.aread_file(override_values_path, ref=self._default_branch)
                    result = cast(YamlParseResult, parse_multi_document(content, return_error=True))
                    if result.error:
                        parse_errors.append({
                            "file": "values.yaml",
                            "path": override_values_path,
                            **result.error.to_dict(),
                        })
                        logger.warning("Failed to parse %s: %s", override_values_path, result.error)
                    elif result.docs:
                        override_values = result.docs[0]
                except NotFoundError:
                    pass
                except Exception as exc:
                    parse_errors.append({
                        "file": "values.yaml",
                        "path": override_values_path,
                        "message": str(exc),
                    })
                    logger.warning("Failed to read %s: %s", override_values_path, exc)

                try:
                    meta_content, _ = await gl.aread_file(override_meta_path, ref=self._default_branch)
                    result = cast(YamlParseResult, parse_multi_document(meta_content, return_error=True))
                    if result.error:
                        parse_errors.append({
                            "file": f"{addon_name}.yaml",
                            "path": override_meta_path,
                            **result.error.to_dict(),
                        })
                        logger.warning("Failed to parse %s: %s", override_meta_path, result.error)
                    elif result.docs and result.docs[0]:
                        meta = AddonArgoMetadata.model_validate(result.docs[0])
                        version = meta.target_revision or ""
                except NotFoundError:
                    pass
                except ValidationError as exc:
                    parse_errors.append({
                        "file": f"{addon_name}.yaml",
                        "path": override_meta_path,
                        "message": f"Schema validation error: {exc}",
                    })
                except Exception as exc:
                    parse_errors.append({
                        "file": f"{addon_name}.yaml",
                        "path": override_meta_path,
                        "message": str(exc),
                    })
                    logger.warning("Failed to read %s: %s", override_meta_path, exc)

                addon_entry: dict[str, Any] = {
                    "team": t,
                    "name": addon_name,
                    "version": version,
                    "override_values": override_values,
                }
                if parse_errors:
                    addon_entry["parse_errors"] = parse_errors

                with contextlib.suppress(Exception):
                    addon_entry["gitlab_url"] = gl.get_tree_web_url(
                        self.pr.day2_override_dir(mce=mce, cluster=cluster_name, addon=addon_name),
                        ref=self._default_branch,
                    )

                installed.append(addon_entry)

        return {"cluster": cluster_name, "mce": mce, "installed": installed}

    async def get_cluster_addon_history(self, cluster_name: str, mce: str) -> list[dict]:
        """Return merged commit history across all teams for a cluster's addon overrides."""
        teams = await self.list_teams()
        cluster_dir = self.pr.day2_cluster_addons_dir(mce=mce, cluster=cluster_name)
        all_commits: list[dict] = []
        for t in teams:
            try:
                gl = self._team_gl(t)
                commits = await gl.alist_commits(ref_name=self._default_branch, path=cluster_dir)
                for c in commits:
                    all_commits.append(gl.format_commit(c, team=t))
            except Exception as exc:
                logger.warning("Failed to fetch addon history for team %s cluster %s: %s", t, cluster_name, exc)
        all_commits.sort(key=lambda x: x.get("date", ""), reverse=True)
        return all_commits

    async def get_merged_addon_values(
        self,
        *,
        team: str,
        addon_name: str,
        cluster_name: str,
        mce: str,
        version: str | None = None,
    ) -> MergedAddonValues:
        """Compute the 3-tier merged values with provenance."""
        from wingman_shared.yaml_utils import (  # noqa: PLC0415
            compute_provenance,
            merge_three_layers,
        )

        entry = await self._load_catalog_entry(team, addon_name)
        actual_version = version or entry.current_version

        # Layer 1: helm chart values.yaml at version
        chart_values: dict[str, Any] = {}
        if entry.argocd_metadata and actual_version:
            chart_values = await self.helm_fetcher.fetch_values(
                entry.argocd_metadata.repourl, actual_version
            )

        # Layer 2: team default values
        team_values = entry.default_values

        # Layer 3: cluster override values
        cluster_values: dict[str, Any] = {}
        override_path = self.pr.day2_override_values(
            mce=mce, cluster=cluster_name, addon=addon_name
        )
        try:
            content, _ = await self._team_gl(team).aread_file(override_path, ref=self._default_branch)
            docs = parse_multi_document(content)
            cluster_values = docs[0] if docs else {}
        except NotFoundError:
            pass
        except Exception as exc:
            logger.warning("Failed to parse cluster override values %s: %s", override_path, exc)

        merged = merge_three_layers(chart_values, team_values, cluster_values)
        provenance = compute_provenance(chart_values, team_values, cluster_values)

        return MergedAddonValues(
            merged=merged,
            provenance=provenance,
            chart_values=chart_values,
            team_values=team_values,
            cluster_values=cluster_values,
            addon_name=addon_name,
            team=team,
            version=actual_version,
        )

    # ── Addon install / update / remove ───────────────────────────────────────

    async def install_addon(
        self,
        *,
        team: str,
        addon_name: str,
        cluster_name: str,
        mce: str,
        version: str,
        override_values: dict[str, Any],
        current_user: UserInfo,
    ) -> MRDetail:
        """Install an addon on a cluster by creating override files via MR."""
        entry = await self._load_catalog_entry(team, addon_name)
        if not entry.argocd_metadata:
            raise HTTPException(
                status_code=404,
                detail=f"Addon {team}/{addon_name} has no ArgoCD metadata",
            )

        # Build override files
        gl = self._team_gl(team)
        override_values_path = self.pr.day2_override_values(
            mce=mce, cluster=cluster_name, addon=addon_name
        )
        override_meta_path = self.pr.day2_override_argocd_metadata(
            mce=mce, cluster=cluster_name, addon=addon_name
        )

        # Compute metadata overrides (only fields that differ from team defaults)
        # Determine team default version: use targetRevision if set, otherwise use
        # first available version or fallback to "main"
        meta_overrides: dict[str, Any] = {}
        team_default_version = ""
        if entry.argocd_metadata and entry.argocd_metadata.target_revision:
            team_default_version = entry.argocd_metadata.target_revision.strip()
        if not team_default_version:
            team_default_version = (
                entry.available_versions[0] if entry.available_versions else "main"
            )

        # Only write targetRevision override if version differs from team default
        # and the version is not empty
        if version and version != team_default_version:
            meta_overrides["targetRevision"] = version

        values_yaml = dump_multi_document([override_values]) if override_values else ""
        meta_yaml = dump_multi_document([meta_overrides])

        # Get repo URL with fallback
        repo_url = entry.argocd_metadata.repourl if entry.argocd_metadata else "unknown"

        overrides_summary = (
            f"{len(override_values)} key(s) overridden: {', '.join(list(override_values.keys())[:5])}"
            if override_values
            else "no value overrides (using team defaults)"
        )
        branch = make_branch_name(current_user.username, f"install-{addon_name}", cluster_name)
        mr_title = make_mr_title(
            "Day2", "Install", "addon", f"{team}/{addon_name}", f"v{version} on {cluster_name}"
        )
        mr_description = make_mr_description(
            f"Installing addon **{addon_name}** v{version} from team **{team}** on cluster **{cluster_name}**.\n"
            f"MCE: `{mce}`\n"
            f"Helm chart: `{repo_url}`\n"
            f"Overrides: {overrides_summary}.",
            username=current_user.username,
            action="install",
            resource_type="addon",
            resource_name=f"{team}/{addon_name}",
            repo="Day2",
        )
        commit_message = (
            f"Install {addon_name} v{version} on cluster {cluster_name}\n\n"
            f"Team: {team}, MCE: {mce}\n"
            f"Helm chart: {repo_url} @ {version}\n"
            f"Overrides: {overrides_summary}"
        )

        try:
            gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=[
                    {"action": "create", "file_path": override_values_path, "content": values_yaml},
                    {"action": "create", "file_path": override_meta_path, "content": meta_yaml},
                ],
                start_branch=self._default_branch,
                author_name=current_user.username,
            )
            mr_raw = gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day2", "install"],
            )
        except GitLabError as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to create install MR: {exc}"
            ) from exc

        self.cache.invalidate("approvals:day2:list")
        return parse_mr_to_detail(mr_raw)

    async def bulk_install_addons(
        self,
        *,
        cluster_name: str,
        mce: str,
        addons: list[
            tuple[str, str, str, dict[str, Any]]
        ],  # (team, addon_name, version, override_values)
        current_user: UserInfo,
        custom_message: str | None = None,
    ) -> MRDetail:
        """Install multiple addons on a cluster in a single MR."""
        if not addons:
            raise HTTPException(status_code=400, detail="No addons to install")

        # Group addons by team since each team has its own GitLab project
        addons_by_team: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for team, addon_name, version, override_values in addons:
            if team not in addons_by_team:
                addons_by_team[team] = []
            addons_by_team[team].append((addon_name, version, override_values))

        # For now, only support bulk install within a single team
        # (multi-team would require multiple MRs since they're different projects)
        if len(addons_by_team) > 1:
            raise HTTPException(
                status_code=400,
                detail="Bulk install across multiple teams not supported. All addons must be from the same team.",
            )

        team = list(addons_by_team.keys())[0]
        team_addons = addons_by_team[team]
        gl = self._team_gl(team)

        # Build all file actions
        all_actions: list[dict[str, Any]] = []
        addon_summaries: list[str] = []

        for addon_name, version, override_values in team_addons:
            entry = await self._load_catalog_entry(team, addon_name)

            override_values_path = self.pr.day2_override_values(
                mce=mce, cluster=cluster_name, addon=addon_name
            )
            override_meta_path = self.pr.day2_override_argocd_metadata(
                mce=mce, cluster=cluster_name, addon=addon_name
            )

            # Compute metadata overrides
            meta_overrides: dict[str, Any] = {}
            team_default_version = ""
            if entry.argocd_metadata and entry.argocd_metadata.target_revision:
                team_default_version = entry.argocd_metadata.target_revision.strip()
            if not team_default_version:
                team_default_version = (
                    entry.available_versions[0] if entry.available_versions else "main"
                )

            if version and version != team_default_version:
                meta_overrides["targetRevision"] = version

            values_yaml = (
                dump_multi_document([override_values])
                if override_values
                else dump_multi_document([{}])
            )
            meta_yaml = dump_multi_document([meta_overrides])

            # Add file actions
            for path, content in [
                (override_values_path, values_yaml),
                (override_meta_path, meta_yaml),
            ]:
                action = "update" if gl.file_exists(path, ref=self._default_branch) else "create"
                all_actions.append({"action": action, "file_path": path, "content": content})

            # Build summary for this addon
            overrides_count = len(override_values) if override_values else 0
            addon_summaries.append(
                f"- **{addon_name}** v{version} ({overrides_count} override{'s' if overrides_count != 1 else ''})"
            )

        # Build MR title and description
        addon_count = len(team_addons)
        addon_names = [a[0] for a in team_addons]

        if addon_count == 1:
            mr_title = f"[Day2] Install {addon_names[0]} on {cluster_name}"
        else:
            mr_title = f"[Day2] Install {addon_count} addons on {cluster_name}"

        mr_description_parts = [
            f"Installing {addon_count} addon{'s' if addon_count > 1 else ''} on cluster **{cluster_name}**",
            f"**Team:** {team}",
            f"**MCE:** `{mce}`",
            "",
            "**Addons:**",
            *addon_summaries,
        ]

        # Append custom message if provided
        if custom_message:
            mr_description_parts.extend(["", "**Notes:**", custom_message])

        mr_description = make_mr_description(
            "\n".join(mr_description_parts),
            username=current_user.username,
            action="install",
            resource_type="addons",
            resource_name=f"{addon_count} addons",
            repo="Day2",
        )

        commit_message = (
            f"Install {addon_count} addon{'s' if addon_count > 1 else ''} on {cluster_name}\n\n"
            f"Team: {team}, MCE: {mce}\n"
            f"Addons: {', '.join(f'{a[0]}@{a[1]}' for a in team_addons)}"
        )

        branch = make_branch_name(
            current_user.username, f"bulk-install-{addon_count}-addons", cluster_name
        )

        try:
            gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=all_actions,
                start_branch=self._default_branch,
                author_name=current_user.username,
            )
            mr_raw = gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day2", "bulk-install"],
            )
        except GitLabError as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to create bulk install MR: {exc}"
            ) from exc

        self.cache.invalidate("approvals:day2:list")
        return parse_mr_to_detail(mr_raw)

    async def update_addon(
        self,
        *,
        team: str,
        addon_name: str,
        cluster_name: str,
        mce: str,
        version: str,
        override_values: dict[str, Any],
        current_user: UserInfo,
    ) -> MRDetail:
        """Update an installed addon's version or values via MR."""
        gl = self._team_gl(team)
        override_values_path = self.pr.day2_override_values(
            mce=mce, cluster=cluster_name, addon=addon_name
        )
        override_meta_path = self.pr.day2_override_argocd_metadata(
            mce=mce, cluster=cluster_name, addon=addon_name
        )

        entry = await self._load_catalog_entry(team, addon_name)
        if not entry.argocd_metadata:
            raise HTTPException(status_code=404, detail=f"Addon {team}/{addon_name} not found")

        previous_version = entry.current_version

        # Compute metadata overrides (only fields that differ from team defaults)
        # Determine team default version: use targetRevision if set, otherwise use
        # first available version or fallback to "main"
        meta_overrides: dict[str, Any] = {}
        team_default_version = ""
        if entry.argocd_metadata and entry.argocd_metadata.target_revision:
            team_default_version = entry.argocd_metadata.target_revision.strip()
        if not team_default_version:
            team_default_version = (
                entry.available_versions[0] if entry.available_versions else "main"
            )

        # Only write targetRevision override if version differs from team default
        # and the version is not empty
        if version and version != team_default_version:
            meta_overrides["targetRevision"] = version

        values_yaml = dump_multi_document([override_values])
        meta_yaml = dump_multi_document([meta_overrides]) if meta_overrides else ""

        version_change = (
            f"version upgrade {previous_version} → {version}"
            if previous_version and previous_version != version
            else f"version {version} (no version change)"
        )
        overrides_summary = (
            f"{len(override_values)} key(s): {', '.join(list(override_values.keys())[:5])}"
            if override_values
            else "cleared (using team defaults)"
        )
        branch = make_branch_name(current_user.username, f"update-{addon_name}", cluster_name)
        mr_title = make_mr_title(
            "Day2", "Update", "addon", f"{team}/{addon_name}", f"to v{version} on {cluster_name}"
        )
        mr_description = make_mr_description(
            f"Updating addon **{addon_name}** on cluster **{cluster_name}**: {version_change}.\n"
            f"MCE: `{mce}`\n"
            f"Value overrides: {overrides_summary}.",
            username=current_user.username,
            action="update",
            resource_type="addon",
            resource_name=f"{team}/{addon_name}",
            repo="Day2",
        )
        commit_message = (
            f"Update {addon_name} on cluster {cluster_name}: {version_change}\n\n"
            f"Team: {team}, MCE: {mce}\n"
            f"Value overrides: {overrides_summary}"
        )

        actions = []
        # Always write values file (even if empty - means using team defaults)
        values_action = (
            "update" if gl.file_exists(override_values_path, ref=self._default_branch) else "create"
        )
        actions.append(
            {"action": values_action, "file_path": override_values_path, "content": values_yaml}
        )

        # Handle metadata file: create/update if overrides exist, delete if reverting to team default
        meta_file_exists = gl.file_exists(override_meta_path, ref=self._default_branch)
        if meta_overrides:
            meta_action = "update" if meta_file_exists else "create"
            actions.append(
                {"action": meta_action, "file_path": override_meta_path, "content": meta_yaml}
            )
        elif meta_file_exists:
            # Version matches team default now - remove override file to keep state clean
            actions.append({"action": "delete", "file_path": override_meta_path})

        try:
            gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=actions,
                start_branch=self._default_branch,
                author_name=current_user.username,
            )
            mr_raw = gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day2", "update"],
            )
        except GitLabError as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to create update MR: {exc}"
            ) from exc

        self.cache.invalidate("approvals:day2:list")
        return parse_mr_to_detail(mr_raw)

    async def remove_addon(
        self,
        *,
        team: str,
        addon_name: str,
        cluster_name: str,
        mce: str,
        current_user: UserInfo,
    ) -> MRDetail:
        """Remove an addon from a cluster via MR."""
        gl = self._team_gl(team)
        override_values_path = self.pr.day2_override_values(
            mce=mce, cluster=cluster_name, addon=addon_name
        )
        override_meta_path = self.pr.day2_override_argocd_metadata(
            mce=mce, cluster=cluster_name, addon=addon_name
        )

        actions = []
        for path in [override_values_path, override_meta_path]:
            if gl.file_exists(path, ref=self._default_branch):
                actions.append({"action": "delete", "file_path": path})

        if not actions:
            raise HTTPException(
                status_code=404,
                detail=f"Addon {addon_name} is not installed on {cluster_name}",
            )

        # Try to get current version for the commit message
        current_version = ""
        try:
            override_meta_content, _ = await gl.aread_file(override_meta_path, ref=self._default_branch)
            docs = parse_multi_document(override_meta_content)
            if docs:
                current_version = AddonArgoMetadata.model_validate(docs[0]).target_revision
        except NotFoundError:
            pass
        except Exception as exc:
            logger.warning("Failed to parse addon metadata for removal %s: %s", override_meta_path, exc)

        branch = make_branch_name(current_user.username, f"remove-{addon_name}", cluster_name)
        mr_title = make_mr_title(
            "Day2", "Remove", "addon", f"{team}/{addon_name}", f"from {cluster_name}"
        )
        mr_description = make_mr_description(
            f"Removing addon **{addon_name}** from cluster **{cluster_name}**.\n"
            f"Team: **{team}**, MCE: `{mce}`"
            + (f", currently at v{current_version}" if current_version else "")
            + ".\n"
            f"Override files ({len(actions)} file(s)) will be deleted.",
            username=current_user.username,
            action="remove",
            resource_type="addon",
            resource_name=f"{team}/{addon_name}",
            repo="Day2",
        )
        commit_message = (
            f"Remove {addon_name} from cluster {cluster_name}\n\n"
            f"Team: {team}, MCE: {mce}"
            + (f"\nPrevious version: {current_version}" if current_version else "")
            + "\n"
            f"Deleted {len(actions)} override file(s)"
        )

        try:
            gl.commit_files(
                branch=branch,
                message=commit_message,
                actions=actions,
                start_branch=self._default_branch,
                author_name=current_user.username,
            )
            mr_raw = gl.create_mr(
                source_branch=branch,
                title=mr_title,
                description=mr_description,
                labels=["wingman", "day2", "remove"],
            )
        except GitLabError as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to create remove MR: {exc}"
            ) from exc

        self.cache.invalidate("approvals:day2:list")
        return parse_mr_to_detail(mr_raw)
