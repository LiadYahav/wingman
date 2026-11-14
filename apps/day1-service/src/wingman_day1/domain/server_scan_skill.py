"""The Claude Code skill server-scan serves, as its Claude page shows it (ADR-0048, 3.27.0).

server-scan's ``GET /api/v1/skill`` (its ``SkillResponse``,
``backend/app/api/v1/skill_schemas.py``, team-redbull/server-scan at
92146d3), typed and in its shape, so the web's port of server-scan's page
reads day1's answer as it is. server-scan reads the skill from its own disk
on every call (its ADR-0052), so Wingman never keeps a copy: a copy goes
stale the first time the skill is edited. The zip is its
``GET /api/v1/skill/download``, passed on as server-scan built it
(docs/notes/2026-11-13-server-scan-area-api.md §12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import BaseModel

from wingman_day1.domain.server_scan_hardware import SHAPE

SKILL_NAME: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
"""server-scan's rule for a skill's name, also its folder and its zip's name (``_NAME``)."""
DEFAULT_SKILL_NAME: Final = "server-scan-api"
"""The name server-scan falls back to when the frontmatter's is missing or not a name."""
VIEWER_TOKEN_LINE: Final = "VIEWER_TOKEN"  # noqa: S105 - a line's name, not a token
AUDITOR_TOKEN_LINE: Final = "AUDITOR_TOKEN"  # noqa: S105 - a line's name, not a token
"""The two names server-scan gives ``SKILL.md``'s token line (a viewer's copy, anyone else's)."""


class SkillFile(BaseModel):
    """One file of the skill: ``SKILL.md`` or a ``references/*.md``."""

    model_config = SHAPE

    path: str
    content: str


class Skill(BaseModel):
    """The skill as server-scan holds it now; ``version`` changes whenever a file does."""

    model_config = SHAPE

    name: str
    description: str
    when_to_use: str
    allowed_tools: str
    version: str
    updated_at: datetime
    files: tuple[SkillFile, ...]
    """``SKILL.md`` first, then the references by path."""


@dataclass(frozen=True, slots=True)
class SkillZip:
    """The skill as server-scan zipped it: ``<name>/...``, ready for ``~/.claude/skills``."""

    name: str
    """The skill's name (``SKILL_NAME``), so the file is ``<name>.zip``."""
    content: bytes

    @property
    def filename(self) -> str:
        """What the browser saves it as, as server-scan names it."""
        return f"{self.name}.zip"


def token_line(*, viewer_token: bool) -> str:
    """The token line the downloaded ``SKILL.md`` names, by server-scan's own rule.

    server-scan renames ``AUDITOR_TOKEN`` to ``VIEWER_TOKEN`` in a viewer's
    copy. Wingman is the caller whose copy it is: with its viewer token, a
    viewer; with no token, a server-scan with auth off, where every caller
    is an admin.
    """
    return VIEWER_TOKEN_LINE if viewer_token else AUDITOR_TOKEN_LINE
