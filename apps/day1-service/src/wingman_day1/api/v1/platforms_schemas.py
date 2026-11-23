"""The top bar's systems, as the web reads them (ADR-0047, ADR-0048; 2026-11-23)."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.domain.platforms import Platform, PlatformId, Platforms


class PlatformOut(BaseModel):
    """One system: its own UI, and whether Wingman's area for it is on."""

    id: PlatformId
    name: str
    url: str
    area: bool

    @classmethod
    def of(cls, platform: Platform) -> PlatformOut:
        """From the domain."""
        return cls(id=platform.id, name=platform.name, url=platform.url, area=platform.area)


class PlatformsOut(BaseModel):
    """The configured systems whose UI day1 knows, in the top bar's order; none: ``[]``."""

    platforms: list[PlatformOut]

    @classmethod
    def of(cls, platforms: Platforms) -> PlatformsOut:
        """From the domain."""
        return cls(platforms=[PlatformOut.of(platform) for platform in platforms.links()])
