"""``/api/day1/specs`` over HTTP, in the shapes the web app reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]

WEB_SPEC = {
    # What apps/web/app/(app)/specs/new/page.tsx buildFinalSpec() sends.
    "apiVersion": "wingman.io/v1",
    "kind": "ClusterSpec",
    "metadata": {"name": "agent-mini", "description": "one pool", "version": "1.0.0", "labels": {}},
    "spec": {
        "day1": {
            "variables": [],
            "structure": {"nodepools": [{}]},
            "immutable_paths": [],
            "template": "",
        },
        "day2": {
            "addons": [
                {"team": "redbull", "name": "cluster-roles", "version": "main", "overrideable": []}
            ]
        },
    },
}


async def test_the_list_carries_the_legacy_spec_shape_and_the_template(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    specs = (await client.get("/api/day1/specs", headers=auth(support.VIEWER))).json()
    assert [s["metadata"]["name"] for s in specs] == ["agent-single", "agent-standard"]
    first = specs[0]
    assert set(first) >= {"apiVersion", "kind", "metadata", "spec", "load_error"}
    assert first["load_error"] is None
    assert first["spec"]["day1"]["template"].startswith("{#-")
    assert first["spec"]["day1"]["structure"] == {"nodepools": [{}]}


async def test_a_broken_spec_is_listed_with_its_error(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/broken.yaml", content="metadata: [\n"
    )
    specs = (await client.get("/api/day1/specs", headers=auth(support.VIEWER))).json()
    broken = next(s for s in specs if s["metadata"]["name"] == "broken")
    assert broken["load_error"]
    assert broken["load_problems"]


async def test_one_spec_and_its_errors(client: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    headers = auth(support.VIEWER)
    spec = (await client.get("/api/day1/specs/agent-standard", headers=headers)).json()
    assert spec["spec"]["day2"]["addons"][0]["name"] == "cluster-roles"
    missing = await client.get("/api/day1/specs/nope", headers=headers)
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


async def test_versions_template_and_schema(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    headers = auth(support.VIEWER)
    gone = await client.get("/api/day1/specs/versions/openshift", headers=headers)
    assert gone.status_code == 404  # each MCE's upgrade/ files say it now (ADR-0034)
    template = (await client.get("/api/day1/specs/template", headers=headers)).json()
    assert isinstance(template, str)
    assert "nodepool:" in template
    schema = (await client.get("/api/day1/specs/template/schema", headers=headers)).json()
    names = [f["name"] for f in schema]
    assert "openshift_release_version" not in names
    nodepools = next(f for f in schema if f["name"] == "nodepools")
    assert nodepools["type"] == "list"
    assert "default" not in schema[0]  # an absent default is omitted, as before
    full = (
        await client.get("/api/day1/specs/template/schema?include_reserved=true", headers=headers)
    ).json()
    assert "openshift_release_version" in [f["name"] for f in full]


async def test_create_update_and_delete_open_spec_mrs(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    created = await client.post("/api/day1/specs", json=WEB_SPEC, headers=alice)
    assert created.status_code == 201, created.text
    mr = created.json()
    assert mr["title"] == "[Wingman/Specs] Create spec agent-mini"
    assert mr["labels"] == ["create", "specs", "wingman"]
    assert mr["repo"] == "specs"
    pid = await support.project_id(gitlab, support.SPECS)
    stored = yaml.safe_load(gitlab.snapshot(pid, mr["source_branch"])["specs/agent-mini.yaml"])
    assert "template" not in stored["spec"]["day1"]
    assert stored["metadata"]["name"] == "agent-mini"

    again = await client.post(
        "/api/day1/specs", json={**WEB_SPEC, "metadata": {"name": "agent-single"}}, headers=alice
    )
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_EXISTS")

    renamed = await client.put("/api/day1/specs/agent-single", json=WEB_SPEC, headers=alice)
    assert (renamed.status_code, renamed.json()["code"]) == (422, "VALIDATION_ERROR")

    update = {**WEB_SPEC, "metadata": {"name": "agent-single", "version": "1.1.0"}}
    read = (await client.get("/api/day1/specs/agent-single", headers=alice)).json()
    file = await gitlab.read_file(pid, RepoPath("specs/agent-single.yaml"), "main")
    assert read["last_commit_id"] == file.last_commit_id
    listed = (await client.get("/api/day1/specs", headers=alice)).json()
    assert {s["metadata"]["name"]: s["last_commit_id"] for s in listed}["agent-single"] == (
        file.last_commit_id
    )
    fresh = await client.put(
        "/api/day1/specs/agent-single",
        params={"last_commit_id": read["last_commit_id"]},
        json=update,
        headers=alice,
    )
    assert fresh.status_code == 200, fresh.text
    stale = await client.put(
        "/api/day1/specs/agent-single",
        params={"last_commit_id": "0" * 40},
        json=update,
        headers=alice,
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "REVISION_CONFLICT")
    updated = await client.put("/api/day1/specs/agent-single", json=update, headers=alice)
    assert updated.json()["title"] == "[Wingman/Specs] Update spec agent-single to v1.1.0"

    deleted = await client.delete("/api/day1/specs/agent-single", headers=alice)
    assert deleted.json()["title"] == "[Wingman/Specs] Delete spec agent-single"


async def test_an_invalid_spec_body_is_refused(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    bad = {**WEB_SPEC, "metadata": {"name": "Not A Label", "version": "1"}}
    response = await client.post("/api/day1/specs", json=bad, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    extra = {**WEB_SPEC, "surprise": True}
    response = await client.post("/api/day1/specs", json=extra, headers=auth(support.ALICE))
    assert response.status_code == 422


async def test_history_and_the_text_at_a_commit(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    headers = auth(support.VIEWER)
    history = (await client.get("/api/day1/specs/agent-single/history", headers=headers)).json()
    assert set(history[0]) == {"sha", "short_sha", "message", "author", "date", "web_url"}
    text = await client.get(f"/api/day1/specs/agent-single/at/{history[0]['sha']}", headers=headers)
    assert text.headers["content-type"].startswith("text/plain")
    assert "name: agent-single" in text.text
    bad = await client.get("/api/day1/specs/agent-single/at/not-hex!", headers=headers)
    assert bad.status_code == 422


async def test_a_specs_clusters_and_their_drift(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    mr = (await client.post("/api/day1/clusters", json=support.create_body(), headers=alice)).json()
    detail = (await client.get(f"/api/day1/approvals/{mr['iid']}", headers=bob)).json()
    await client.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": detail["mr"]["sha"]}, headers=bob
    )
    clusters = (await client.get("/api/day1/specs/agent-standard/clusters", headers=bob)).json()
    assert clusters == [
        {
            "name": "ocp4-prod-falcon-site1",
            "site": "site1",
            "mce": "ocp4-prod-mce-site1-a",
            "phase": "Unknown",
            "state": "drifted",
            "is_drifted": True,
            "error": None,
        }
    ]
    drift = (await client.get("/api/day1/specs/agent-standard/drift", headers=bob)).json()
    assert drift[0]["cluster"] == "ocp4-prod-falcon-site1"
    assert drift[0]["spec_version"] == "1.0.0"
