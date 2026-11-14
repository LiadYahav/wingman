"""The Server Scan area's Claude page: server-scan's skill and its zip (ADR-0048, 3.27.0).

Admins only, as the area (decision 13 of ``docs/ideas/single-pane.md``):
501 with ``SERVER_SCAN_URL`` empty, 404 when server-scan carries no skill,
502 when server-scan fails or refuses the token. Read only: Wingman never
makes a personal token; server-scan makes one only for someone signed in to
it. The contract: ``docs/notes/2026-11-13-server-scan-area-api.md`` §12.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import ServerScan
from wingman_day1.api.v1.server_scan_skill_schemas import SkillOut

router = APIRouter(prefix="/api/day1/server-scan", tags=["server-scan"])
ZIP: dict[int | str, dict[str, object]] = {
    200: {"content": {"application/zip": {}}, "description": "The skill, `<name>/...`"}
}


@router.get("/skill")
async def server_scan_skill(service: ServerScan, user: AdminUser) -> SkillOut:
    """server-scan's Claude Code skill in its shape, with where server-scan is for people."""
    return SkillOut.of(
        await service.skill(), server_scan_url=service.ui_url, token_line=service.token_line
    )


@router.get("/skill/download", response_class=Response, responses=ZIP)
async def download_server_scan_skill(service: ServerScan, user: AdminUser) -> Response:
    """The skill as server-scan zips it, its address written in, for ``~/.claude/skills``."""
    archive = await service.skill_zip()
    return Response(
        content=archive.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive.filename}"',
            "Cache-Control": "no-cache",
        },
    )
