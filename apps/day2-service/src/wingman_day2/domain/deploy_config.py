"""The deploy config (``<chart>.yaml``) and the leaf Application it produces.

The deploy config is a values file of the platform's ``deploy`` chart, merged
through its own stack (team default, OCP-version pin, fleet default, the
cluster's folder; ``stacks.deploy_config_layers``). ``deployApp.yaml`` turns
the merged values into the leaf Application; :func:`leaf_application` is that
template in Python:

- ``repourl``, **lowercase only**. ``repoUrl`` reaches the template as nil and
  renders an empty ``repoURL``, a known bug in several production files.
- ``targetRevision`` defaults to ``HEAD``; ``path`` to ``.``.
- ``releaseName`` is the chart (``<cluster>-<team>-<chart>`` with ``oldConvention``).
- the app is ``<team>-<cluster>-<chart>-deploy`` unless ``appname`` is set.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from wingman_core.domain.git import Project
from wingman_day2.domain.clusters import UPI_ARGO_NAMESPACE, ClusterKind, ClusterRef

REPOURL: Final = "repourl"
TARGET_REVISION: Final = "targetRevision"
PATH: Final = "path"
PROJECT_NAMESPACE: Final = "projectNamespace"
SYNC_POLICY: Final = "syncPolicy"
IGNORE_DIFFERENCES: Final = "ignoreDifferences"
APPNAME: Final = "appname"
OLD_CONVENTION: Final = "oldConvention"
DEFAULT_REVISION: Final = "HEAD"
DEFAULT_PATH: Final = "."


def truthy(value: object) -> bool:
    """Go template truthiness (``if``, ``default``): nil, false, 0, "" and empties are false."""
    if value is None or value is False:
        return False
    if isinstance(value, int | float | str | list | dict | tuple):
        return bool(value)
    return True


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def repourl_moved_to(repo_url: str, project: Project) -> str | None:
    """The URL to write instead, when ``repo_url`` names ``project`` by an old path.

    GitLab keeps a renamed or moved project's old path as a redirect, so the
    old ``repourl`` still works for git and ArgoCD, until someone creates a
    project at the old path. ``None`` when ``repo_url`` is already current.
    """
    path = urlsplit(repo_url.strip()).path.strip("/").removesuffix(".git")
    current = project.path_with_namespace.strip("/")
    if f"/{path}".lower().endswith(f"/{current}".lower()):
        return None
    return f"{project.web_url}.git" if repo_url.strip().endswith(".git") else project.web_url


def miscased_repourl_keys(doc: Mapping[str, object]) -> list[str]:
    """Keys that look like ``repourl`` but are not it (``repoUrl``, ``repoURL``, ...)."""
    return sorted(k for k in doc if k.lower() == REPOURL and k != REPOURL)


@dataclass(frozen=True, slots=True)
class LeafApplication:
    """The identity fields of the leaf Application ``deployApp.yaml`` renders."""

    name: str
    argo: str
    namespace: str
    repo_url: str
    target_revision: str
    path: str
    release_name: str
    destination: str
    destination_namespace: str | None
    sync_policy: object
    ignore_differences: object

    @property
    def auto_sync(self) -> bool:
        """Whether the leaf syncs by itself; leaves are manual-sync unless the config opts in."""
        return isinstance(self.sync_policy, Mapping) and truthy(self.sync_policy.get("automated"))


def leaf_application(
    merged: Mapping[str, object], *, team: str, chart: str, ref: ClusterRef
) -> LeafApplication:
    """What ``deployApp.yaml`` renders for ``merged`` deploy values on ``ref``."""
    cluster = ref.argo_cluster
    revision = merged.get(TARGET_REVISION)
    path = merged.get(PATH)
    namespace = merged.get(PROJECT_NAMESPACE)
    sync_policy = merged.get(SYNC_POLICY)
    ignore = merged.get(IGNORE_DIFFERENCES)
    return LeafApplication(
        name=(
            _text(merged[APPNAME])
            if truthy(merged.get(APPNAME))
            else f"{team}-{cluster}-{chart}-deploy"
        ),
        argo=ref.argo_instance,
        namespace=UPI_ARGO_NAMESPACE if ref.kind is ClusterKind.UPI else f"gitops-{team}",
        repo_url=_text(merged.get(REPOURL)),
        target_revision=_text(revision) if truthy(revision) else DEFAULT_REVISION,
        path=_text(path) if truthy(path) else DEFAULT_PATH,
        release_name=(f"{cluster}-{team}-{chart}" if truthy(merged.get(OLD_CONVENTION)) else chart),
        destination=cluster,
        destination_namespace=_text(namespace) if truthy(namespace) else None,
        sync_policy=sync_policy if truthy(sync_policy) else None,
        ignore_differences=ignore if truthy(ignore) else None,
    )
