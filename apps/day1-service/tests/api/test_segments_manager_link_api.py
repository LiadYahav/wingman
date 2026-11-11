"""The cluster detail's links to segments-manager (docs/notes/2026-11-11-cluster-nodes-api.md §5).

Day1 builds both URLs from ``SEGMENTS_MANAGER_UI_URL``; the web only shows
them. Off (the default), the field is ``null``. The search is by the cluster
file's stem, the ``cluster_name`` allocate-segment gave segments-manager.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

Auth = Callable[[User], dict[str, str]]
HERZI = "ocp4-prod-herzi-site1"
UI = "https://segments-manager.example"


async def detail(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, name: str, **settings: object
) -> dict[str, Any]:
    """``GET /api/day1/clusters/{name}`` as a viewer, on an app with ``settings``."""
    app = support.build_app(
        gitlab=gitlab, hub=None, identity=None, day2=FakeDay2Addons(), clock=clock, **settings
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        response = await client.get(
            f"/api/day1/clusters/{quote(name, safe='')}", headers=auth(support.VIEWER)
        )
    assert response.status_code == 200, response.text
    return response.json()


async def test_without_the_setting_a_cluster_has_no_link(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await detail(support, gitlab, clock, auth, HERZI)
    assert "segments_manager" in body
    assert body["segments_manager"] is None


async def test_with_the_setting_a_cluster_links_to_the_ui_and_its_segment_search(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await detail(support, gitlab, clock, auth, HERZI, SEGMENTS_MANAGER_UI_URL=UI + "/")
    assert body["segments_manager"] == {
        "url": f"{UI}/",
        "search_url": f"{UI}/api/segments/search?q={HERZI}",
    }


async def test_the_search_is_by_the_file_stem_not_the_chart_cluster_name(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    body = await detail(support, gitlab, clock, auth, HERZI, SEGMENTS_MANAGER_UI_URL=UI)
    assert body["hosted_cluster"]["cluster_name"] == "prod-herzi-site1"
    assert body["segments_manager"]["search_url"].endswith(f"?q={body['name']}")


async def test_the_name_is_encoded_in_the_search_and_a_base_path_is_kept(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    odd = "ocp4-lab+a&b-site1"
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=f"sites/{support.PROD_SITE}/mces/{support.PROD_MCE}/hostedClusters/{odd}.yaml",
        content="mastertag: 4.16.27-x86_64\nnodepool: []\n",
    )
    body = await detail(support, gitlab, clock, auth, odd, SEGMENTS_MANAGER_UI_URL=f"{UI}/sm/")
    assert body["segments_manager"] == {
        "url": f"{UI}/sm/",
        "search_url": f"{UI}/sm/api/segments/search?q=ocp4-lab%2Ba%26b-site1",
    }
