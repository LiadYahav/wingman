"""Quick Links' response bodies (docs/notes/2026-11-12-quick-links-api.md, ADR-0052).

Apart from ``schemas.py`` so the launcher's shapes read as one contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from wingman_day1.domain.quick_links import Board, Card, CardLink, Section


class CardLinkOut(BaseModel):
    """One link of a card: a generated card's are labelled, a file card's one is not."""

    label: str | None
    url: str

    @classmethod
    def of(cls, link: CardLink) -> CardLinkOut:
        """From the domain."""
        return cls(label=link.label, url=link.url)


class CardOut(BaseModel):
    """One card; ``links[0]`` is its own link (the title opens it)."""

    id: str
    name: str
    description: str | None
    icon: str
    links: list[CardLinkOut]

    @classmethod
    def of(cls, card: Card) -> CardOut:
        """From the domain."""
        return cls(
            id=card.id,
            name=card.name,
            description=card.description,
            icon=card.icon,
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
