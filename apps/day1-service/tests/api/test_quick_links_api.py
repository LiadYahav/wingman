"""``GET /api/day1/quick-links`` and ``/status`` (docs/notes/2026-11-12-quick-links-api.md).

Admins only (decision 13, until RBAC). Built on the fixture day1 repo with
the fake checks and ArgoCD, and a links file in a temporary folder.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.settings import Environment, GitBackend, RuntimeSettings
from wingman_day1.domain.quick_links import LinkState
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_quick_links import (
    CheckRule,
    FakeArgoCd,
    FakeLinkProbe,
    counts,
)
from wingman_day1.main import Adapters, create_app

Auth = Callable[[User], dict[str, str]]
ARGOCD = "https://openshift-gitops-server-openshift-gitops.apps.{}.example.internal"
CONSOLE = "https://console-openshift-console.apps.{}.example.internal"
LINKS = """
sections:
  - name: Core GitOps
    columns: 2
    links:
      - name: ArgoCD Main
        url: https://argocd.example.internal
        icon: argocd
        argocd: main
      - name: Typo
        href: https://typo.example.internal
"""


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    path: str,
    *,
    probe: FakeLinkProbe | None = None,
    argocd: FakeArgoCd | None = None,
    **settings: object,
) -> httpx.Response:
    values: dict[str, object] = {
        "quick_links_hub_name": "hub-prod",
        "mce_api_domain": "example.internal",
    }
    values.update(settings)
    app = create_app(
        settings=support.make_settings(**values),
        auth=support.make_auth(),
        runtime=RuntimeSettings(environment=Environment.TEST, git_backend=GitBackend.FAKE),
        adapters=Adapters(gitlab=gitlab, day2=FakeDay2Addons({}), link_probe=probe, argocd=argocd),
        clock=clock,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return await client.get(path, headers=headers)


@pytest.fixture
def links_file(tmp_path: Path) -> Path:
    path = tmp_path / "links.yaml"
    path.write_text(LINKS, encoding="utf-8")
    return path


@pytest.mark.parametrize("path", ["/api/day1/quick-links", "/api/day1/quick-links/status"])
async def test_only_admins_see_quick_links(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, path: str
) -> None:
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), path)
    assert viewer.status_code == 403
    assert viewer.json()["code"] == "FORBIDDEN"
    anonymous = await call(support, gitlab, clock, {}, path)
    assert anonymous.status_code == 401


async def test_the_cards_are_the_hub_each_site_s_mces_then_the_file(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, links_file: Path
) -> None:
    response = await call(
        support,
        gitlab,
        clock,
        auth(support.ALICE),
        "/api/day1/quick-links",
        probe=FakeLinkProbe(),
        argocd=FakeArgoCd({"hub-prod": counts(synced=1, healthy=1)}),
        quick_links_file=links_file,
    )
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["sections"]] == [
        "hub",
        "site:site1",
        "site:site2",
        "file:core-gitops",
    ]
    hub = body["sections"][0]["cards"][0]
    assert hub == {
        "id": "hub:hub-prod",
        "name": "hub-prod",
        "description": None,
        "icon": "argocd",
        "argocd": "hub-prod",
        "links": [
            {
                "label": "ArgoCD",
                "url": ARGOCD.format("hub-prod"),
                "ping": ARGOCD.format("hub-prod"),
            },
            {
                "label": "Console",
                "url": CONSOLE.format("hub-prod"),
                "ping": CONSOLE.format("hub-prod"),
            },
        ],
    }
    site1 = body["sections"][1]
    assert site1["name"] == "MCEs in site1"
    names = [c["name"] for c in site1["cards"]]
    assert names == sorted(names)
    assert "ocp4-prod-mce-site1-a" in names
    prod = next(c for c in site1["cards"] if c["name"] == "ocp4-prod-mce-site1-a")
    assert prod["argocd"] is None  # no token for it
    assert "hosted cluster" in (prod["description"] or "")
    core = body["sections"][3]
    assert (core["columns"], core["generated"]) == (2, False)
    assert [c["name"] for c in core["cards"]] == ["ArgoCD Main"]
    assert body["problems"] == []
    assert body["links_file"]["state"] == "loaded"
    assert body["links_file"]["path"] == str(links_file)
    assert body["links_file"]["problems"] == [
        'sections[0] "Core GitOps" links[1] "Typo": unknown key \'href\' (ignored)',
        'sections[0] "Core GitOps" links[1] "Typo": '
        "url must be an http(s) URL with a host (skipped)",
    ]


async def test_without_a_domain_the_page_says_what_to_set(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, tmp_path: Path
) -> None:
    response = await call(
        support,
        gitlab,
        clock,
        auth(support.ALICE),
        "/api/day1/quick-links",
        mce_api_domain="",
        quick_links_hub_name="",
        quick_links_file=tmp_path / "none.yaml",
    )
    body = response.json()
    assert body["sections"] == []
    assert body["problems"] == [
        "Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console."
    ]
    assert body["links_file"] == {
        "path": str(tmp_path / "none.yaml"),
        "state": "missing",
        "problems": [],
    }


async def test_a_file_that_is_not_yaml_is_named_and_the_generated_cards_stay(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, tmp_path: Path
) -> None:
    broken = tmp_path / "links.yaml"
    broken.write_text("sections: [\n", encoding="utf-8")
    body = (
        await call(
            support,
            gitlab,
            clock,
            auth(support.ALICE),
            "/api/day1/quick-links",
            quick_links_file=broken,
        )
    ).json()
    assert body["links_file"]["state"] == "invalid"
    assert body["links_file"]["problems"][0].startswith("the links file is not YAML")
    assert body["sections"][0]["id"] == "hub"


async def test_status_has_each_check_and_each_argocd_s_counts(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, links_file: Path
) -> None:
    probe = FakeLinkProbe(
        [CheckRule("console-openshift-console", LinkState.DOWN, "no answer within 3 s", None, None)]
    )
    argocd = FakeArgoCd(
        {
            "hub-prod": counts(synced=40, out_of_sync=2, healthy=39, degraded=2, progressing=1),
            "main": "ArgoCD refused the token (401)",
        }
    )
    response = await call(
        support,
        gitlab,
        clock,
        auth(support.ALICE),
        "/api/day1/quick-links/status",
        probe=probe,
        argocd=argocd,
        quick_links_file=links_file,
    )
    assert response.status_code == 200
    body = response.json()
    checks = {c["url"]: c for c in body["checks"]}
    assert checks[CONSOLE.format("hub-prod")]["state"] == "down"
    assert checks[CONSOLE.format("hub-prod")]["reason"] == "no answer within 3 s"
    up = checks[ARGOCD.format("hub-prod")]
    assert (up["state"], up["reason"], up["http_status"], up["latency_ms"]) == (
        "up",
        "answered 200",
        200,
        40,
    )
    assert "checked_at" in up
    assert "https://argocd.example.internal" in checks
    by_instance = {a["instance"]: a for a in body["argocd"]}
    assert by_instance["hub-prod"]["counts"] == {
        "applications": 42,
        "sync": {"synced": 40, "out_of_sync": 2, "unknown": 0},
        "health": {
            "healthy": 39,
            "progressing": 1,
            "degraded": 2,
            "missing": 0,
            "suspended": 0,
            "unknown": 0,
        },
    }
    assert by_instance["main"] == {
        "instance": "main",
        "counts": None,
        "error": "ArgoCD refused the token (401)",
        "checked_at": by_instance["main"]["checked_at"],
    }


async def test_status_checks_are_off_without_a_probe(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    board = await call(support, gitlab, clock, auth(support.ALICE), "/api/day1/quick-links")
    links = [link for s in board.json()["sections"] for c in s["cards"] for link in c["links"]]
    assert links
    assert all(link["ping"] is None for link in links)
    status = await call(support, gitlab, clock, auth(support.ALICE), "/api/day1/quick-links/status")
    assert status.json() == {"checks": [], "argocd": []}
