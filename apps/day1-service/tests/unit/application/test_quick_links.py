"""QuickLinksService: the page never fails because something it links to does (ADR-0052)."""

from __future__ import annotations

from typing import Any

from wingman_core.domain.errors import GitUnavailableError
from wingman_day1.application.quick_links import QuickLinksService
from wingman_day1.application.sites import MceView
from wingman_day1.domain.names import describe_mce
from wingman_day1.domain.quick_links import (
    GeneratedLinks,
    LinksFileState,
    LinksFileUnreadableError,
)
from wingman_day1.infrastructure.fake_quick_links import FakeArgoCd, FakeLinkProbe, counts

LINKS = """
sections:
  - name: Tools
    links:
      - {name: ArgoCD Main, url: "https://argocd.example.internal", argocd: main}
      - {name: Wiki, url: "https://wiki.example.internal", ping: "https://wiki.example.internal/health"}
      - {name: Same ping, url: "https://wiki.example.internal/x", ping: "https://wiki.example.internal/health"}
clusters:
  hub-prod: {console: "https://console.hub.example.internal"}
"""
GENERATED = GeneratedLinks(hub="hub-prod", hub_domain="example.internal", domain="example.internal")


class Sites:
    """A SiteCatalog's ``mces``: one MCE, or GitLab down."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down

    async def mces(self) -> list[MceView]:
        if self.down:
            raise GitUnavailableError("GitLab answered 503")
        mce = "ocp4-prod-mce-site1-a"
        return [MceView("site1", describe_mce(mce, site="site1"), None, "4.18.22", 2, (), ())]


class Links:
    def __init__(self, text: str | None = LINKS, *, unreadable: bool = False) -> None:
        self.text = text
        self.unreadable = unreadable

    @property
    def path(self) -> str:
        return "/etc/wingman/quick-links/links.yaml"

    async def read(self) -> str | None:
        if self.unreadable:
            raise LinksFileUnreadableError("Permission denied")
        return self.text


def service(**kw: Any) -> QuickLinksService:
    sites = kw.pop("sites", Sites())
    return QuickLinksService(sites, generated=GENERATED, **kw)


async def test_generated_sections_come_first_then_the_file_s() -> None:
    board = await service(links=Links(), probe=FakeLinkProbe()).board()
    assert [s.id for s in board.sections] == ["hub", "site:site1", "file:tools"]
    hub = board.sections[0].cards[0]
    assert hub.links[1].url == "https://console.hub.example.internal"  # the file's address
    assert board.problems == ()
    assert board.links_file.state is LinksFileState.LOADED
    assert board.links_path == "/etc/wingman/quick-links/links.yaml"


async def test_gitlab_down_drops_the_mces_with_a_problem_and_keeps_the_rest() -> None:
    board = await service(sites=Sites(down=True), links=Links()).board()
    assert [s.id for s in board.sections] == ["hub", "file:tools"]
    assert board.problems == (
        "The day1 repo could not be read, so its MCEs are missing: GitLab answered 503",
    )


async def test_an_unreadable_or_missing_file_gives_only_the_generated_cards() -> None:
    unreadable = await service(links=Links(unreadable=True)).board()
    assert [s.id for s in unreadable.sections] == ["hub", "site:site1"]
    assert unreadable.links_file.state is LinksFileState.INVALID
    assert unreadable.links_file.problems == ("the links file cannot be read: Permission denied",)
    missing = await service(links=Links(None)).board()
    assert missing.links_file.state is LinksFileState.MISSING
    assert missing.links_file.problems == ()
    none = await service().board()
    assert none.links_file.state is LinksFileState.MISSING
    assert none.links_path == ""


async def test_without_a_probe_there_are_no_dots() -> None:
    board = await service(links=Links()).board()
    assert board.pings() == []
    status = await service(links=Links()).status()
    assert status.checks == ()


async def test_counts_are_offered_only_for_an_argocd_with_a_token() -> None:
    argocd = FakeArgoCd({"hub-prod": counts(synced=3, healthy=3), "main": "ArgoCD answered 503"})
    board = await service(links=Links(), argocd=argocd).board()
    by_id = {c.id: c for s in board.sections for c in s.cards}
    assert by_id["hub:hub-prod"].argocd is not None
    assert by_id["cluster:ocp4-prod-mce-site1-a"].argocd is None  # no token
    assert by_id["file:tools:argocd-main"].argocd is not None
    no_argocd = await service(links=Links()).board()
    assert all(c.argocd is None for s in no_argocd.sections for c in s.cards)


async def test_status_checks_each_ping_once_and_reads_each_argocd() -> None:
    probe = FakeLinkProbe()
    argocd = FakeArgoCd({"hub-prod": counts(synced=3, healthy=3), "main": "ArgoCD answered 503"})
    status = await service(links=Links(), probe=probe, argocd=argocd).status()
    assert sorted(probe.checked) == sorted(set(probe.checked))
    assert "https://wiki.example.internal/health" in probe.checked
    assert len(probe.checked) == 2 + 2 + 2  # hub, the MCE, then ArgoCD Main and the wiki's ping
    assert {r.instance: r.error for r in status.argocd} == {
        "hub-prod": None,
        "main": "ArgoCD answered 503",
    }
    assert [i for i, _ in argocd.reads] == ["hub-prod", "main"]
