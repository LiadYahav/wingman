"""The bodies of ``/api/day1/sites`` and ``/api/day1/mces``: MCE folders and their releases."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.application.sites import MceView
from wingman_day1.domain.openshift_versions import OpenShiftVersions


class MceOut(BaseModel):
    """An MCE folder (read-only) and what its files say."""

    name: str
    site: str
    env: str | None
    letter: str | None
    follows_convention: bool
    naming_problems: list[str]
    default_mastertag: str | None
    hub_version: str | None
    cluster_count: int
    stray_files: list[str]
    problems: list[str]

    @classmethod
    def of(cls, view: MceView) -> MceOut:
        """From an MCE view."""
        return cls(
            name=view.name,
            site=view.site,
            env=view.naming.env.value if view.naming.env else None,
            letter=view.naming.letter,
            follows_convention=view.naming.follows_convention,
            naming_problems=list(view.naming.problems),
            default_mastertag=view.default_mastertag,
            hub_version=view.hub_version,
            cluster_count=view.cluster_count,
            stray_files=list(view.stray_files),
            problems=list(view.problems),
        )


class OpenShiftVersionsOut(BaseModel):
    """The releases a new cluster on an MCE may use, newest first (ADR-0034)."""

    mce: str
    versions: list[str]
    problems: list[str]
    """Why ``versions`` may be short or empty: a missing or broken ``upgrade/`` file."""

    @classmethod
    def of(cls, offered: OpenShiftVersions) -> OpenShiftVersionsOut:
        """From the domain result."""
        return cls(
            mce=offered.mce, versions=list(offered.versions), problems=list(offered.problems)
        )
