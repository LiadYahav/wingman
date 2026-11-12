"""Quick Links' cache wrappers, links file and fakes (ADR-0052)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.quick_links import (
    ArgoCdReading,
    LinkReading,
    LinksFileState,
    LinksFileUnreadableError,
    LinkState,
    parse_links_file,
)
from wingman_day1.infrastructure.cached_quick_links import CachedArgoCd, CachedLinkProbe
from wingman_day1.infrastructure.fake_quick_links import (
    CHECKS_FILE,
    DEMO_LINKS_FILE,
    CheckRule,
    FakeArgoCd,
    FakeLinkProbe,
    counts,
    fleet_fixture,
    load_fake_quick_links,
)
from wingman_day1.infrastructure.links_file import FileLinksSource

URL = "https://argocd.example.internal"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SlowProbe:
    """Counts checks; each takes a moment, so concurrent reads overlap."""

    def __init__(self) -> None:
        self.calls = 0
        self.inner = FakeLinkProbe()

    async def check(self, url: str) -> LinkReading:
        self.calls += 1
        await asyncio.sleep(0.01)
        return await self.inner.check(url)


async def test_a_check_is_kept_for_the_ttl_and_shared_by_concurrent_reads() -> None:
    clock = Clock()
    inner = SlowProbe()
    probe = CachedLinkProbe(inner, TtlCache(clock=clock), ttl=60)
    await asyncio.gather(*(probe.check(URL) for _ in range(5)))
    assert inner.calls == 1
    clock.now = 59
    await probe.check(URL)
    assert inner.calls == 1


async def test_an_old_check_is_answered_while_one_refresh_runs() -> None:
    clock = Clock()
    inner = SlowProbe()
    probe = CachedLinkProbe(inner, TtlCache(clock=clock), ttl=60)
    first = await probe.check(URL)
    clock.now = 90  # past the TTL, within the stale window
    again = await probe.check(URL)
    assert again is first
    await asyncio.sleep(0.05)
    assert inner.calls == 2  # the background refresh
    clock.now = 400  # past both: a read waits for a new check
    await probe.check(URL)
    assert inner.calls == 3


async def test_a_down_link_is_kept_like_an_answer() -> None:
    clock = Clock()
    inner = FakeLinkProbe([CheckRule("", LinkState.DOWN, "no answer within 3 s", None, None)])
    probe = CachedLinkProbe(inner, TtlCache(clock=clock), ttl=60)
    await probe.check(URL)
    await probe.check(URL)
    assert inner.checked == [URL]


async def test_argocd_counts_are_kept_per_instance_and_url() -> None:
    clock = Clock()
    inner = FakeArgoCd({"hub": counts(synced=1, healthy=1), "main": "ArgoCD answered 503"})
    argocd = CachedArgoCd(inner, TtlCache(clock=clock), ttl=60)
    assert argocd.has_token("hub")
    assert not argocd.has_token("other")
    a = await argocd.application_counts("hub", URL)
    b = await argocd.application_counts("hub", URL)
    await argocd.application_counts("main", URL)
    await argocd.application_counts("main", URL)
    assert a is b
    assert inner.reads == [("hub", URL), ("main", URL)]


async def test_the_links_file_is_read_each_time_and_may_be_missing(tmp_path: Path) -> None:
    path = tmp_path / "links.yaml"
    source = FileLinksSource(path)
    assert source.path == str(path)
    assert await source.read() is None
    path.write_text("sections: []\n", encoding="utf-8")
    assert await source.read() == "sections: []\n"
    path.write_text("clusters: {}\n", encoding="utf-8")
    assert await source.read() == "clusters: {}\n"


async def test_an_unreadable_links_file_says_why(tmp_path: Path) -> None:
    with pytest.raises(LinksFileUnreadableError):
        await FileLinksSource(tmp_path).read()  # a directory
    binary = tmp_path / "links.yaml"
    binary.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(LinksFileUnreadableError, match="not UTF-8"):
        await FileLinksSource(binary).read()


async def test_the_fake_probe_answers_the_first_matching_rule() -> None:
    probe = FakeLinkProbe(
        [
            CheckRule("netbox", LinkState.UNKNOWN, "TLS certificate not trusted", None, None),
            CheckRule("net", LinkState.DOWN, "answered 503", 503, 5),
        ]
    )
    assert (await probe.check("https://netbox.example.internal")).state is LinkState.UNKNOWN
    assert (await probe.check("https://network.example.internal")).http_status == 503
    assert (await probe.check("https://other.example.internal")).state is LinkState.UP


async def test_the_demo_fixtures_load() -> None:
    probe, argocd = load_fake_quick_links(fleet_fixture(CHECKS_FILE))
    down = await probe.check(
        "https://console-openshift-console.apps.ocp4-prep-mce-site2-a.example.internal"
    )
    assert (down.state, down.reason) == (LinkState.DOWN, "no answer within 3 s")
    hub = await argocd.application_counts("hub-dev", URL)
    assert isinstance(hub, ArgoCdReading)
    assert hub.counts is not None
    assert hub.counts.applications == 45
    assert hub.counts.health.unknown == 1  # 45 apps, 44 with a known health
    refused = await argocd.application_counts("ocp4-prod-mce-site2-a", URL)
    assert refused.error == "ArgoCD refused the token (401)"
    demo = parse_links_file(fleet_fixture(DEMO_LINKS_FILE).read_text(encoding="utf-8"))
    assert demo.state is LinksFileState.LOADED
    instances = {c.argocd.instance for s in demo.sections for c in s.cards if c.argocd}
    assert instances == {"main"}
    assert argocd.has_token("main")


def test_a_bad_fake_fixture_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "fake.yaml"
    path.write_text("- a\n", encoding="utf-8")
    with pytest.raises(TypeError):
        load_fake_quick_links(path)
    path.write_text("argocd: {hub: 3}\n", encoding="utf-8")
    with pytest.raises(TypeError):
        load_fake_quick_links(path)
    with pytest.raises(FileNotFoundError):
        fleet_fixture(Path("dev/fleet-fixtures/nothing-here.yaml"))
