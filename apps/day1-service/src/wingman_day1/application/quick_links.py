"""Quick Links: the launcher page's cards (ADR-0052).

The cards come from what Wingman knows (the hub it runs on, every MCE folder
of the day1 repo) and from the team's links file. Wingman only lists the
links: it never calls them (the ADR's 2026-11-13 amendment).

A launcher must work when something it links to does not, so nothing here
fails the page: GitLab down drops the MCE cards with a problem saying so,
and a bad links file drops what is bad with a problem per mistake.
"""

from __future__ import annotations

from wingman_core.domain.errors import GitUnavailableError, PermissionDeniedError
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.domain.quick_links import (
    MISSING_LINKS_FILE,
    Board,
    GeneratedLinks,
    LinksFile,
    LinksFileUnreadableError,
    MceInfo,
    generated_sections,
    parse_links_file,
    unreadable_links_file,
)
from wingman_day1.ports import LinksFileSource


class QuickLinksService:
    """The page's sections and cards."""

    def __init__(
        self,
        sites: SiteCatalog,
        *,
        generated: GeneratedLinks,
        links: LinksFileSource | None = None,
    ) -> None:
        """Build the page from ``sites`` and the links file (without ``links``: no team links)."""
        self._sites = sites
        self._generated = generated
        self._links = links

    async def board(self) -> Board:
        """Every section and card, and what could not be shown."""
        links_file = await self._links_file()
        problems: list[str] = []
        try:
            views = await self._sites.mces()
        except (GitUnavailableError, PermissionDeniedError) as exc:
            views = []
            problems.append(f"The day1 repo could not be read, so its MCEs are missing: {exc}")
        mces = [MceInfo(v.site, v.name, v.hub_version, v.cluster_count) for v in views]
        generated, generation_problems = generated_sections(
            self._generated, mces, links_file.clusters
        )
        return Board(
            sections=(*generated, *links_file.sections),
            problems=(*problems, *generation_problems),
            links_file=links_file,
            links_path=self._links.path if self._links is not None else "",
        )

    async def _links_file(self) -> LinksFile:
        if self._links is None:
            return MISSING_LINKS_FILE
        try:
            text = await self._links.read()
        except LinksFileUnreadableError as exc:
            return unreadable_links_file(str(exc))
        return MISSING_LINKS_FILE if text is None else parse_links_file(text)
