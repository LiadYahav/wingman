"""Quick Links' links file and the fake fleet's demo of it (ADR-0052)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wingman_day1.domain.quick_links import LinksFileUnreadableError
from wingman_day1.infrastructure.fake_quick_links import default_demo_links_file
from wingman_day1.infrastructure.links_file import FileLinksSource


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


def test_the_fake_fleet_finds_the_demo_links_file() -> None:
    demo = default_demo_links_file()
    assert demo.is_file()
    assert demo.as_posix().endswith("dev/fleet-fixtures/quick-links-links.yaml")
