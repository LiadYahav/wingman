"""Configurable path resolution for all three GitLab repos.

ALL file paths are built from env var templates — nothing is hardcoded.

Placeholders available per template:
  {site}    — site name (day1)
  {mce}     — MCE name (day1 + day2)
  {cluster} — cluster name (day1 + day2)
  {team}    — team name (day2)
  {addon}   — addon name (day2)
"""

from __future__ import annotations


class PathResolver:
    """Resolves GitLab file paths from configurable env var templates.

    Keeps the GitLab client completely decoupled from path structure.
    Both services receive a PathResolver instance via FastAPI Depends().
    """

    def __init__(
        self,
        day1_clusters_path_template: str,
        day2_addon_defs_path_template: str,
        day2_addon_overrides_path_template: str,
        specs_root_path: str,
        day2_teams_root_path: str = "",  # unused — teams are GitLab projects now
    ) -> None:
        self._day1_clusters = day1_clusters_path_template
        self._day2_defs = day2_addon_defs_path_template
        self._day2_overrides = day2_addon_overrides_path_template
        self.specs_root = specs_root_path

    # ── Day1 paths ────────────────────────────────────────────────────────────

    def day1_cluster_dir(self, *, site: str, mce: str) -> str:
        """Directory containing cluster files."""
        return self._day1_clusters.format(site=site, mce=mce)

    def day1_cluster_file(self, *, site: str, mce: str, cluster: str) -> str:
        """Main multi-document YAML for the cluster."""
        return f"{self.day1_cluster_dir(site=site, mce=mce)}/{cluster}.yaml"

    def day1_cluster_metadata(self, *, site: str, mce: str, cluster: str) -> str:
        """Wingman metadata file (.wingman.yaml) for the cluster."""
        return f"{self.day1_cluster_dir(site=site, mce=mce)}/{cluster}.wingman.yaml"

    # ── Day2 addon definition paths (relative to team project root) ──────────────
    # The team is identified by which GitLabClient (project) is used — not by path.

    def day2_addon_def_dir(self, *, addon: str) -> str:
        """Directory containing team-level addon defaults (relative to team project root)."""
        return self._day2_defs.format(addon=addon)

    def day2_addon_values(self, *, addon: str) -> str:
        """Team default values.yaml for an addon."""
        return f"{self.day2_addon_def_dir(addon=addon)}/values.yaml"

    def day2_addon_argocd_metadata(self, *, addon: str) -> str:
        """Team default ArgoCD metadata file for an addon."""
        return f"{self.day2_addon_def_dir(addon=addon)}/{addon}.yaml"

    # ── Day2 cluster override paths (relative to team project root) ───────────

    def day2_override_dir(self, *, mce: str, cluster: str, addon: str) -> str:
        """Directory containing cluster-specific addon overrides."""
        return self._day2_overrides.format(mce=mce, cluster=cluster, addon=addon)

    def day2_override_values(self, *, mce: str, cluster: str, addon: str) -> str:
        """Cluster-specific override values.yaml (highest priority layer)."""
        return f"{self.day2_override_dir(mce=mce, cluster=cluster, addon=addon)}/values.yaml"

    def day2_override_argocd_metadata(self, *, mce: str, cluster: str, addon: str) -> str:
        """Cluster-specific ArgoCD metadata override."""
        return f"{self.day2_override_dir(mce=mce, cluster=cluster, addon=addon)}/{addon}.yaml"

    def day2_cluster_addons_dir(self, *, mce: str, cluster: str) -> str:
        """Parent directory listing all addons installed on a cluster (for a given team)."""
        return self._day2_overrides.format(mce=mce, cluster=cluster, addon="").rstrip("/")

    def day2_mces_root(self) -> str:
        """Root directory for all MCEs (for enumerating clusters)."""
        # Extract the base path before {mce} placeholder
        # e.g., "mces/{mce}/{cluster}/{addon}" -> "mces"
        base = self._day2_overrides.split("{mce}")[0].rstrip("/")
        return base if base else "mces"

    # ── Specs paths ───────────────────────────────────────────────────────────

    def spec_file(self, *, spec_name: str) -> str:
        """YAML file for a cluster spec."""
        return f"{self.specs_root}/{spec_name}.yaml"
