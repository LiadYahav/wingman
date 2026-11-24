"""A viewer reads the tenants' clusters, and no answer names the infrastructure (ADR-0068).

The fixtures' day1 tree has eight MCE-level folders, a seed among them, and two
KV clusters. A world with every feature on (live status, segments-manager,
upgrades, Scale, the excluded labels) and an open merge request of each kind
is read through every route a viewer may call; none of them may answer an
MCE's, the seed's or a KV cluster's name, or a path through ``mces/``. A new
viewer route joins :data:`VIEWER_READS`, or the coverage test fails.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.redaction import HIDDEN
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.web.auth import admin_user, current_user
from wingman_day1.application.tree import read_tree
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_scale import FakePool, FakeScaleWorkflow
from wingman_day1.infrastructure.fake_upgrade import FakeUpgradeWorkflow
from wingman_day1.infrastructure.fake_upgrade_script import (
    default_upgrade_file,
    load_upgrade_script,
)
from wingman_day1.integrations.segments_manager.infrastructure.fake import (
    FakeSegmentLedger,
    default_segments_file,
    load_segments,
)

LARK = "ocp4-prod-lark-site1"
AMIT = "ocp4-prep-amit-site2-a"
HERZI = "ocp4-prod-herzi-site1"
MCE = "ocp4-prod-mce-site1-a"
SMALL = "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"
FLAVOR = "agent-baseline"
LARK_FILE = f"sites/site1/mces/{MCE}/hostedClusters/{LARK}.yaml"
MCE_VALUES = f"sites/site1/mces/{MCE}/values.yaml"


async def _pools(_cluster: str) -> Sequence[FakePool]:
    return (FakePool(SMALL, "dell-r660-site1-128c-1024gb-5tb", 3),)


class World:
    """The app, a client, and what was opened in it."""

    def __init__(self, app: FastAPI, client: httpx.AsyncClient) -> None:
        self.app = app
        self.client = client
        self.mr_iid = 0
        self.spec_iid = 0
        self.lark_commit = ""
        self.mce_commit = ""
        self.spec_commit = ""

    def headers(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.app.state.session_tokens.issue(user)}"}


@pytest.fixture
async def world(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> AsyncIterator[World]:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        ledger=FakeSegmentLedger(load_segments(default_segments_file())),
        upgrade=FakeUpgradeWorkflow(load_upgrade_script(default_upgrade_file()), clock=clock),
        scale=FakeScaleWorkflow(clock=clock, pools=_pools),
        day1_upgrades=True,
        day1_excluded_agent_labels="redbull.io/used",
        workflows_api_url="http://workflows-orchestrator-api.test:8080",
        server_scan_url="http://server-scan.test:8000",
        segments_manager_ui_url="http://segments-manager.test",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        world = World(app, client)
        await _open_everything(world, support, gitlab)
        yield world


async def _open_everything(world: World, support: Any, gitlab: InMemoryGitLab) -> None:
    """A delete MR (its words name the MCE), provision MRs and a run, a flavor MR, runs, commits."""
    alice = world.headers(support.ALICE)
    client = world.client
    lark = (await client.get(f"/api/day1/clusters/{LARK}", headers=alice)).json()
    deleted = await client.delete(
        f"/api/day1/clusters/{LARK}",
        params={"last_commit_id": lark["last_commit_id"]},
        headers=alice,
    )
    assert deleted.status_code == 200, deleted.text
    world.mr_iid = deleted.json()["iid"]
    await support.open_provision_mr(gitlab, "ocp4-prod-newbie-site1")
    created = await client.post(
        "/api/day1/clusters", json=support.create_body("ocp4-prod-falcon-site1"), headers=alice
    )
    assert created.status_code == 202, created.text
    spec = {"metadata": {"name": "agent-mini", "version": "1.0.0"}}
    world.spec_iid = (await client.post("/api/day1/specs", json=spec, headers=alice)).json()["iid"]
    started = await client.post(
        f"/api/day1/clusters/{LARK}/upgrade", json={"target_version": "4.18.56"}, headers=alice
    )
    assert started.status_code == 202, started.text
    scaled = await client.post(
        f"/api/day1/clusters/{LARK}/scale", json={"replicas": 2, "nodepool": SMALL}, headers=alice
    )
    assert scaled.status_code == 202, scaled.text
    # On main: a commit to lark's file that names its MCE, and one to the MCE's own values
    world.lark_commit = await _commit(
        gitlab, support, LARK_FILE, "# a note\n", f"Retag lark on {MCE}"
    )
    world.mce_commit = await _commit(gitlab, support, MCE_VALUES, "# tuned\n", f"Tune {MCE}")
    history = await client.get(f"/api/day1/specs/{FLAVOR}/history", headers=alice)
    world.spec_commit = history.json()[0]["sha"]


async def _commit(gitlab: InMemoryGitLab, support: Any, path: str, extra: str, message: str) -> str:
    pid = await support.project_id(gitlab, support.DAY1)
    current = await gitlab.read_file(pid, RepoPath(path), "main")
    change = FileChange.update(
        RepoPath(path), current.content + extra, last_commit_id=current.last_commit_id
    )
    commit = await gitlab.commit(pid, branch="main", message=message, changes=[change])
    return commit.id


def VIEWER_READS(world: World) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Every route a viewer may call, with what it is called with here."""
    one = f"/api/day1/clusters/{LARK}"
    return [
        ("GET", "/api/auth/me", None),
        ("GET", "/api/day1/build", None),
        ("GET", "/api/day1/clusters", None),
        ("GET", "/api/day1/clusters/drift-summary", None),
        ("POST", "/api/day1/clusters/bulk-status", {"clusters": [{"name": LARK}]}),
        ("GET", f"{one}/status", None),
        ("GET", f"{one}?site=site1&mce=ocp4-prod-mce-site1-z", None),
        ("GET", f"{one}/history", None),
        ("GET", f"{one}/current-yaml", None),
        ("GET", f"{one}/drift", None),
        ("GET", f"{one}/network", None),
        ("GET", f"/api/day1/clusters/{AMIT}/network", None),
        ("GET", f"{one}/provision-run", None),
        ("GET", "/api/day1/clusters/ocp4-prod-falcon-site1/provision-run", None),
        ("GET", f"{one}/delete-workflow", None),
        ("GET", f"{one}/scale", None),
        ("GET", f"{one}/scale-run", None),
        ("GET", f"{one}/excluded-agent-labels", None),
        ("GET", f"{one}/upgrade-run", None),
        ("GET", "/api/day1/upgrades", None),
        ("GET", "/api/day1/specs", None),
        ("GET", f"/api/day1/specs/{FLAVOR}", None),
        ("GET", "/api/day1/specs/template", None),
        ("GET", "/api/day1/specs/template/schema", None),
        ("GET", f"/api/day1/specs/{FLAVOR}/history", None),
        ("GET", f"/api/day1/specs/{FLAVOR}/at/{world.spec_commit}", None),
        ("GET", f"/api/day1/specs/{FLAVOR}/clusters", None),
        ("GET", f"/api/day1/specs/{FLAVOR}/drift", None),
        ("GET", f"/api/day1/specs/{FLAVOR}/rollout", None),
        ("GET", "/api/day1/machine-configs", None),
        ("GET", "/api/day1/tuning-profiles", None),
        ("GET", "/api/day1/approvals", None),
        ("GET", f"/api/day1/approvals/{world.mr_iid}", None),
        ("GET", f"/api/day1/approvals/{world.spec_iid}?repo=specs", None),
        ("GET", f"/api/day1/approvals/{world.spec_iid}/rollout?repo=specs", None),
        ("GET", "/api/day1/audit/commits", None),
        ("GET", "/api/day1/audit/merge-requests", None),
        ("GET", f"/api/day1/audit/commits/day1/{world.lark_commit}/diff", None),
        ("GET", f"/api/day1/audit/commits/specs/{world.spec_commit}/diff", None),
    ]


