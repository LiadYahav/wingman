"""The in-app docs page names only endpoints, settings and error codes that exist.

The page users read to learn Wingman (`apps/web/app/(app)/docs/page.tsx`) was
written for the legacy services and kept describing `sync-yaml`,
`/cache/stats`, site creation and environment variables the rewrite removed,
because nothing compared it with the code. These tests read the page's
source (and the web README, which states the same facts): what was removed
must not come back, and every SCREAMING_CASE name the page shows must be a
variable a settings class reads or a problem `code` (ADR-0004).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import AliasChoices
from pydantic_settings import BaseSettings

from wingman_core.settings import AuthSettings, GitLabSettings, RuntimeSettings
from wingman_core.web.errors import ErrorCode
from wingman_day1.settings import Day1Settings
from wingman_day2.settings import Day2Settings

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps/web/app/(app)/docs/page.tsx"
README = ROOT / "apps/web/README.md"
SETTINGS: tuple[type[BaseSettings], ...] = (
    GitLabSettings,
    AuthSettings,
    RuntimeSettings,
    Day1Settings,
    Day2Settings,
)

# What the rewrite removed, and the rule that removed it.
REMOVED: dict[str, re.Pattern[str]] = {
    "GET /cache/stats (ADR-0011)": re.compile(r"/cache/stats"),
    "POST /sites (ADR-0018)": re.compile(r"POST\s+(?:/api/day1)?/sites(?![/\w])"),
    "POST /sites/{site}/mces (ADR-0018)": re.compile(r"POST\s+(?:/api/day1)?/sites/\{site\}/mces"),
    "sync-yaml and its Sync button (ADR-0016)": re.compile(r"sync[-_ ]?yaml", re.IGNORECASE),
    "GITLAB_ACCESS_TOKEN (now GITLAB_TOKEN)": re.compile(r"\bGITLAB_ACCESS_TOKEN\b"),
    "the legacy CACHE_* variables (ADR-0011)": re.compile(r"(?<![A-Z0-9_])CACHE_[A-Z0-9_]+"),
    "the legacy *_PATH_TEMPLATE variables (ADR-0020)": re.compile(r"[A-Z0-9_]+_PATH_TEMPLATE\b"),
    "the legacy entry point src.main:app": re.compile(r"src\.main:app"),
    "day2 chart dependencies (always [] now)": re.compile(
        r"\b(?:addon|chart|day2)\s+dependenc(?:y|ies)\b|\bdependency\s+chips?\b|\bdependencies\s*:",
        re.IGNORECASE,
    ),
}
SCREAMING_CASE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
DEFINED_IN_PAGE = re.compile(r"\b(?:const|let|function)\s+([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")


def env_names(cls: type[BaseSettings]) -> set[str]:
    """Every environment name ``cls`` reads, aliases included."""
    prefix = str(cls.model_config.get("env_prefix", "")).upper()
    names: set[str] = set()
    for field_name, field in cls.model_fields.items():
        alias = field.validation_alias
        choices = alias.choices if isinstance(alias, AliasChoices) else [alias or field_name]
        names |= {
            (choice if alias else prefix + choice).upper()
            for choice in choices
            if isinstance(choice, str)
        }
    return names


def removed_mentions(text: str) -> list[str]:
    """``"<what>: <match>"`` for every removed thing ``text`` still mentions."""
    return [
        f"{what}: {match.group(0)!r}"
        for what, pattern in REMOVED.items()
        for match in pattern.finditer(text)
    ]


@pytest.mark.parametrize("doc", [PAGE, README], ids=lambda p: p.name)
def test_docs_do_not_mention_what_was_removed(doc: Path) -> None:
    found = removed_mentions(doc.read_text(encoding="utf-8"))
    assert not found, f"{doc.relative_to(ROOT)} still mentions removed features: {found}"


def test_every_name_the_page_shows_is_a_setting_or_an_error_code() -> None:
    source = PAGE.read_text(encoding="utf-8")
    known = {code.value for code in ErrorCode}
    for cls in SETTINGS:
        known |= env_names(cls)
    named = set(SCREAMING_CASE.findall(source)) - set(DEFINED_IN_PAGE.findall(source))
    unknown = sorted(named - known)
    assert not unknown, f"the docs page names settings or codes nothing defines: {unknown}"


def test_the_guard_bites() -> None:
    """Each pattern matches the thing it forbids, so a typo cannot disable it."""
    samples = [
        "GET /api/day1/cache/stats",
        "POST /sites",
        "POST /api/day1/sites/{site}/mces",
        "the Sync YAML button",
        "GITLAB_ACCESS_TOKEN",
        "CACHE_TTL_SECONDS",
        "DAY1_CLUSTERS_PATH_TEMPLATE",
        "uv run uvicorn src.main:app",
        "dependency chips",
    ]
    assert len(samples) == len(REMOVED)
    for sample, (what, pattern) in zip(samples, REMOVED.items(), strict=True):
        assert pattern.search(sample), what
    assert not removed_mentions(
        "DAY1_CACHE_TTL_SECONDS DEPENDENCY_UNAVAILABLE GET /sites # Install dependencies"
    )
