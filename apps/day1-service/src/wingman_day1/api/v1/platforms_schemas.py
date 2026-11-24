"""The Infrastructure sidebar's systems, as the web reads them (ADR-0066, ADR-0067)."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from wingman_day1.domain.platforms import Platform, PlatformId


class PlatformOut(BaseModel):
    """One system: its name (the link's label) and its own UI, opened in a new tab."""

    id: PlatformId
    name: str
    url: str

    @classmethod
    def of(cls, platform: Platform) -> PlatformOut:
        """From the domain."""
        return cls(id=platform.id, name=platform.name, url=platform.url)


class PlatformsOut(BaseModel):
    """The configured systems whose UI day1 knows, in the sidebar's order; none: ``[]``."""

    platforms: list[PlatformOut]

    @classmethod
    def of(cls, platforms: Iterable[Platform]) -> PlatformsOut:
        """From the domain."""
        return cls(platforms=[PlatformOut.of(platform) for platform in platforms])
