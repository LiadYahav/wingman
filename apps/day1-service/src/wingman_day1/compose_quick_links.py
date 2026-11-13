"""Quick Links' part of the composition root (ADR-0052).

``main`` builds the app; this builds the launcher's use case: the generated
cards from the settings' URL templates, and the links file (with the fake
fleet and no file, the demo's). Kept apart so ``main`` stays one screen of
wiring per system.
"""

from __future__ import annotations

from wingman_day1.application.quick_links import QuickLinksService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.domain.quick_links import GeneratedLinks, UrlTemplates
from wingman_day1.infrastructure.links_file import FileLinksSource
from wingman_day1.settings import Day1Settings


def links_file(settings: Day1Settings) -> FileLinksSource:
    """The links file; with the fake fleet and no file there, the demo's (ADR-0052)."""
    if settings.day1_fake_fleet and not settings.quick_links_file.exists():
        from wingman_day1.infrastructure.fake_quick_links import default_demo_links_file

        return FileLinksSource(default_demo_links_file())
    return FileLinksSource(settings.quick_links_file)


def quick_links_service(settings: Day1Settings, sites: SiteCatalog) -> QuickLinksService:
    """The launcher: the hub's and every MCE's cards, then the links file's sections."""
    return QuickLinksService(
        sites,
        generated=GeneratedLinks(
            hub=settings.quick_links_hub_name or None,
            hub_domain=settings.quick_links_hub_base_domain,
            domain=settings.quick_links_mce_domain,
            templates=UrlTemplates(
                argocd=settings.quick_links_argocd_url_template,
                console=settings.quick_links_console_url_template,
            ),
        ),
        links=links_file(settings),
    )
