"""server-scan's reads for the Claude page: its skill and the skill's zip (ADR-0048, 3.27.0).

``GET /api/v1/skill`` read strictly into the domain's ``Skill``, and
``GET /api/v1/skill/download?base_url=``, the zip server-scan builds with
that address written into ``SKILL.md``'s ``BASE_URL=`` line, passed on as it
is once it reads as a zip. Both go with the viewer token (any caller server-scan
resolves may read them). server-scan carrying no skill is a 404:
``ServerScanSkillMissingError``.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Final

import httpx

from wingman_day1.domain.errors import ServerScanSkillMissingError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_skill import DEFAULT_SKILL_NAME, Skill, SkillZip
from wingman_day1.infrastructure.server_scan_record import check, fetch, parsed, problem_detail

SKILL_PATH: Final = "/api/v1/skill"
DOWNLOAD_PATH: Final = "/api/v1/skill/download"
MISSING: Final = "server-scan carries no Claude Code skill"
_FILENAME: Final = re.compile(r'filename="([a-z0-9][a-z0-9-]{0,63})\.zip"')
"""server-scan's ``Content-Disposition``: the skill's name, by its own naming rule."""


async def read_skill(client: httpx.AsyncClient) -> Skill:
    """The skill as server-scan holds it now; none is ``ServerScanSkillMissingError``."""
    what = "reading the Claude skill"
    response = await fetch(client, SKILL_PATH, what=what)
    _found(response)
    check(response, what=what)
    return parsed(Skill, response, "a malformed Claude skill")


async def read_skill_zip(client: httpx.AsyncClient, base_url: str) -> SkillZip:
    """The skill's zip with ``base_url`` written in; server-scan refusing the address names it."""
    what = "downloading the Claude skill"
    response = await fetch(client, DOWNLOAD_PATH, what=what, params={"base_url": base_url})
    _found(response)
    if response.status_code == 422:
        raise ServerScanUnavailableError(
            f"server-scan refused the address Wingman writes into the skill ({base_url}): "
            "check SERVER_SCAN_UI_URL"
        )
    check(response, what=what)
    if not zipfile.is_zipfile(io.BytesIO(response.content)):
        raise ServerScanUnavailableError("server-scan returned a Claude skill that is not a zip")
    match = _FILENAME.search(response.headers.get("content-disposition", ""))
    return SkillZip(name=match.group(1) if match else DEFAULT_SKILL_NAME, content=response.content)


def _found(response: httpx.Response) -> None:
    """A 404 is ``ServerScanSkillMissingError``, in server-scan's own words when it sent them."""
    if response.status_code == 404:
        raise ServerScanSkillMissingError(problem_detail(response) or MISSING)
