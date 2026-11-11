"""The links from a cluster to segments-manager's UI and its segment search."""

from __future__ import annotations

import pytest

from wingman_day1.domain.segments_manager import SegmentsManagerLinks, segments_manager_links

UI = "https://segments-manager.example"


@pytest.mark.parametrize("base", [UI, UI + "/", UI + "//"])
def test_the_ui_link_is_the_base_with_one_slash(base: str) -> None:
    assert segments_manager_links(base, "ocp4-prod-herzi-site1") == SegmentsManagerLinks(
        url=f"{UI}/",
        search_url=f"{UI}/api/segments/search?q=ocp4-prod-herzi-site1",
    )


def test_a_base_path_is_kept() -> None:
    links = segments_manager_links(f"{UI}/tools/sm/", "ocp4-prod-herzi-site1")
    assert links.url == f"{UI}/tools/sm/"
    assert links.search_url == f"{UI}/tools/sm/api/segments/search?q=ocp4-prod-herzi-site1"


@pytest.mark.parametrize(
    ("cluster", "query"),
    [
        ("ocp4-prod-a_b.c~d-site1", "ocp4-prod-a_b.c~d-site1"),
        ("a b", "a%20b"),
        ("a+b&c=d", "a%2Bb%26c%3Dd"),
        ("a/b?c#d", "a%2Fb%3Fc%23d"),
        ("שם", "%D7%A9%D7%9D"),
    ],
)
def test_the_cluster_is_one_encoded_query_value(cluster: str, query: str) -> None:
    assert segments_manager_links(UI, cluster).search_url == f"{UI}/api/segments/search?q={query}"