NOT_READ = {"/provision-run": 404, "/delete-workflow": 501}
"""The crawl's answers that are not a 200: lark was never provisioned by Wingman, and the
delete-cluster workflow does not exist yet (ADR-0033). Each still names nothing."""


def _api_routes(routes: Sequence[Any]) -> list[APIRoute]:
    """Every API route, inside the routers FastAPI includes lazily (``original_router``)."""
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif (router := getattr(route, "original_router", None)) is not None:
            found += _api_routes(router.routes)
    return found


def _viewer_routes(app: FastAPI) -> set[tuple[str, str]]:
    """``(method, path)`` of every route a session may call that does not need an admin."""

    def calls(dependant: Any) -> set[Any]:
        found = {dependant.call}
        for sub in dependant.dependencies:
            found |= calls(sub)
        return found

    routes: set[tuple[str, str]] = set()
    for route in _api_routes(app.routes):
        needed = calls(route.dependant)
        if current_user in needed and admin_user not in needed:
            routes |= {(m, route.path) for m in route.methods or ()}
    return routes


async def _infrastructure_names(gitlab: InMemoryGitLab, world: World) -> set[str]:
    tree = await read_tree(world.app.state.day1.repos["day1"])
    names = set(tree.infrastructure.names)
    assert {MCE, "ocp4-prod-seed-site1-az1-a", "ocp4-prod-kv-site1-az1-a"} <= names
    return names


