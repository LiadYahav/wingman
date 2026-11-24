"""A viewer reads the tenants' clusters, and no day2 answer names the infrastructure (ADR-0068).

The fixtures' day1 tree has seven Customer MCEs, a seed and its two KV
clusters; the team repos add the hub (``prod-hub``, its UPI Argo CD
``prod-hub-upi``) and two UPI clusters. A world with an open install on a
tenant's cluster, on an MCE hub, on the hub, on a UPI and on a KV cluster,
a fleet default of each kind open, and a tenant's and an MCE's install
merged is read through every route a viewer may call; none may answer a
hidden name or a path through an MCE's folder. A new viewer route joins
:data:`VIEWER_READS`, or the coverage test fails.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.redaction import HIDDEN
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.web.auth import admin_user, current_user

HERZI = "ocp4-prod-herzi-site1"
KARNIOL = "ocp4-prod-karniol-site1"
MCE = "ocp4-prod-mce-site1-a"
PREP_MCE = "ocp4-prep-mce-site1-a"
SEED = "ocp4-prod-seed-site1-az1-a"
KV = "ocp4-prod-kv-site1-az1-a"
UPI = "ocp4-dok-site1"
HERZI_ID = f"hosted:site1:prod:{MCE}:{HERZI}"
MCE_ID = f"mce:site1:prod:{MCE}"
UPI_ID = f"upi:site1:prod:{UPI}"
HERZI_DIR = f"sites/site1/prod/mces/{MCE}/{HERZI}"
PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id", "details"}


def ok(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == PROBLEM_KEYS and (body["status"], body["code"]) == (status, code)
    return body


@dataclass
class World:
    """What the admins opened and merged."""

    tenant_mr: int
    mce_mr: int
    hub_mr: int
    upi_mr: int
    kv_mr: int
    hosted_default_mr: int
    mce_default_mr: int
    tenant_commit: str
    mce_commit: str


async def _open(client: httpx.AsyncClient, url: str, body: Any = None) -> dict[str, Any]:
    return ok(await client.post(url, json=body or {}), 201)


async def _install(client: httpx.AsyncClient, cluster: str, chart: str) -> dict[str, Any]:
    return await _open(client, f"/api/day2/clusters/{cluster}/addons/redbull/{chart}")


async def _merged(jane: httpx.AsyncClient, bob: httpx.AsyncClient, cluster: str) -> str:
    """The commit of an install on ``cluster``, which ``bob`` merged."""
    change = await _install(jane, cluster, "cluster-roles" if ":" in cluster else "bmhgen")
    approve = f"/api/day2/approvals/redbull/{change['iid']}/approve"
    ok(await bob.post(approve, json={"sha": change["sha"]}))
    return change["sha"]


@pytest.fixture
async def world(jane: httpx.AsyncClient, bob: httpx.AsyncClient) -> World:
    tenant = await _open(
        jane,
        f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen",
        {"override_values": {"replicas": 2}},
    )
    mce = await _install(jane, MCE_ID, "cluster-roles")
    hub = await _install(jane, "hub", "bmhgen")
    upi = await _install(jane, UPI_ID, "bmhgen")
    kv = await _install(jane, KV, "cluster-roles")
    hosted = await _open(jane, "/api/day2/addons/redbull/kyverno/defaults/hosted-clusters")
    mces = await _open(jane, "/api/day2/addons/redbull/cluster-roles/defaults/mces")
    return World(
        tenant_mr=tenant["iid"],
        mce_mr=mce["iid"],
        hub_mr=hub["iid"],
        upi_mr=upi["iid"],
        kv_mr=kv["iid"],
        hosted_default_mr=hosted["iid"],
        mce_default_mr=mces["iid"],
        tenant_commit=await _merged(jane, bob, KARNIOL),
        mce_commit=await _merged(jane, bob, f"mce:site1:prep:{PREP_MCE}"),
    )


def VIEWER_READS(world: World) -> list[tuple[str, str, dict[str, Any] | None, int]]:
    """Every route a viewer may call, with what it is called with here and its status."""
    one = f"/api/day2/clusters/{HERZI}"
    preview = {"team": "redbull", "addon": "cluster-roles", "cluster": HERZI}
    return [
        ("GET", "/api/day2/build", None, 200),
        ("GET", "/api/day2/gitlab-info", None, 200),
        ("GET", "/api/day2/teams", None, 200),
        ("GET", "/api/day2/teams/redbull", None, 200),
        ("GET", "/api/day2/addons", None, 200),
        ("GET", "/api/day2/addons/redbull/cluster-roles", None, 200),
        ("GET", "/api/day2/addons/redbull/cluster-roles/versions", None, 200),
        ("GET", "/api/day2/addons/redbull/cluster-roles/values", None, 200),
        ("GET", "/api/day2/lints", None, 200),
        ("GET", "/api/day2/clusters", None, 200),
        ("GET", f"{one}?mce=ocp4-prod-mce-site1-z", None, 200),
        ("GET", f"{one}/addons?mce={SEED}", None, 200),
        ("GET", f"{one}/addons/redbull/cluster-roles", None, 200),
        ("POST", "/api/day2/merge-preview", preview, 200),
        ("GET", f"{one}/history", None, 200),
        ("GET", f"{one}/upgrade-check?to=4.17.1", None, 200),
        ("GET", "/api/day2/clusters/hub", None, 404),
        ("GET", f"/api/day2/clusters/{MCE_ID}/addons", None, 404),
        ("GET", f"/api/day2/clusters/{UPI}", None, 404),
        ("GET", f"/api/day2/clusters/{KV}/history", None, 404),
        ("GET", "/api/day2/approvals", None, 200),
        ("GET", f"/api/day2/approvals/redbull/{world.tenant_mr}", None, 200),
        ("GET", f"/api/day2/approvals/redbull/{world.hosted_default_mr}", None, 200),
        ("GET", f"/api/day2/approvals/redbull/{world.mce_mr}", None, 404),
        ("GET", f"/api/day2/approvals/redbull/{world.hub_mr}", None, 404),
        ("GET", "/api/day2/audit/commits", None, 200),
        ("GET", "/api/day2/audit/merge-requests", None, 200),
        ("GET", f"/api/day2/audit/commits/{world.tenant_commit}/diff", None, 200),
        ("GET", f"/api/day2/audit/commits/{world.mce_commit}/diff", None, 404),
        ("GET", "/api/day2/fleet-defaults", None, 200),
        ("GET", "/api/day2/teams/redbull/addons", None, 200),
        ("GET", "/api/day2/teams/redbull/addons/cluster-roles", None, 200),
        ("GET", "/api/day2/teams/redbull/addons/dhcp-api-token", None, 404),
        ("GET", "/api/day2/teams/redbull/operators", None, 200),
        ("GET", "/api/day2/teams/redbull/operators/kyverno", None, 200),
    ]


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


def _template(app: FastAPI, method: str, url: str) -> tuple[str, str] | None:
    path = httpx.URL(url).path
    for route in _api_routes(app.routes):
        if method in (route.methods or ()) and route.path_regex.match(path):
            return (method, route.path)
    return None


async def _hidden_names(app: FastAPI) -> set[str]:
    names = set((await app.state.day2.topology.load()).infrastructure.names)
    assert {MCE, PREP_MCE, SEED, KV, UPI, "prod-hub", "prod-hub-upi"} <= names
    return names


async def test_every_viewer_route_is_read_here(app: FastAPI, world: World) -> None:
    crawled = {_template(app, m, url) for m, url, _, _ in VIEWER_READS(world)}
    assert _viewer_routes(app) - crawled == set()


async def test_no_answer_a_viewer_reads_names_the_infrastructure(
    app: FastAPI, world: World, vic: httpx.AsyncClient
) -> None:
    names = await _hidden_names(app)
    for method, url, body, status in VIEWER_READS(world):
        response = await vic.request(method, url, json=body)
        assert response.status_code == status, (url, response.text)
        text = response.text.lower()
        # A 404 says back the name the viewer sent, as an unknown one's does: nothing more
        asked = httpx.URL(url).path.lower() if status == 404 else ""
        leaked = {n for n in names if n in text and n not in asked}
        assert not leaked, (url, leaked)
        assert all(k not in text for k in ("mce:", "upi:") if k not in asked), url
        found = re.search(r"mces/[a-z0-9]", text)
        at = found.start() if found else -1
        assert at < 0, (url, text[max(0, at - 160) : at + 40])


async def test_an_admin_reads_the_same_routes_with_every_name(
    world: World, jane: httpx.AsyncClient
) -> None:
    herzi = ok(await jane.get(f"/api/day2/clusters/{HERZI}"))
    assert (herzi["id"], herzi["mce"], herzi["argo"]) == (HERZI_ID, MCE, MCE)
    kinds = {c["kind"] for c in ok(await jane.get("/api/day2/clusters"))}
    assert kinds == {"hub", "mce", "hosted", "upi"}
    approvals = {m["iid"] for m in ok(await jane.get("/api/day2/approvals"))}
    assert {
        world.mce_mr,
        world.hub_mr,
        world.upi_mr,
        world.kv_mr,
        world.mce_default_mr,
    } <= approvals
    mce = ok(await jane.get(f"/api/day2/approvals/redbull/{world.mce_mr}"))
    assert MCE in mce["mr"]["title"]
    assert [d["new_path"] for d in mce["diffs"]] == [
        f"sites/site1/prod/mces/{MCE}/in-cluster/cluster-roles/values.yaml"
    ]
    commits = {c["id"] for c in ok(await jane.get("/api/day2/audit/commits"))}
    assert world.mce_commit in commits
    ok(await jane.get("/api/day2/teams/redbull/addon-template"))


# ── R1, R2: the tenants' clusters, by name ───────────────────────────────────


@pytest.mark.parametrize("cluster", ["hub", "prod-hub", UPI, UPI_ID, MCE, MCE_ID, KV, SEED])
async def test_a_viewer_naming_anything_but_a_tenant_gets_what_an_unknown_name_gets(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, cluster: str
) -> None:
    hidden = problem(await vic.get(f"/api/day2/clusters/{cluster}"), 404, "NOT_FOUND")
    unknown = problem(await vic.get("/api/day2/clusters/ocp4-prod-nothere-site1"), 404, "NOT_FOUND")
    assert hidden["detail"] == unknown["detail"].replace("ocp4-prod-nothere-site1", cluster)
    assert hidden["details"] == {"cluster": cluster}
    ok(await jane.get(f"/api/day2/clusters/{cluster}"))


async def test_a_viewers_list_is_the_tenants_clusters(vic: httpx.AsyncClient) -> None:
    listed = ok(await vic.get("/api/day2/clusters"))
    assert {c["kind"] for c in listed} == {"hosted"}
    assert HERZI in {c["name"] for c in listed} and KV not in {c["name"] for c in listed}
    assert ok(await vic.get("/api/day2/clusters?kind=upi")) == []


async def test_a_viewers_cluster_is_named_by_its_name_with_no_mce_argo_or_link(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    herzi = ok(await vic.get(f"/api/day2/clusters/{HERZI}"))
    assert (herzi["id"], herzi["name"], herzi["site"], herzi["env"]) == (
        HERZI,
        HERZI,
        "site1",
        "prod",
    )
    assert herzi["mce"] is None and herzi["argo"] is None
    charts = ok(await vic.get(f"/api/day2/clusters/{HERZI}/addons"))
    assert (charts["id"], charts["cluster"], charts["mce"]) == (HERZI, HERZI, None)
    (roles,) = charts["installed"]
    assert roles["gitlab_url"] is None and roles["deploy"]["argo"] is None
    assert roles["path"] == f"{HERZI}/cluster-roles"
    assert roles["override_path"] == f"{HERZI}/cluster-roles/values.yaml"
    admin = ok(await jane.get(f"/api/day2/clusters/{HERZI}/addons"))
    assert admin["installed"][0]["gitlab_url"].endswith(f"/-/tree/main/{HERZI_DIR}/cluster-roles")
    problem(await vic.get(f"/api/day2/clusters/{HERZI_ID}"), 404, "NOT_FOUND")
    assert ok(await jane.get(f"/api/day2/clusters/{HERZI_ID}"))["id"] == HERZI_ID


@pytest.mark.parametrize("mce", [MCE, "ocp4-prod-mce-site1-z", SEED])
async def test_a_viewers_mce_is_ignored_so_it_tests_no_name(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, mce: str
) -> None:
    # day1's drift reads a tenant's add-ons this way, as a viewer (system:wingman-day1)
    shown = ok(await vic.get(f"/api/day2/clusters/{HERZI}/addons", params={"mce": mce}))
    assert [(a["team"], a["name"], a["version"]) for a in shown["installed"]] == [
        ("redbull", "cluster-roles", "main")
    ]
    admin = await jane.get(f"/api/day2/clusters/{HERZI}/addons", params={"mce": mce})
    assert admin.status_code == (200 if mce == MCE else 404)


async def test_day1s_drift_session_reads_a_tenants_add_ons(
    client_for: Any, gitlab: InMemoryGitLab
) -> None:
    day1 = client_for(User("system:wingman-day1", Role.VIEWER))
    params = {"mce": "ocp4-prep-mce-site2-a", "site": "site2"}
    shown = ok(await day1.get("/api/day2/clusters/ocp4-prep-wren-site2/addons", params=params))
    assert {(a["team"], a["name"]) for a in shown["installed"]} == {("lynx", "cluster-roles")}


async def _commit(gitlab: InMemoryGitLab, team: str, files: dict[str, str], message: str) -> str:
    """One commit on ``team``'s main writing ``files`` (each created, or updated if it exists)."""
    pid = (await gitlab.get_project(f"sigs/{team}")).id
    changes = []
    for path, text in files.items():
        try:
            read = await gitlab.read_file(pid, RepoPath(path), "main")
        except NotFoundError:
            changes.append(FileChange.create(RepoPath(path), text))
        else:
            changes.append(
                FileChange.update(RepoPath(path), text, last_commit_id=read.last_commit_id)
            )
    return (await gitlab.commit(pid, branch="main", message=message, changes=changes)).id


