"""Fetch values.yaml from a helm chart repo at a specific version (branch).

The addon's {addon}.yaml contains a `repourl` pointing to the helm chart GitLab repo.
This fetcher creates a temporary GitLabClient for that project and reads values.yaml
at the requested branch (branch name == version).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import GitLabError, NotFoundError
from wingman_shared.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


def _extract_project_path(repourl: str, gitlab_base_url: str) -> str:
    """Extract the GitLab project path from a full repourl.

    Example:
        repourl   = "https://gitlab.internal/charts/cert-manager"
        gitlab_url = "https://gitlab.internal"
        -> "charts/cert-manager"
    """
    base = gitlab_base_url.rstrip("/")
    url = repourl.rstrip("/")

    if url.startswith(base):
        path = url[len(base) :].lstrip("/")
        # Strip .git suffix if present
        return re.sub(r"\.git$", "", path)

    # Fallback: try to extract path from URL
    parsed = urlparse(repourl)
    return parsed.path.lstrip("/").rstrip("/").removesuffix(".git")


class HelmValuesFetcher:
    """Fetches helm chart values.yaml from addon helm chart repos."""

    def __init__(
        self,
        gitlab_url: str,
        access_token: str,
        ssl_verify: bool | str,
        cache: CacheManager,
        helm_values_ttl: float = 300.0,
        helm_branches_ttl: float = 120.0,
    ) -> None:
        self._gitlab_url = gitlab_url
        self._access_token = access_token
        self._ssl_verify = ssl_verify
        self._cache = cache
        self._helm_values_ttl = helm_values_ttl
        self._helm_branches_ttl = helm_branches_ttl

    def _get_client(self, project_path: str) -> GitLabClient:
        """Create a GitLabClient for a helm chart repo (cached by project path)."""
        return GitLabClient(
            gitlab_url=self._gitlab_url,
            access_token=self._access_token,
            project_id=project_path,
            ssl_verify=self._ssl_verify,
        )

    async def list_versions(self, repourl: str) -> list[str]:
        """List available versions (branch names) from the addon's helm chart repo."""
        project_path = _extract_project_path(repourl, self._gitlab_url)

        async def _fetch() -> list[str]:
            try:
                client = self._get_client(project_path)
                branches = client.list_branches()
                # Exclude non-useful branches but always keep "main" if it exists
                exclude_branches = {"master", "HEAD", "develop", "dev"}
                versions = [b for b in branches if b not in exclude_branches]
                # Sort: "main" first, then other versions in descending order
                main_branch = []
                other_versions = []
                for v in versions:
                    if v == "main":
                        main_branch.append(v)
                    else:
                        other_versions.append(v)
                return main_branch + sorted(other_versions, reverse=True)
            except GitLabError as exc:
                logger.warning("Failed to list versions for %s: %s", repourl, exc)
                return []

        return await self._cache.get_or_fetch(
            f"day2:helm:branches:{project_path}",
            _fetch,
            ttl=self._helm_branches_ttl,
        )

    async def fetch_values(self, repourl: str, version: str) -> dict:
        """Fetch values.yaml from the helm chart repo at the given version (branch)."""
        project_path = _extract_project_path(repourl, self._gitlab_url)

        async def _fetch() -> dict:
            try:
                client = self._get_client(project_path)
                content, _ = client.read_file("values.yaml", ref=version)
                from wingman_shared.yaml_utils import parse_multi_document  # noqa: PLC0415

                docs = parse_multi_document(content)
                return docs[0] if docs else {}
            except NotFoundError:
                logger.debug("No values.yaml in %s@%s", repourl, version)
                return {}
            except GitLabError as exc:
                logger.warning("Failed to fetch values from %s@%s: %s", repourl, version, exc)
                return {}
            except Exception as exc:
                logger.warning("Failed to parse values.yaml from %s@%s: %s", repourl, version, exc)
                return {}

        return await self._cache.get_or_fetch(
            f"day2:helm:values:{project_path}:{version}",
            _fetch,
            ttl=self._helm_values_ttl,
        )
