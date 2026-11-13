"""The bodies of ``/api/day1/specs/{name}/import``: existing clusters into a flavor (ADR-0044)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wingman_core.web.errors import from_git_error
from wingman_day1.api.v1.schemas import ClusterDriftOut, MRDetailOut, _In, change_out
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.imports import (
    ImportCandidate,
    ImportedCluster,
    ImportFailure,
    ImportPreview,
    ImportResult,
)

MAX_PICKED = 500
"""A request-size bound; the import itself takes at most ``imports.MAX_IMPORT``."""


class ClusterPickIn(_In):
    """A cluster to compare with a flavor; ``site`` and ``mce`` only when the name is ambiguous."""

    name: str = Field(min_length=1, max_length=63)
    site: str | None = Field(default=None, min_length=1, max_length=63)
    mce: str | None = Field(default=None, min_length=1, max_length=63)


class ImportPreviewIn(_In):
    """The clusters to preview an import of."""

    clusters: list[ClusterPickIn] = Field(min_length=1, max_length=MAX_PICKED)


class ImportPickIn(_In):
    """A cluster to import, as the preview returned it."""

    name: str = Field(min_length=1, max_length=63)
    site: str = Field(min_length=1, max_length=63)
    mce: str = Field(min_length=1, max_length=63)
    last_commit_id: str = Field(min_length=7, max_length=64)
    """The preview's ``last_commit_id``: a file that moved since fails the import."""
    relink: bool = False
    """``true`` to link a cluster that follows another flavor to this one instead."""


class ImportIn(_In):
    """Link existing clusters to the flavor: one day1 MR per cluster (ADR-0044)."""

    spec_version: str = Field(min_length=1, max_length=64)
    """The flavor version the preview showed."""
    clusters: list[ImportPickIn] = Field(min_length=1, max_length=MAX_PICKED)


class LinkedSpecOut(BaseModel):
    """The flavor a cluster file's header names."""

    name: str
    version: str | None


class ImportCandidateOut(BaseModel):
    """One picked cluster in an import preview."""

    name: str
    site: str
    mce: str
    path: str
    last_commit_id: str
    """Send it back with the import."""
    status: Literal["ready", "relink", "linked", "refused"]
    linked_spec: LinkedSpecOut | None
    """The flavor the file follows now, if any."""
    problems: list[str]
    """Why it cannot be imported as it is (empty for ``ready``)."""
    drift: ClusterDriftOut
    """The cluster against this flavor: what will show as drift once it is linked."""

    @classmethod
    def of(cls, candidate: ImportCandidate) -> ImportCandidateOut:
        """From an import candidate."""
        cluster = candidate.cluster
        provenance = cluster.provenance
        return cls(
            name=cluster.ref.name,
            site=cluster.ref.site,
            mce=cluster.ref.mce,
            path=str(cluster.ref.path),
            last_commit_id=cluster.last_commit_id,
            status=candidate.status.value,
            linked_spec=LinkedSpecOut(name=provenance.spec_name, version=provenance.spec_version)
            if provenance.spec_name
            else None,
            problems=list(candidate.problems),
            drift=ClusterDriftOut.of(candidate.drift),
        )


class ImportPreviewOut(BaseModel):
    """``POST /specs/{name}/import/preview``."""

    spec_name: str
    spec_version: str
    """Send it back with the import."""
    warnings: list[str]
    """About the flavor: locks by nodepool position, which compare whichever nodepool is there."""
    clusters: list[ImportCandidateOut]

    @classmethod
    def of(cls, preview: ImportPreview) -> ImportPreviewOut:
        """From an import preview."""
        return cls(
            spec_name=preview.spec_name,
            spec_version=preview.spec_version,
            warnings=list(preview.warnings),
            clusters=[ImportCandidateOut.of(c) for c in preview.candidates],
        )


class ImportedClusterOut(BaseModel):
    """A picked cluster and the day1 MR that links it to the flavor."""

    name: str
    site: str
    mce: str
    path: str
    merge_request: MRDetailOut

    @classmethod
    def of(cls, imported: ImportedCluster) -> ImportedClusterOut:
        """From an opened import MR."""
        ref = imported.cluster
        return cls(
            name=ref.name,
            site=ref.site,
            mce=ref.mce,
            path=str(ref.path),
            merge_request=change_out(RepoKey.DAY1, imported.merge_request),
        )


class ImportFailureOut(BaseModel):
    """A picked cluster, checked like the others, whose MR did not open."""

    name: str
    site: str
    mce: str
    path: str
    code: str
    """The problem code its write failed with (ADR-0004). ``AMBIGUOUS_WRITE``: GitLab did
    not confirm it, so the MR may exist; check before importing it again (ADR-0006).
    ``GIT_UNAVAILABLE``: nothing was sent. ``REVISION_CONFLICT``: the file moved since the
    preview."""
    detail: str

    @classmethod
    def of(cls, failure: ImportFailure) -> ImportFailureOut:
        """From an import MR that did not open."""
        ref = failure.cluster
        return cls(
            name=ref.name,
            site=ref.site,
            mce=ref.mce,
            path=str(ref.path),
            code=from_git_error(failure.error).code.value,
            detail=str(failure.error),
        )


class ImportOut(BaseModel):
    """``POST /specs/{name}/import``: one day1 MR per picked cluster (ADR-0044)."""

    spec_name: str
    spec_version: str
    merge_requests: list[ImportedClusterOut]
    """The MRs that opened, in pick order."""
    failed: list[ImportFailureOut]
    """The clusters whose MR did not open, in pick order."""

    @classmethod
    def of(cls, result: ImportResult) -> ImportOut:
        """From an import's result."""
        return cls(
            spec_name=result.spec_name,
            spec_version=result.spec_version,
            merge_requests=[ImportedClusterOut.of(o) for o in result.opened],
            failed=[ImportFailureOut.of(f) for f in result.failed],
        )
