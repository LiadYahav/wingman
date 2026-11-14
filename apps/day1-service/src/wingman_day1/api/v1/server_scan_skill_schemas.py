"""The Claude page's response body (docs/notes/2026-11-13-server-scan-area-api.md §12).

server-scan's skill is the domain's model of its own shape
(``domain/server_scan_skill.py``), sent as it is, so server-scan's TypeScript
applies (ADR-0048, decision 18 of the single-pane plan). Two additions: where
server-scan is for people, which its page takes from its own origin, and
the token line Wingman's copy of the zip names.
"""

from __future__ import annotations

from wingman_day1.domain.server_scan_skill import Skill


class SkillOut(Skill):
    """``GET /api/day1/server-scan/skill``: server-scan's skill, typed.

    Plus ``server_scan_url``, the address written into the zip, the MCP
    command's and the token page's (``SERVER_SCAN_UI_URL``, else
    ``SERVER_SCAN_URL``), and ``token_line``, the placeholder the zip's
    ``SKILL.md`` names (``VIEWER_TOKEN`` or ``AUDITOR_TOKEN``).
    """

    server_scan_url: str
    token_line: str

    @classmethod
    def of(cls, skill: Skill, *, server_scan_url: str, token_line: str) -> SkillOut:
        """The skill with this deployment's address and token line."""
        return cls(**dict(skill), server_scan_url=server_scan_url, token_line=token_line)
