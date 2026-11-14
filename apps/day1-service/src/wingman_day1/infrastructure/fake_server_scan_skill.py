"""The fake server-scan's Claude Code skill: a folder read and zipped as server-scan does (3.27.0).

``DAY1_FAKE_FLEET=true`` (development only) serves the skill in
``dev/fleet-fixtures/skill/``: a short stand-in for server-scan's
``.claude/skills/server-scan-api``, read the way server-scan's
``backend/app/application/services/skill_bundle.py`` reads its own
(team-redbull/server-scan at 92146d3, ported): ``SKILL.md`` and then
``references/*.md``, the frontmatter's ``key: value`` lines, a short hash as
the version. Its zip writes the address over the ``BASE_URL=`` line and never
fills the token in; a server-scan with auth off (the fake's) gives every
caller an admin's copy, so the token line stays ``AUDITOR_TOKEN``.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from wingman_day1.domain.server_scan_skill import (
    DEFAULT_SKILL_NAME,
    SKILL_NAME,
    Skill,
    SkillFile,
    SkillZip,
)

SKILL_DIR: Final = Path("dev") / "fleet-fixtures" / "skill"
_BASE_URL_LINE: Final = re.compile(r"^BASE_URL=.*$", re.MULTILINE)


def default_skill_dir() -> Path:
    """``dev/fleet-fixtures/skill/`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / SKILL_DIR
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise FileNotFoundError(f"{SKILL_DIR}/SKILL.md not found above this file")


def _frontmatter(text: str) -> dict[str, str]:
    """The ``key: value`` lines between the opening ``---`` pair, as server-scan reads them."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    found: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            found[key.strip()] = value.strip()
    return found


def load_skill(folder: Path) -> Skill:
    """The skill in ``folder``: its files, frontmatter, version and newest change."""
    paths = [folder / "SKILL.md", *sorted((folder / "references").glob("*.md"))]
    files: list[SkillFile] = []
    digest = hashlib.sha256()
    newest = 0.0
    for path in paths:
        content = path.read_text(encoding="utf-8")
        relative = path.relative_to(folder).as_posix()
        files.append(SkillFile(path=relative, content=content))
        digest.update(relative.encode() + b"\0" + content.encode() + b"\0")
        newest = max(newest, path.stat().st_mtime)
    meta = _frontmatter(files[0].content)
    name = meta.get("name", "")
    return Skill(
        name=name if SKILL_NAME.fullmatch(name) else DEFAULT_SKILL_NAME,
        description=meta.get("description", ""),
        when_to_use=meta.get("when_to_use", ""),
        allowed_tools=meta.get("allowed-tools", ""),
        version=digest.hexdigest()[:12],
        updated_at=datetime.fromtimestamp(newest, tz=UTC),
        files=tuple(files),
    )


def zip_skill(skill: Skill, base_url: str) -> SkillZip:
    """``skill`` as ``<name>/...``, ``base_url`` written over ``SKILL.md``'s ``BASE_URL=`` line."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in skill.files:
            content = file.content
            if file.path == "SKILL.md":
                content = _BASE_URL_LINE.sub(lambda _: f"BASE_URL={base_url}", content, count=1)
            archive.writestr(f"{skill.name}/{file.path}", content)
    return SkillZip(name=skill.name, content=out.getvalue())