async def test_a_name_a_hidden_destination_shares_resolves_to_the_viewers_tenant(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    upi = f"sites/site1/prod/upi/{HERZI}/cluster-roles/values.yaml"
    await _commit(gitlab, "redbull", {upi: "{}\n"}, "a UPI folder reusing a tenant's name")
    admin = problem(await jane.get(f"/api/day2/clusters/{HERZI}/addons"), 422, "VALIDATION_ERROR")
    assert admin["details"]["candidates"] == [HERZI_ID, f"upi:site1:prod:{HERZI}"]
    # The viewer's name is the tenant's: resolved once, and the service is asked by its id
    shown = ok(await vic.get(f"/api/day2/clusters/{HERZI}/addons"))
    assert shown["kind"] == "hosted" and shown["installed"][0]["name"] == "cluster-roles"
    ok(await vic.get(f"/api/day2/clusters/{HERZI}/addons/redbull/cluster-roles"))
    ok(await vic.get(f"/api/day2/clusters/{HERZI}/history"))
    ok(await vic.get(f"/api/day2/clusters/{HERZI}/upgrade-check?to=4.17.1"))


async def test_a_name_two_tenants_share_is_ambiguous_for_a_viewer_without_their_ids(
    vic: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    twin = f"sites/site1/prod/mces/ocp4-prod-mce-site1-b/{HERZI}/cluster-roles/values.yaml"
    await _commit(gitlab, "redbull", {twin: "{}\n"}, "the same name under another MCE")
    body = problem(await vic.get(f"/api/day2/clusters/{HERZI}"), 422, "VALIDATION_ERROR")
    assert body["details"] == {"cluster": HERZI}
    assert "mce" not in str(body).lower().replace(HERZI, "")


# ── R3, R4, R10: a tenant's values, its paths, its errors ────────────────────


async def test_a_viewers_value_stack_keeps_every_layer_with_paths_they_may_read(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    url = f"/api/day2/clusters/{HERZI}/addons/redbull/cluster-roles"
    shown = ok(await vic.get(url))
    layers = {x["role"]: x["path"] for x in shown["layers"]}
    assert layers["mce"] == f"sites/site1/prod/mces/{HIDDEN}/values.yaml"
    assert layers["cluster-wide"] == f"{HERZI}/values.yaml"
    assert layers["cluster"] == f"{HERZI}/cluster-roles/values.yaml"
    assert layers["fleet-target"] == f"defaults/hosted-clusters/cluster-roles/values-{HERZI}.yaml"
    assert shown["cluster"] == HERZI and shown["deploy"]["argo"] is None
    assert [x["path"] for x in shown["deploy"]["layers"]][-1] == (
        f"{HERZI}/cluster-roles/cluster-roles.yaml"
    )
    admin = ok(await jane.get(url))
    assert [x["role"] for x in admin["layers"]] == [x["role"] for x in shown["layers"]]
    assert {x["role"]: x["path"] for x in admin["layers"]}["mce"] == (
        f"sites/site1/prod/mces/{MCE}/values.yaml"
    )


@pytest.mark.parametrize(
    "path", [f"{HERZI}/cluster-roles/values.yaml", f"sites/site1/prod/mces/{HIDDEN}/values.yaml"]
)
async def test_a_viewer_previews_an_edit_of_a_layer_by_the_path_they_read(
    vic: httpx.AsyncClient, path: str
) -> None:
    body = {
        "team": "redbull",
        "addon": "cluster-roles",
        "cluster": HERZI,
        "mce": SEED,
        "override_values": {"note": "x"},
        "override_path": path,
    }
    shown = ok(await vic.post("/api/day2/merge-preview", json=body))
    assert shown["merged"]["note"] == "x"
    assert shown["provenance"]["note"] == ("cluster" if path.startswith(HERZI) else "mce")


async def test_a_viewers_refused_preview_lists_no_path(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    body = {
        "team": "redbull",
        "addon": "cluster-roles",
        "cluster": HERZI,
        "override_values": {"a": 1},
        "override_path": "operators/x.yaml",
    }
    shown = problem(await vic.post("/api/day2/merge-preview", json=body), 422, "VALIDATION_ERROR")
    assert shown["details"]["rule"] == "override-path" and "have:" not in shown["detail"]
    assert "sites/" not in shown["detail"]
    admin = problem(await jane.post("/api/day2/merge-preview", json=body), 422, "VALIDATION_ERROR")
    assert f"sites/site1/prod/mces/{MCE}/values.yaml" in admin["detail"]


async def test_a_viewers_other_errors_name_their_cluster_by_its_name(
    vic: httpx.AsyncClient,
) -> None:
    body = problem(
        await vic.get(f"/api/day2/clusters/{HERZI}/addons/redbull/ghost"), 404, "NOT_FOUND"
    )
    assert body["details"]["cluster"] == HERZI and MCE not in body["detail"]


# ── R5, R6, R7: merge requests, commits, diffs ───────────────────────────────


async def test_a_viewers_merge_requests_are_about_a_tenant_or_the_hosted_clusters(
    world: World, jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    listed = ok(await vic.get("/api/day2/approvals"))
    assert {m["iid"] for m in listed} == {world.tenant_mr, world.hosted_default_mr}
    audit = {m["iid"] for m in ok(await vic.get("/api/day2/audit/merge-requests"))}
    assert {world.tenant_mr, world.hosted_default_mr} <= audit
    assert not audit & {world.mce_mr, world.hub_mr, world.upi_mr, world.kv_mr}
    tenant = ok(await vic.get(f"/api/day2/approvals/redbull/{world.tenant_mr}"))
    assert [d["new_path"] for d in tenant["diffs"]] == [f"{HERZI}/bmhgen/values.yaml"]
    assert f"ArgoCD on {HIDDEN} generates" in tenant["mr"]["description"]
    fleet = ok(await vic.get(f"/api/day2/approvals/redbull/{world.hosted_default_mr}"))
    assert [d["new_path"] for d in fleet["diffs"]] == [
        "defaults/hosted-clusters/kyverno/values.yaml"
    ]
    admin = ok(await jane.get(f"/api/day2/approvals/redbull/{world.tenant_mr}"))
    assert f"ArgoCD on {MCE} generates" in admin["mr"]["description"]
    assert [d["new_path"] for d in admin["diffs"]] == [f"{HERZI_DIR}/bmhgen/values.yaml"]


@pytest.mark.parametrize("which", ["mce_mr", "hub_mr", "upi_mr", "kv_mr", "mce_default_mr"])
async def test_a_merge_request_about_the_infrastructure_is_a_missing_one_for_a_viewer(
    world: World, vic: httpx.AsyncClient, which: str
) -> None:
    iid = getattr(world, which)
    hidden = problem(await vic.get(f"/api/day2/approvals/redbull/{iid}"), 404, "NOT_FOUND")
    missing = problem(await vic.get("/api/day2/approvals/redbull/999"), 404, "NOT_FOUND")
    assert hidden["detail"] == missing["detail"].replace("999", str(iid))


async def test_a_viewers_commits_and_diffs_are_a_tenants(
    world: World, jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    commits = ok(await vic.get("/api/day2/audit/commits"))
    assert [c["id"] for c in commits] == [world.tenant_commit]
    assert f"Cluster: hosted:site1:prod:{HIDDEN}:{KARNIOL}" in commits[0]["message"]
    diff = ok(await vic.get(f"/api/day2/audit/commits/{world.tenant_commit}/diff"))
    assert [d["new_path"] for d in diff] == [f"{KARNIOL}/bmhgen/values.yaml"]
    hidden = problem(
        await vic.get(f"/api/day2/audit/commits/{world.mce_commit}/diff"), 404, "NOT_FOUND"
    )
    assert hidden["detail"] == f"commit {world.mce_commit} is in no team repo"
    admin = ok(await jane.get(f"/api/day2/audit/commits/{world.mce_commit}/diff"))
    assert [d["new_path"] for d in admin] == [
        f"sites/site1/prep/mces/{PREP_MCE}/in-cluster/cluster-roles/values.yaml"
    ]


# ── R8, R9: lints, fleet defaults, add-on pages ──────────────────────────────


async def _broken_and_defaults(gitlab: InMemoryGitLab) -> None:
    """A broken deploy config on herzi and on an MCE; kyverno a hosted clusters and MCE default."""
    fleet = "defaults/hosted-clusters/kyverno"
    await _commit(
        gitlab,
        "redbull",
        {
            f"{HERZI_DIR}/cluster-roles/cluster-roles.yaml": "a: [\n",
            f"sites/site1/prod/mces/{MCE}/in-cluster/kyverno/kyverno.yaml": "b: [\n",
            f"sites/site1/prod/mces/{SEED}/{KV}/cluster-roles/values.yaml": "{}\n",
            f"{fleet}/values.yaml": "{}\n",
            f"{fleet}/values-prod.yaml": "{}\n",
            f"{fleet}/values-{HERZI}.yaml": "{}\n",
            f"{fleet}/values-{KV}.yaml": "{}\n",
            "defaults/hosted-clusters/exclusions.yaml": (
                f"exclusions:\n  kyverno:\n    - {KV}\n    - {HERZI}\n"
            ),
            "defaults/mces/kyverno/values.yaml": "{}\n",
        },
        "broken files and kyverno defaults",
    )


async def test_a_viewers_lints_are_about_a_tenant_or_no_destination(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    await _broken_and_defaults(gitlab)
    shown = ok(await vic.get("/api/day2/lints"))
    assert all(":" not in f["cluster"] and not f["path"].startswith("sites/") for f in shown)
    broken = [(f["cluster"], f["path"]) for f in shown if f["rule"] == "yaml-invalid"]
    assert broken == [(HERZI, f"{HERZI}/cluster-roles/cluster-roles.yaml")]
    admin = ok(await jane.get("/api/day2/lints"))
    paths = {f["path"] for f in admin if f["rule"] == "yaml-invalid"}
    assert f"sites/site1/prod/mces/{MCE}/in-cluster/kyverno/kyverno.yaml" in paths


async def test_a_viewers_fleet_defaults_are_the_hosted_clusters_reaching_tenants(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    await _broken_and_defaults(gitlab)
    shown = ok(await vic.get("/api/day2/fleet-defaults?team=redbull"))
    assert [(d["scope"], d["chart"]) for d in shown] == [("hosted-clusters", "kyverno")]
    (kyverno,) = shown
    assert HERZI in kyverno["excluded"] and KV not in kyverno["excluded"] + kyverno["reach"]
    assert all(":" not in r for r in kyverno["reach"])
    assert sorted(kyverno["tweaks"]) == [
        f"defaults/hosted-clusters/kyverno/values-{HERZI}.yaml",
        "defaults/hosted-clusters/kyverno/values-prod.yaml",
    ]
    admin = ok(await jane.get("/api/day2/fleet-defaults?team=redbull"))
    assert {d["scope"] for d in admin} == {"hosted-clusters", "mces", "hub"}
    entry = ok(await vic.get("/api/day2/addons/redbull/kyverno"))
    assert entry["fleet_defaults"] == ["hosted-clusters"]
    admin_entry = ok(await jane.get("/api/day2/addons/redbull/kyverno"))
    assert sorted(admin_entry["fleet_defaults"]) == ["hosted-clusters", "mces"]


async def test_a_viewers_add_ons_count_and_list_the_tenants_alone(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    await _broken_and_defaults(gitlab)
    listed = {a["name"]: a for a in ok(await vic.get("/api/day2/teams/redbull/addons"))}
    assert sorted(listed) == ["bmhgen", "cluster-roles", "kyverno"]
    assert [d["scope"] for d in listed["kyverno"]["defaults"]] == ["hosted-clusters"]
    every = {a["name"]: a for a in ok(await jane.get("/api/day2/teams/redbull/addons"))}
    assert every["cluster-roles"]["installed_on"] == listed["cluster-roles"]["installed_on"] + 2
    hosted = every["kyverno"]["defaults"][0]
    assert listed["kyverno"]["defaults"][0]["excluded"] == hosted["excluded"] - 1
    page = ok(await vic.get("/api/day2/teams/redbull/addons/kyverno"))
    (scope,) = page["scopes"]
    assert scope["scope"] == "hosted-clusters" and scope["unregistered"] == []
    assert scope["exclusions"]["names"] == [HERZI] and scope["exclusions"]["unknown_names"] == []
    ids = {d["id"] for d in scope["destinations"]}
    assert HERZI in ids and KV not in ids and all(":" not in i for i in ids)
    assert {d["mce"] for d in scope["destinations"]} == {None}
    herzi = next(d for d in scope["destinations"] if d["id"] == HERZI)
    assert herzi["override"]["path"] == f"defaults/hosted-clusters/kyverno/values-{HERZI}.yaml"
    assert page["catalog"]["fleet_defaults"] == ["hosted-clusters"]
    for chart in ("dhcp-api-token", "example-chart"):
        hidden = problem(await vic.get(f"/api/day2/teams/redbull/addons/{chart}"), 404, "NOT_FOUND")
        missing = problem(await vic.get("/api/day2/teams/redbull/addons/ghost"), 404, "NOT_FOUND")
        assert hidden["detail"] == missing["detail"].replace("ghost", chart)
        ok(await jane.get(f"/api/day2/teams/redbull/addons/{chart}"))


async def test_the_new_add_on_template_is_an_admins(vic: httpx.AsyncClient) -> None:
    problem(await vic.get("/api/day2/teams/redbull/addon-template"), 403, "FORBIDDEN")
