"""The body of ``GET /api/day1/tuning-profiles``: what ``tuning/`` offers (ADR-0061)."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.domain.tuning_profiles import TUNING_DIR, TuningCatalog, TuningKind


class TuningProfileOut(BaseModel):
    """A shared profile a nodepool may name."""

    name: str
    kind: TuningKind
    summary: str | None
    """A Tuned's ``[main]`` ``summary=``; ``null`` for a PerformanceProfile or none."""
    path: str
    clusters: list[str]
    """Clusters (the chart's names) with their own ``tuning/<cluster>/<name>.yaml``."""
    requires_performance_profile: str | None
    """A Tuned including ``openshift-node-performance-<pp>``: the PerformanceProfile it needs."""


class TuningProblemOut(BaseModel):
    """A file under ``tuning/`` that is not offered, and why."""

    path: str
    detail: str


class TuningProfilesOut(BaseModel):
    """``GET /api/day1/tuning-profiles``: the shared profiles and the files that fail."""

    folder: str
    found: bool
    """``false``: the day1 repo has no ``tuning/``, so nothing is offered."""
    profiles: list[TuningProfileOut]
    problems: list[TuningProblemOut]

    @classmethod
    def of(cls, catalog: TuningCatalog) -> TuningProfilesOut:
        """From the catalogue."""
        return cls(
            folder=str(TUNING_DIR),
            found=catalog.found,
            profiles=[
                TuningProfileOut(
                    name=p.name,
                    kind=p.kind,
                    summary=p.summary,
                    path=str(p.path),
                    clusters=catalog.clusters_with_variant(p.name),
                    requires_performance_profile=p.requires_performance_profile,
                )
                for p in catalog.profiles()
            ],
            problems=[TuningProblemOut(path=p.path, detail=p.detail) for p in catalog.problems],
        )
