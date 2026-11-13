"""Add-on authoring and per-team access through HTTP (the 2026-11-12 authoring API note)."""

from __future__ import annotations

from typing import Any

import httpx

from wingman_day2.settings import FAKE_GITLAB_URL

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id", "details"}
MANUAL = {
    "auto_sync": False,
    "prune": False,
    "self_heal": False,
    "sync_options": ["CreateNamespace=true"],
}
AUTO = {
    "auto_sync": True,
    "prune": False,
    "self_heal": True,
    "sync_options": ["CreateNamespace=true"],
}
NEW = {
    "name": "podinfo",
    "repourl": f"{FAKE_GITLAB_URL}/helm-charts/example-chart.git",
    "project_namespace": "podinfo",
    "sync": MANUAL,
}
HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"


def ok(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def confirmed(
    client: httpx.AsyncClient, method: str, url: str, body: dict[str, Any], status: int = 200
) -> Any:
    """Preview a write, then send the same body confirming what the preview showed."""
    plan = ok(await client.request(method, url, params={"dry_run": "true"}, json=body))
    confirm = {"confirm_changes": plan["needs_confirmation"], "expected_digest": plan["digest"]}
    return ok(await client.request(method, url, json={**body, **confirm}), status)


def problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == PROBLEM_KEYS and (body["status"], body["code"]) == (status, code)
    return body


async def test_teams_say_whether_wingman_may_write_there(jane: httpx.AsyncClient) -> None:
    teams = {t["name"]: t for t in ok(await jane.get("/api/day2/teams"))}
    assert {n: t["writable"] for n, t in teams.items()} == {
        "falcon": True,
        "lynx": True,
        "orca": False,
        "redbull": True,
    }
    orca = ok(await jane.get("/api/day2/teams/orca"))
    assert orca == teams["orca"]
    assert (orca["access_level"], orca["access_role"]) == (20, "reporter")
    assert orca["read_only_reason"].startswith("orca hasn't given Wingman write access")
    assert teams["redbull"]["read_only_reason"] is None
    entries = ok(await jane.get("/api/day2/addons", params={"team": "orca"}))
    assert {e["writable"] for e in entries} == {False}
    problem(await jane.get("/api/day2/teams/ghost"), 404, "NOT_FOUND")


async def test_a_read_only_teams_writes_are_403_before_any_other_check(
    jane: httpx.AsyncClient,
) -> None:
    writes = [
        jane.post("/api/day2/addons/orca", json={**NEW, "repourl": "not a url"}),
        jane.put("/api/day2/addons/orca/metrics", json={"sync": AUTO}),
        jane.post("/api/day2/addons/orca/metrics/defaults/hosted-clusters", json={}),
        jane.put("/api/day2/addons/orca/metrics/defaults/upi", json={"values": {"a": 1}}),
        jane.post("/api/day2/clusters/ocp4-dok-site1/addons/orca/metrics", json={}),
        jane.post("/api/day2/approvals/orca/1/reject"),
    ]
    for write in writes:
        body = problem(await write, 403, "TEAM_READ_ONLY")
        assert body["type"] == "/problems/team-read-only"
        assert body["details"] == {
            "team": "orca",
            "project": "sigs/orca",
            "access_level": 20,
            "access_role": "reporter",
            "required_level": 30,
        }


async def test_the_template_pre_fills_a_new_addon(jane: httpx.AsyncClient) -> None:
    body = ok(await jane.get("/api/day2/teams/redbull/addon-template"))
    assert body["sync"] == MANUAL and body["writable"] is True
    assert body["repourl_prefix"] == f"{FAKE_GITLAB_URL}/helm-charts/"
    assert "ServerSideApply=true" in body["known_sync_options"]
    assert [s["scope"] for s in body["scopes"]] == ["hosted-clusters", "mces", "hub", "upi"]
    assert body["scopes"][0]["label"] == "every hosted cluster"


async def test_create_dry_run_then_real(jane: httpx.AsyncClient) -> None:
    plan = ok(await jane.post("/api/day2/addons/redbull", params={"dry_run": "true"}, json=NEW))
    assert plan["action"] == "create-addon" and plan["title"].startswith("[Wingman/Day2] Create")
    assert [(f["action"], f["path"], f["previous"]) for f in plan["files"]] == [
        ("create", "operators/podinfo/podinfo.yaml", None),
        ("create", "operators/podinfo/values.yaml", None),
    ]
    assert "repourl:" in plan["files"][0]["content"]
    assert ok(await jane.get("/api/day2/approvals")) == []
    change = ok(await jane.post("/api/day2/addons/redbull", json=NEW), 201)
    assert (change["team"], change["chart"], change["scope"]) == ("redbull", "podinfo", None)
    assert change["iid"] == 1 and change["files"][0] == {
        "action": "create",
        "path": "operators/podinfo/podinfo.yaml",
    }
    problem(
        await jane.post("/api/day2/addons/redbull", json={**NEW, "name": "bmhgen"}),
        409,
        "ALREADY_EXISTS",
    )
    bad = problem(
        await jane.post("/api/day2/addons/redbull", json={**NEW, "target_revision": "9.9.9"}),
        422,
        "VALIDATION_ERROR",
    )
    assert bad["details"]["rule"] == "revision-unknown"


async def test_an_existing_add_on_is_refused_with_its_sig_values_named(
    jane: httpx.AsyncClient,
) -> None:
    # ADR-0043's amendment: day2's messages say Sig values, as the UI does, since 3.20.1.
    exists = problem(
        await jane.post("/api/day2/addons/redbull", json={**NEW, "name": "bmhgen"}),
        409,
        "ALREADY_EXISTS",
    )
    assert exists["detail"] == "redbull has operators/bmhgen/ already; edit its Sig values instead"
    assert exists["details"]["rule"] == "addon-exists"
    assert "team default" not in str(exists).lower()


async def test_writes_are_admin_only(vic: httpx.AsyncClient) -> None:
    problem(await vic.post("/api/day2/addons/redbull", json=NEW), 403, "FORBIDDEN")
    assert ok(await vic.get("/api/day2/fleet-defaults"))


async def test_team_default_edit_sends_only_what_changed(jane: httpx.AsyncClient) -> None:
    entry = ok(await jane.get("/api/day2/addons/redbull/bmhgen"))
    assert entry["sync"] == MANUAL and entry["deploy_config_exists"] is True
    assert entry["last_commit_id"] and entry["ignore_differences"] is None
    url = "/api/day2/addons/redbull/bmhgen"
    body = {"sync": AUTO, "last_commit_id": entry["last_commit_id"]}
    refused = problem(await jane.put(url, json=body), 422, "VALIDATION_ERROR")
    assert refused["details"]["rule"] == "confirm-changes"
    change = await confirmed(jane, "PUT", url, body)
    assert change["action"] == "update-default" and change["files"] == [
        {"action": "update", "path": "operators/bmhgen/bmhgen.yaml"}
    ]
    assert change["title"] == "[Wingman/Day2] Update addon redbull/bmhgen Sig values"


async def test_make_default_dry_run_shows_the_moves_and_the_confirmation(
    jane: httpx.AsyncClient,
) -> None:
    url = "/api/day2/addons/redbull/cluster-roles/defaults/hosted-clusters"
    plan = ok(await jane.post(url, params={"dry_run": "true"}, json={"values": {"a": 1}}))
    assert len(plan["adopted"]) == 4 and len(plan["needs_confirmation"]) == 4
    herzi = next(a for a in plan["adopted"] if a["cluster"] == HERZI)
    assert herzi["changes"] == [
        {"stack": "values", "key": "a", "before": None, "after": 1, "after_null": False}
    ]
    assert herzi["exclusion_removed"] is False
    assert herzi["gitkeep"].endswith("ocp4-prod-herzi-site1/.gitkeep") and herzi["moved"] == []
    refused = problem(await jane.post(url, json={"values": {"a": 1}}), 422, "VALIDATION_ERROR")
    assert refused["details"]["rule"] == "confirm-changes"
    assert sorted(refused["details"]["needs_confirmation"]) == sorted(plan["needs_confirmation"])
    unseen = problem(
        await jane.post(
            url, json={"values": {"a": 1}, "confirm_changes": plan["needs_confirmation"]}
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert unseen["details"]["rule"] == "confirm-against-preview"
    change = ok(
        await jane.post(
            url,
            json={
                "values": {"a": 1},
                "confirm_changes": plan["needs_confirmation"],
                "expected_digest": plan["digest"],
            },
        ),
        201,
    )
    assert change["action"] == "make-default" and change["scope"] == "hosted-clusters"
    assert len(change["reach"]) == 4


async def test_fleet_defaults_list_and_edit(jane: httpx.AsyncClient) -> None:
    found = {
        (d["chart"], d["scope"]): d
        for d in ok(await jane.get("/api/day2/fleet-defaults", params={"team": "redbull"}))
    }
    token = found[("dhcp-api-token", "mces")]
    assert token["scope_label"] == "every MCE" and token["in_catalog"] is False
    assert token["sync"]["prune"] is True and token["sync_overridden"] is True
    url = "/api/day2/addons/redbull/dhcp-api-token/defaults/mces"
    plan = ok(
        await jane.put(
            url,
            params={"dry_run": "true"},
            json={"sync": {**AUTO, "prune": False}, "last_commit_id": token["last_commit_id"]},
        )
    )
    (file,) = plan["files"]
    assert file["action"] == "update" and "# prune: true so" in file["content"]
    assert file["previous"] != file["content"]
    inherit = await confirmed(
        jane, "PUT", "/api/day2/addons/redbull/example-chart/defaults/mces", {"sync": None}
    )
    assert inherit["title"] == (
        "[Wingman/Day2] Update addon redbull/example-chart fleet default on every MCE"
    )
    nothing = problem(await jane.put(url, json={}), 422, "VALIDATION_ERROR")
    assert nothing["details"]["rule"] == "no-change"
    problem(
        await jane.put("/api/day2/addons/redbull/bmhgen/defaults/mces", json={"values": {}}),
        404,
        "NOT_FOUND",
    )
