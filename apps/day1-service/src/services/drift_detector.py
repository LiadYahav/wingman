"""Drift detection — compare actual cluster files in Git vs what the spec would produce.

Drift is purely Git-level: re-render the spec template with stored variables,
then compare to the actual cluster YAML. No live cluster access.

Two flavors:
  - per_cluster_drift: check one cluster's actual YAML vs its spec re-render
  - spec_drift_summary: check ALL clusters that reference a given spec
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field

from wingman_shared.exceptions import NotFoundError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import ClusterMetadata, ClusterSpec
from wingman_shared.path_resolver import PathResolver
from wingman_shared.yaml_utils import normalize_yaml, parse_multi_document

from .yaml_renderer import apply_variable_defaults, render_spec

logger = logging.getLogger(__name__)


@dataclass
class AddonDriftEntry:
    addon_name: str
    team: str
    reason: str  # "missing" | "version_mismatch"
    expected_version: str = ""
    installed_version: str = ""


@dataclass
class DriftResult:
    cluster_name: str
    site: str
    mce: str
    spec_name: str
    spec_version: str
    is_drifted: bool
    unified_diff: str = ""  # empty when not drifted
    missing_keys: list[str] = field(default_factory=list)
    extra_keys: list[str] = field(default_factory=list)
    addon_drift: list[AddonDriftEntry] = field(default_factory=list)


class DriftDetector:
    """Compares cluster YAML in the day1 repo vs the spec it was created from."""

    def __init__(
        self,
        gitlab_day1: GitLabClient,
        gitlab_specs: GitLabClient,
        path_resolver: PathResolver,
        default_branch: str = "main",
    ) -> None:
        self.gl_day1 = gitlab_day1
        self.gl_specs = gitlab_specs
        self.pr = path_resolver
        self.default_branch = default_branch

    @staticmethod
    def check_addon_compliance(
        spec: ClusterSpec,
        installed_addons: list[dict],
    ) -> list[AddonDriftEntry]:
        """Compare spec-required addons against actually installed addons.

        Returns a list of drift entries for addons that are missing or at the
        wrong version. Extra addons (installed but not required by spec) are
        ignored — they may be intentional admin additions.
        """
        installed_by_name: dict[str, dict] = {a["name"]: a for a in installed_addons}
        drift: list[AddonDriftEntry] = []

        for spec_addon in spec.spec.day2.addons:
            installed = installed_by_name.get(spec_addon.name)
            if installed is None:
                drift.append(
                    AddonDriftEntry(
                        addon_name=spec_addon.name,
                        team=spec_addon.team,
                        reason="missing",
                        expected_version=spec_addon.version,
                    )
                )
            elif installed.get("version", "") != spec_addon.version:
                drift.append(
                    AddonDriftEntry(
                        addon_name=spec_addon.name,
                        team=spec_addon.team,
                        reason="version_mismatch",
                        expected_version=spec_addon.version,
                        installed_version=installed.get("version", ""),
                    )
                )

        return drift

    async def check_cluster(
        self,
        *,
        cluster_name: str,
        site: str,
        mce: str,
        metadata: ClusterMetadata,
        spec: ClusterSpec,
        installed_addons: list[dict] | None = None,
    ) -> DriftResult:
        """Check drift for a single cluster.

        Args:
            cluster_name: Cluster name
            site: Site identifier
            mce: MCE identifier
            metadata: The .wingman.yaml metadata (contains stored variables)
            spec: The current spec object from the specs repo

        Returns:
            DriftResult with is_drifted flag and unified diff if drifted.
        """
        cluster_path = self.pr.day1_cluster_file(site=site, mce=mce, cluster=cluster_name)

        try:
            actual_content, _ = self.gl_day1.read_file(cluster_path, ref=self.default_branch)
        except NotFoundError:
            return DriftResult(
                cluster_name=cluster_name,
                site=site,
                mce=mce,
                spec_name=metadata.spec_name,
                spec_version=metadata.spec_version,
                is_drifted=True,
                unified_diff="Cluster file not found in repository",
            )

        # Re-render the spec with stored variables to get expected output
        variables_with_defaults = apply_variable_defaults(spec, dict(metadata.variables))

        try:
            expected_content = render_spec(spec, variables_with_defaults)
        except Exception as exc:
            logger.warning(
                "Cannot render spec %s for drift check on %s: %s",
                metadata.spec_name,
                cluster_name,
                exc,
            )
            return DriftResult(
                cluster_name=cluster_name,
                site=site,
                mce=mce,
                spec_name=metadata.spec_name,
                spec_version=metadata.spec_version,
                is_drifted=False,  # Cannot determine drift if spec can't render
                unified_diff="",
            )

        # Normalize both sides to remove formatting noise before comparing
        try:
            actual_normalized = _normalize_multi_doc(actual_content)
            expected_normalized = _normalize_multi_doc(expected_content)
        except Exception as exc:
            logger.warning("YAML normalization failed for %s: %s", cluster_name, exc)
            actual_normalized = actual_content.strip()
            expected_normalized = expected_content.strip()

        # Check Day 2 addon compliance
        addon_drift = self.check_addon_compliance(spec, installed_addons or [])

        if actual_normalized == expected_normalized:
            return DriftResult(
                cluster_name=cluster_name,
                site=site,
                mce=mce,
                spec_name=metadata.spec_name,
                spec_version=metadata.spec_version,
                is_drifted=bool(addon_drift),
                addon_drift=addon_drift,
            )

        # Compute unified diff for display
        diff_lines = list(
            difflib.unified_diff(
                expected_normalized.splitlines(keepends=True),
                actual_normalized.splitlines(keepends=True),
                fromfile=f"expected ({metadata.spec_name} v{metadata.spec_version})",
                tofile=f"actual ({cluster_name})",
                lineterm="",
            )
        )

        return DriftResult(
            cluster_name=cluster_name,
            site=site,
            mce=mce,
            spec_name=metadata.spec_name,
            spec_version=metadata.spec_version,
            is_drifted=True,
            unified_diff="".join(diff_lines),
            addon_drift=addon_drift,
        )

    async def check_spec_clusters(
        self,
        spec_name: str,
        spec: ClusterSpec,
        cluster_list: list[dict],  # [{name, site, mce}]
    ) -> list[DriftResult]:
        """Check drift for all clusters created from a given spec."""
        results: list[DriftResult] = []

        for cluster_info in cluster_list:
            name = cluster_info["name"]
            site = cluster_info["site"]
            mce = cluster_info["mce"]

            metadata_path = self.pr.day1_cluster_metadata(site=site, mce=mce, cluster=name)
            try:
                content, _ = self.gl_day1.read_file(metadata_path, ref=self.default_branch)
                docs = parse_multi_document(content)
                metadata = ClusterMetadata.model_validate(docs[0])
            except Exception as exc:
                logger.warning("Cannot read metadata for %s: %s", name, exc)
                continue

            if metadata.spec_name != spec_name:
                continue

            result = await self.check_cluster(
                cluster_name=name,
                site=site,
                mce=mce,
                metadata=metadata,
                spec=spec,
            )
            results.append(result)

        return results


def _normalize_multi_doc(content: str) -> str:
    """Normalize all documents in a multi-doc YAML for comparison."""
    try:
        docs = parse_multi_document(content)
        parts = []
        for doc in docs:
            if doc is None:
                continue
            parts.append(
                normalize_yaml(str(doc) if not isinstance(doc, dict) else _dict_to_yaml(doc))
            )
        return "\n---\n".join(parts)
    except Exception:
        return content.strip()


def _dict_to_yaml(data: dict) -> str:
    from wingman_shared.yaml_utils import dump_single  # noqa: PLC0415

    return dump_single(data)
