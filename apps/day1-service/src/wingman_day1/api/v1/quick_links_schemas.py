"""Quick Links' response bodies (docs/notes/2026-11-12-quick-links-api.md, ADR-0052).

Apart from ``schemas.py`` so the launcher's shapes read as one contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from wingman_day1.domain.quick_links import (
    AppCounts,
    ArgoCdReading,
    Board,
    Card,
    CardLink,
    LinkReading,
    Section,
    StatusBoard,
)


class CardLinkOut(BaseModel):
    """One link of a card; ``ping`` is the URL its dot is checked at (``null``: no dot)."""

    label: str | None
    url: str
    ping: str | None

    @classmethod
    def of(cls, link: CardLink) -> CardLinkOut:
        """From the domain."""
        return cls(label=link.label, url=link.url, ping=link.ping)


class CardOut(BaseModel):
    """One card; ``links[0]`` is its own link, and ``argocd`` names the counts it shows."""

    id: str
    name: str
    description: str | None
    icon: str
    argocd: str | None
    links: list[CardLinkOut]

    @classmethod
    def of(cls, card: Card) -> CardOut:
        """From the domain; the ArgoCD's URL and token stay in day1."""
        return cls(
            id=card.id,
            name=card.name,
            description=card.description,
            icon=card.icon,
            argocd=card.argocd.instance if card.argocd is not None else None,
            links=[CardLinkOut.of(link) for link in card.links],
        )


class SectionOut(BaseModel):
    """A heading and its cards."""

    id: str
    name: str
    description: str | None
    columns: int
    generated: bool
    cards: list[CardOut]

    @classmethod
    def of(cls, section: Section) -> SectionOut:
        """From the domain."""
        return cls(
            id=section.id,
            name=section.name,
            description=section.description,
            columns=section.columns,
            generated=section.generated,
            cards=[CardOut.of(card) for card in section.cards],
        )


class LinksFileOut(BaseModel):
    """Whether the links file was read, and every problem in it."""

    path: str
    state: Literal["loaded", "missing", "invalid"]
    problems: list[str]


class QuickLinksOut(BaseModel):
    """``GET /api/day1/quick-links``."""

    sections: list[SectionOut]
    problems: list[str]
    links_file: LinksFileOut

    @classmethod
    def of(cls, board: Board) -> QuickLinksOut:
        """From the domain."""
        return cls(
            sections=[SectionOut.of(section) for section in board.sections],
            problems=list(board.problems),
            links_file=LinksFileOut(
                path=board.links_path,
                state=board.links_file.state.value,
                problems=list(board.links_file.problems),
            ),
        )


class LinkCheckOut(BaseModel):
    """One URL's dot."""

    url: str
    state: Literal["up", "down", "unknown"]
    reason: str
    http_status: int | None
    latency_ms: int | None
    checked_at: datetime

    @classmethod
    def of(cls, reading: LinkReading) -> LinkCheckOut:
        """From the domain."""
        return cls(
            url=reading.url,
            state=reading.state.value,
            reason=reading.reason,
            http_status=reading.http_status,
            latency_ms=reading.latency_ms,
            checked_at=reading.checked_at,
        )


class SyncCountsOut(BaseModel):
    """Applications by sync status."""

    synced: int
    out_of_sync: int
    unknown: int


class HealthCountsOut(BaseModel):
    """Applications by health."""

    healthy: int
    progressing: int
    degraded: int
    missing: int
    suspended: int
    unknown: int


class AppCountsOut(BaseModel):
    """An ArgoCD's applications, counted."""

    applications: int
    sync: SyncCountsOut
    health: HealthCountsOut

    @classmethod
    def of(cls, counts: AppCounts) -> AppCountsOut:
        """From the domain."""
        sync, health = counts.sync, counts.health
        return cls(
            applications=counts.applications,
            sync=SyncCountsOut(
                synced=sync.synced, out_of_sync=sync.out_of_sync, unknown=sync.unknown
            ),
            health=HealthCountsOut(
                healthy=health.healthy,
                progressing=health.progressing,
                degraded=health.degraded,
                missing=health.missing,
                suspended=health.suspended,
                unknown=health.unknown,
            ),
        )


class ArgoCdCountsOut(BaseModel):
    """One ArgoCD's counts, or why they could not be read."""

    instance: str
    counts: AppCountsOut | None
    error: str | None
    checked_at: datetime

    @classmethod
    def of(cls, reading: ArgoCdReading) -> ArgoCdCountsOut:
        """From the domain."""
        return cls(
            instance=reading.instance,
            counts=AppCountsOut.of(reading.counts) if reading.counts is not None else None,
            error=reading.error,
            checked_at=reading.checked_at,
        )


class QuickLinksStatusOut(BaseModel):
    """``GET /api/day1/quick-links/status``."""

    checks: list[LinkCheckOut]
    argocd: list[ArgoCdCountsOut]

    @classmethod
    def of(cls, status: StatusBoard) -> QuickLinksStatusOut:
        """From the domain."""
        return cls(
            checks=[LinkCheckOut.of(reading) for reading in status.checks],
            argocd=[ArgoCdCountsOut.of(reading) for reading in status.argocd],
        )
