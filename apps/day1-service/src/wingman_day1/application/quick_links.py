"""Quick Links: the launcher page's cards and their status (ADR-0052).

The cards come from what Wingman knows (the hub it runs on, every MCE folder
of the day1 repo) and from the team's links file. The status comes from
checking each link and, for an ArgoCD with a token, counting its
applications; both are the ports' and are cached below this service, so
every viewer shares one check per link.

A launcher must work when something it links to does not, so nothing here
fails the page: GitLab down drops the MCE cards with a problem saying so,
a bad links file drops what is bad with a problem per mistake, and a check
that fails is a dot.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from wingman_core.domain.errors import GitUnavailableError, PermissionDeniedError
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.domain.quick_links import (
    MISSING_LINKS_FILE,
    Board,
    Card,
    GeneratedLinks,
    LinksFile,
    LinksFileUnreadableError,
    MceInfo,
    Section,
    StatusBoard,
    generated_sections,
    parse_links_file,
    unreadable_links_file,
    without_pings,
)
from wingman_day1.ports import ArgoCdApi, LinkProbe, LinksFileSource


class QuickLinksService:
    """The page's sections, cards and dots."""

    def __init__(
        self,
        sites: SiteCatalog,
        *,
        generated: GeneratedLinks,
        links: LinksFileSource | None = None,
        probe: LinkProbe | None = None,
        argocd: ArgoCdApi | None = None,
    ) -> None:
        """Build the page from ``sites`` and the links file.

        Without ``links`` there are no team links; without ``probe`` no dots;
        without ``argocd`` (or a token for an instance) no counts.
        """
        self._sites = sites
        self._generated = generated
        self._links = links
        self._probe = probe
        self._argocd = argocd

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
        sections = [self._finished(s) for s in (*generated, *links_file.sections)]
        return Board(
            sections=tuple(sections),
            problems=(*problems, *generation_problems),
            links_file=links_file,
            links_path=self._links.path if self._links is not None else "",
        )

    async def status(self) -> StatusBoard:
        """Every dot's check and every ArgoCD's counts (cached by the ports' wrappers)."""
        board = await self.board()
        probe, argocd = self._probe, self._argocd
        checks = (
            await asyncio.gather(*(probe.check(url) for url in board.pings()))
            if probe is not None
            else []
        )
        readings = (
            await asyncio.gather(
                *(argocd.application_counts(t.instance, t.url) for t in board.argocd_targets())
            )
            if argocd is not None
            else []
        )
        return StatusBoard(checks=tuple(checks), argocd=tuple(readings))

    async def _links_file(self) -> LinksFile:
        if self._links is None:
            return MISSING_LINKS_FILE
        try:
            text = await self._links.read()
        except LinksFileUnreadableError as exc:
            return unreadable_links_file(str(exc))
        return MISSING_LINKS_FILE if text is None else parse_links_file(text)

    def _finished(self, section: Section) -> Section:
        """No dots without a probe; counts only for an ArgoCD that has a token."""
        cards = tuple(self._with_token(card) for card in section.cards)
        section = replace(section, cards=cards)
        return section if self._probe is not None else without_pings(section)

    def _with_token(self, card: Card) -> Card:
        if card.argocd is None:
            return card
        if self._argocd is not None and self._argocd.has_token(card.argocd.instance):
            return card
        return replace(card, argocd=None)