def _template(app: FastAPI, method: str, url: str) -> tuple[str, str] | None:
    path = httpx.URL(url).path
    for route in _api_routes(app.routes):
        if method in (route.methods or ()) and route.path_regex.match(path):
            return (method, route.path)
    return None


async def test_every_viewer_route_is_read_here(world: World) -> None:
    crawled = {_template(world.app, m, url) for m, url, _ in VIEWER_READS(world)}
    # An event stream never ends: test_status_api.py reads its first event as a viewer
    crawled.add(("GET", "/api/day1/clusters/{name}/status/stream"))
    assert _viewer_routes(world.app) - crawled == set()


async def test_no_answer_a_viewer_reads_names_the_infrastructure(
    world: World, support: Any, gitlab: InMemoryGitLab
) -> None:
    names = await _infrastructure_names(gitlab, world)
    viewer = world.headers(support.VIEWER)
    for method, url, body in VIEWER_READS(world):
        response = await world.client.request(method, url, json=body, headers=viewer)
        expected = NOT_READ.get(url.removeprefix(f"/api/day1/clusters/{LARK}"), 200)
        assert response.status_code == expected, (url, response.text)
        text = response.text.lower()
        leaked = {n for n in names if n in text}
        assert not leaked, (url, leaked)
        found = re.search(r"mces/[a-z0-9]", text)  # a folder, not the template's <mce>
        at = found.start() if found else -1
        assert at < 0, (url, text[max(0, at - 160) : at + 40])


async def test_an_admin_reads_the_same_routes_with_every_name(world: World, support: Any) -> None:
    alice = world.headers(support.ALICE)
    detail = (await world.client.get(f"/api/day1/clusters/{AMIT}", headers=alice)).json()
    assert detail["mce"] == "ocp4-prep-mce-site2-a"
    assert detail["path"].startswith("sites/site2/mces/")
    assert detail["gitlab_url"] and detail["segments_manager"]
    approval = (await world.client.get(f"/api/day1/approvals/{world.mr_iid}", headers=alice)).json()
    assert f"MCE `{MCE}`" in approval["mr"]["description"]
    assert [d["new_path"] for d in approval["diffs"]] == [LARK_FILE]


# ── A tenant's cluster: its site, never its MCE ──────────────────────────────


async def test_a_viewers_cluster_says_its_site_and_no_mce_path_or_link(
    world: World, support: Any
) -> None:
    viewer = world.headers(support.VIEWER)
    detail = (await world.client.get(f"/api/day1/clusters/{AMIT}", headers=viewer)).json()
    assert (detail["name"], detail["site"]) == (AMIT, "site2")
    assert detail["mce"] is detail["path"] is detail["gitlab_url"] is None
    assert detail["metadata"]["mce"] is None
    assert detail["mce_default_mastertag"] is detail["segments_manager"] is None
    listed = (await world.client.get("/api/day1/clusters", headers=viewer)).json()
    amit = next(c for c in listed if c["name"] == AMIT)
    assert (amit["site"], amit["mce"], amit["path"]) == ("site2", None, None)


@pytest.mark.parametrize(
    "params",
    [
        {"mce": "ocp4-prod-mce-site1-z"},
        {"site": "site9", "mce": MCE},
        {"site": "site1", "mce": "ocp4-prod-seed-site1-az1-a"},
    ],
)
async def test_a_viewers_site_and_mce_are_ignored_so_they_test_no_name(
    world: World, support: Any, params: dict[str, str]
) -> None:
    viewer = world.headers(support.VIEWER)
    read = await world.client.get(f"/api/day1/clusters/{AMIT}", params=params, headers=viewer)
    assert (read.status_code, read.json()["name"]) == (200, AMIT)
    admin = await world.client.get(
        f"/api/day1/clusters/{AMIT}", params=params, headers=world.headers(support.ALICE)
    )
    assert admin.status_code == 404, "an admin's site and mce still pin the file"


async def test_a_viewers_network_is_the_files_and_segments_manager_is_not_asked(
    world: World, support: Any
) -> None:
    viewer = world.headers(support.VIEWER)
    shown = (await world.client.get(f"/api/day1/clusters/{AMIT}/network", headers=viewer)).json()
    assert shown == {
        "vlan_id": 2490,
        "segment": "10.20.90.0/24",
        "epg": None,
        "ledger": None,
        "problems": [],
        "ledger_error": None,
    }
    alice = world.headers(support.ALICE)
    admin = (await world.client.get(f"/api/day1/clusters/{AMIT}/network", headers=alice)).json()
    assert admin["epg"] == "EPG_site2_HC_2490"


