"""``/api/day1/specs``: cluster specs, the shared template and its form schema."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastapi.responses import PlainTextResponse

from wingman_core.domain.errors import AmbiguousWriteError
from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_core.web.errors import AppError, from_git_error
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.schemas import (
    CommitOut,
    ImportFailureOut,
    ImportIn,
    ImportOut,
    ImportPreviewIn,
    ImportPreviewOut,
    MRDetailOut,
    SpecClusterOut,
    SpecDriftOut,
    SpecOut,
    change_out,
)
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.imports import ImportPick, ImportResult
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec

router = APIRouter(prefix="/api/day1/specs", tags=["specs"])

Name = Annotated[str, Path(min_length=1, max_length=63)]
LastCommit = Annotated[str | None, Query(min_length=7, max_length=64)]


@router.get("")
async def list_specs(context: Context, user: CurrentUser) -> list[SpecOut]:
    """Every spec; one whose file does not parse carries ``load_error`` instead of vanishing."""
    return [SpecOut.of(entry) for entry in await context.specs.entries()]


@router.get("/template")
async def shared_template(context: Context, user: CurrentUser) -> str:
    """The shared ``cluster-template.j2`` (a JSON string, as before)."""
    return await context.specs.template()


@router.get("/template/schema")
async def template_schema(
    context: Context, user: CurrentUser, include_reserved: bool = False
) -> list[dict[str, Any]]:
    """The template's inputs as a form schema; reserved inputs only with ``include_reserved``."""
    return [f.to_dict() for f in await context.specs.schema(include_reserved=include_reserved)]


@router.get("/{name}/history")
async def spec_history(name: Name, context: Context, user: CurrentUser) -> list[CommitOut]:
    """Commits that changed the spec's file."""
    return [CommitOut.of(c) for c in await context.specs.history(name)]


@router.get("/{name}/at/{sha}", response_class=PlainTextResponse)
async def spec_at(
    name: Name,
    sha: Annotated[str, Path(min_length=7, max_length=64, pattern=r"^[0-9a-f]+$")],
    context: Context,
    user: CurrentUser,
) -> str:
    """The spec file's text at a commit."""
    return await context.specs.at(name, sha)


@router.get("/{name}/clusters")
async def spec_clusters(name: Name, context: Context, user: CurrentUser) -> list[SpecClusterOut]:
    """Clusters created from the spec, with their drift."""
    return [
        SpecClusterOut(
            name=d.ref.name,
            site=d.ref.site,
            mce=d.ref.mce,
            state=d.state.value,
            is_drifted=d.is_drifted,
            error=d.error,
        )
        for d in await context.drift.for_spec(name)
    ]


@router.get("/{name}/drift")
async def spec_drift(name: Name, context: Context, user: CurrentUser) -> list[SpecDriftOut]:
    """Drift of every cluster created from the spec."""
    return [
        SpecDriftOut(
            cluster=d.ref.name,
            site=d.ref.site,
            mce=d.ref.mce,
            state=d.state.value,
            is_drifted=d.is_drifted,
            spec_version=d.spec_version,
            error=d.error,
        )
        for d in await context.drift.for_spec(name)
    ]


@router.post("/{name}/import/preview")
async def import_preview(
    name: Name, body: ImportPreviewIn, context: Context, user: AdminUser
) -> ImportPreviewOut:
    """Each picked cluster against the flavor: whether it can join it, and what would drift."""
    refs = [await context.clusters.locate(c.name, site=c.site, mce=c.mce) for c in body.clusters]
    return ImportPreviewOut.of(await context.imports.preview(name, refs))


@router.post("/{name}/import", status_code=201)
async def import_clusters(
    name: Name, body: ImportIn, context: Context, user: AdminUser
) -> ImportOut:
    """Open one day1 MR per picked cluster that links its file to the flavor, and nothing else.

    Every pick is checked first; one refused (422) or moved (409) opens none.
    201 when at least one MR opened, with the clusters whose MR did not in
    ``failed``. When none opened, the answer is the problem of the failure
    (ADR-0044).
    """
    picks = [
        ImportPick(ClusterRef(c.site, c.mce, c.name), c.last_commit_id, relink=c.relink)
        for c in body.clusters
    ]
    result = await context.imports.import_clusters(
        name, picks, spec_version=body.spec_version, user=user
    )
    if not result.opened:
        raise _none_opened(result)
    return ImportOut.of(result)


def _none_opened(result: ImportResult) -> AppError:
    """No import MR opened: an unconfirmed write's problem first, else the first failure's.

    An ``AMBIGUOUS_WRITE`` leads because it is the one a person must check in
    GitLab before importing again (ADR-0006); every cluster's failure is in
    ``details.problems`` and, as ``POST`` returns them, ``details.failed``.
    """
    failed = result.failed
    lead = next((f for f in failed if isinstance(f.error, AmbiguousWriteError)), failed[0])
    error = from_git_error(lead.error)
    lines = [f"{f.cluster.name}: {f.error}" for f in failed]
    detail = (
        lines[0]
        if len(lines) == 1
        else f"GitLab confirmed none of the {len(lines)} import merge requests"
    )
    return type(error)(
        detail,
        details={
            "problems": lines,
            "failed": [ImportFailureOut.of(f).model_dump() for f in failed],
        },
    )


@router.get("/{name}")
async def get_spec(name: Name, context: Context, user: CurrentUser) -> SpecOut:
    """One spec, with the shared template filled in."""
    return SpecOut.of(await context.specs.entry(name))


@router.post("", status_code=201)
async def create_spec(spec: ClusterSpec, context: Context, user: AdminUser) -> MRDetailOut:
    """Open the MR that adds the spec."""
    result = await context.specs.create(spec, user=user)
    return change_out(RepoKey.SPECS, result.merge_request)


@router.put("/{name}")
async def update_spec(
    name: Name,
    spec: ClusterSpec,
    context: Context,
    user: AdminUser,
    last_commit_id: LastCommit = None,
) -> MRDetailOut:
    """Open the MR that replaces the spec (same name)."""
    result = await context.specs.update(name, spec, user=user, last_commit_id=last_commit_id)
    return change_out(RepoKey.SPECS, result.merge_request)


@router.delete("/{name}")
async def delete_spec(
    name: Name, context: Context, user: AdminUser, last_commit_id: LastCommit = None
) -> MRDetailOut:
    """Open the MR that removes the spec."""
    result = await context.specs.delete(name, user=user, last_commit_id=last_commit_id)
    return change_out(RepoKey.SPECS, result.merge_request)