async def test_the_name_suggestion_is_an_admins(world: World, support: Any) -> None:
    params = {"site": "site1", "mce": MCE, "flavor": FLAVOR}
    viewer = await world.client.get(
        "/api/day1/clusters/name-suggestion", params=params, headers=world.headers(support.VIEWER)
    )
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")


async def test_a_viewers_bulk_status_is_found_by_name(world: World, support: Any) -> None:
    body = {"clusters": [{"name": HERZI}, {"name": HERZI, "mce": "ocp4-prod-mce-site1-z"}]}
    viewer = await world.client.post(
        "/api/day1/clusters/bulk-status", json=body, headers=world.headers(support.VIEWER)
    )
    assert viewer.json()[HERZI]["error"] is None


# ── Merge requests and commits ───────────────────────────────────────────────


async def test_a_viewers_merge_request_is_its_clusters_file_by_name_and_its_words_hidden(
    world: World, support: Any
) -> None:
    viewer = world.headers(support.VIEWER)
    approval = (
        await world.client.get(f"/api/day1/approvals/{world.mr_iid}", headers=viewer)
    ).json()
    assert [d["new_path"] for d in approval["diffs"]] == [f"{LARK}.yaml"]
    assert f"MCE `{HIDDEN}`" in approval["mr"]["description"]
    listed = (await world.client.get("/api/day1/approvals", headers=viewer)).json()
    provision = next(m for m in listed if m["opened_by_workflow"])
    assert provision["title"] == f"Provision hosted cluster ocp4-prod-newbie-site1 on {HIDDEN}"


async def test_a_day1_merge_request_about_no_cluster_is_not_a_viewers(
    world: World, support: Any, gitlab: InMemoryGitLab
) -> None:
    by_hand = await support.open_provision_mr(
        gitlab,
        "ocp4-prod-other-site1",
        branch="hand/mce-tuning",
        title="Tune the hub",
        labels=("wingman",),
    )
    world.app.state.day1.repos["day1"].forget_merge_requests()
    viewer = world.headers(support.VIEWER)
    listed = (await world.client.get("/api/day1/approvals", headers=viewer)).json()
    assert by_hand.ref.iid not in {m["iid"] for m in listed if m["repo"] == "day1"}
    one = await world.client.get(f"/api/day1/approvals/{by_hand.ref.iid}", headers=viewer)
    assert one.status_code == 404
    admin = await world.client.get(
        f"/api/day1/approvals/{by_hand.ref.iid}", headers=world.headers(support.ALICE)
    )
    assert admin.status_code == 200


async def test_a_viewers_commits_are_the_tenants_files_and_the_flavors(
    world: World, support: Any
) -> None:
    viewer = world.headers(support.VIEWER)
    commits = (await world.client.get("/api/day1/audit/commits", headers=viewer)).json()
    ids = {c["id"] for c in commits}
    assert world.lark_commit in ids and world.spec_commit in ids
    assert world.mce_commit not in ids
    lark = next(c for c in commits if c["id"] == world.lark_commit)
    assert lark["title"] == f"Retag lark on {HIDDEN}"
    alice = world.headers(support.ALICE)
    every = (await world.client.get("/api/day1/audit/commits", headers=alice)).json()
    assert world.mce_commit in {c["id"] for c in every}


async def test_a_viewer_reads_a_commits_tenant_files_alone(world: World, support: Any) -> None:
    viewer = world.headers(support.VIEWER)
    lark = await world.client.get(
        f"/api/day1/audit/commits/day1/{world.lark_commit}/diff", headers=viewer
    )
    assert [d["new_path"] for d in lark.json()] == [f"{LARK}.yaml"]
    mce = await world.client.get(
        f"/api/day1/audit/commits/day1/{world.mce_commit}/diff", headers=viewer
    )
    assert (mce.status_code, mce.json()["code"]) == (404, "NOT_FOUND")
    admin = await world.client.get(
        f"/api/day1/audit/commits/day1/{world.mce_commit}/diff",
        headers=world.headers(support.ALICE),
    )
    assert [d["new_path"] for d in admin.json()] == [MCE_VALUES]


# ── Live status ──────────────────────────────────────────────────────────────


async def test_a_viewers_status_is_found_by_name_never_by_an_mce(
    world: World, support: Any
) -> None:
    viewer = world.headers(support.VIEWER)
    status = await world.client.get(f"/api/day1/clusters/{LARK}/status", headers=viewer)
    assert status.status_code == 200
    unmerged = await world.client.get(
        "/api/day1/clusters/ocp4-prod-newbie-site1/status", params={"mce": MCE}, headers=viewer
    )
    assert unmerged.status_code == 404, "a viewer's cluster is the tree's: no MCE to name"
