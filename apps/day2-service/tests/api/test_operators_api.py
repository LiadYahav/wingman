"""The add-on detail API through HTTP (``docs/notes/2026-11-12-operators-page-api.md``)."""

from __future__ import annotations

from typing import Any

import httpx

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id", "details"}
PREP = "mce:site1:prep:ocp4-prep-mce-site1-a"
PROD = "mce:site1:prod:ocp4-prod-mce-site1-a"
TOKEN = "/api/day2/addons/redbull/dhcp-api-token/defaults/mces"
PREP_IN_CLUSTER = "sites/site1/prep/mces/ocp4-prep-mce-site1-a/in-cluster"
EXAMPLE = "/api/day2/addons/redbull/example-chart/defaults/mces"


def ok(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == PROBLEM_KEYS and (body["status"], body["code"]) == (status, code)
    return body


async def preview(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    return ok(await client.put(url, params={"dry_run": "true"}, json=body))


async def test_the_operators_list_has_the_catalog_and_defaults_outside_it(
    vic: httpx.AsyncClient,
) -> None:
    found = {o["name"]: o for o in ok(await vic.get("/api/day2/teams/redbull/operators"))}
    assert sorted(found) == [
        "bmhgen",
        "cluster-roles",
        "dhcp-api-token",
        "example-chart",
        "kyverno",
    ]
    token = found["dhcp-api-token"]
    assert token["in_catalog"] is False and token["repourl"] == ""
    assert token["defaults"] == [{"scope": "mces", "label": "every MCE", "reach": 1, "excluded": 1}]
    roles = found["cluster-roles"]
    assert roles["in_catalog"] and roles["defaults"] == [] and roles["installed_on"] == 5
    assert roles["writable"] is True and roles["read_only_reason"] is None
    problem(await vic.get("/api/day2/teams/ghost/operators"), 404, "NOT_FOUND")


async def test_an_operator_page_shows_each_scope_and_each_destination(
    vic: httpx.AsyncClient,
) -> None:
    body = ok(await vic.get("/api/day2/teams/redbull/operators/dhcp-api-token"))
    assert body["in_catalog"] is False and body["catalog"] is None
    assert body["deploy_config"]["exists"] is False and body["deploy_config"]["text"] is None
    scopes = {s["scope"]: s for s in body["scopes"]}
    assert list(scopes) == ["hosted-clusters", "mces", "hub", "upi"]
    mces = scopes["mces"]
    assert mces["is_default"] and mces["folder"] == "defaults/mces/dhcp-api-token"
    assert "# " in mces["deploy_config"]["text"] and mces["sync_overridden"]
    exclusions = mces["exclusions"]
    # Read as the platform reads it; Wingman never writes it (ADR-0053's amendment).
    assert exclusions["names"] == ["ocp4-prep-mce-site1-a"] and "editable" not in exclusions
    assert exclusions["last_commit_id"] and exclusions["unknown_names"] == []
    states = {d["id"]: (d["state"], d["deployed"], d["app_name"]) for d in mces["destinations"]}
    assert states == {
        PREP: ("excluded", False, None),
        PROD: ("default", True, "redbull-in-cluster-dhcp-api-token-deploy"),
    }
    prod = next(d for d in mces["destinations"] if d["id"] == PROD)
    assert (
        prod["override"]["path"] == "defaults/mces/dhcp-api-token/values-ocp4-prod-mce-site1-a.yaml"
    )
    assert prod["override"]["exists"] is False and prod["override"]["last_commit_id"] is None
    assert prod["own_folder"] is None and prod["own_deploy"] is None
    assert prod["override_shared_with"] == []
    assert "mce:site2:prod:ocp4-prod-mce-site2-a" in [u["id"] for u in mces["unregistered"]]
    assert scopes["hub"]["exclusions"] is None and not scopes["hub"]["is_default"]
    assert scopes["hub"]["destinations"][0]["state"] == "none"
    roles = ok(await vic.get("/api/day2/teams/redbull/operators/cluster-roles"))
    hosted = next(s for s in roles["scopes"] if s["scope"] == "hosted-clusters")
    assert {d["state"] for d in hosted["destinations"]} == {"own-folder"}
    assert roles["catalog"]["name"] == "cluster-roles" and roles["values_file"]["exists"]
    problem(await vic.get("/api/day2/teams/redbull/operators/ghost"), 404, "NOT_FOUND")


async def test_values_for_one_mce_are_previewed_then_confirmed_against_the_digest(
    jane: httpx.AsyncClient,
) -> None:
    url = f"{TOKEN}/destinations/{PROD}/values"
    body = {"values": {"note": "x"}}
    plan = await preview(jane, url, body)
    assert plan["action"] == "override-values" and plan["needs_confirmation"] == [PROD]
    refused = problem(await jane.put(url, json=body), 422, "VALIDATION_ERROR")
    assert refused["details"]["rule"] == "confirm-changes"
    stale = problem(
        await jane.put(url, json={**body, "confirm_changes": [PROD], "expected_digest": "0" * 64}),
        409,
        "REVISION_CONFLICT",
    )
    assert stale["details"]["rule"] == "plan-changed"
    assert stale["details"]["digest"] == plan["digest"]
    change = ok(
        await jane.put(
            url, json={**body, "confirm_changes": [PROD], "expected_digest": plan["digest"]}
        )
    )
    assert change["title"].startswith("[Wingman/Day2] Override addon redbull/dhcp-api-token values")
    assert change["iid"] == 1 and change["digest"] == plan["digest"]


async def test_no_exclusion_or_own_deploy_write_is_served(jane: httpx.AsyncClient) -> None:
    for url, body in [
        (f"{TOKEN}/exclusions", {"excluded": [PREP]}),
        (f"{EXAMPLE}/destinations/{PROD}/deploy", {"deploy": {"project_namespace": "x"}}),
    ]:
        assert (await jane.put(url, json=body)).status_code in (404, 405), url


async def test_overrides_for_one_destination(jane: httpx.AsyncClient) -> None:
    values = await preview(jane, f"{EXAMPLE}/destinations/{PROD}/values", {"values": {"r": 3}})
    assert values["action"] == "override-values"
    assert [f["path"] for f in values["files"]] == [
        "defaults/mces/example-chart/values-ocp4-prod-mce-site1-a.yaml"
    ]
    assert values["impact"][0]["changes"] == [
        {"stack": "values", "key": "r", "before": None, "after": 3, "after_null": False}
    ]
    hub = problem(
        await jane.put(
            "/api/day2/addons/redbull/example-chart/defaults/hub/destinations/hub/values",
            json={"values": {"a": 1}},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert hub["details"]["rule"] == "override-scope"
    unknown = problem(
        await jane.put(f"{EXAMPLE}/destinations/hub/values", json={"values": {"a": 1}}),
        422,
        "VALIDATION_ERROR",
    )
    assert unknown["details"]["rule"] == "destination-unknown"


async def test_deploy_on_specific_mces_opens_one_mr_per_mce(jane: httpx.AsyncClient) -> None:
    url = "/api/day2/addons/redbull/cluster-roles/mce-installs"
    body = {"clusters": [PREP, PROD], "values": {"tier": "hub"}}
    planned = ok(await jane.post(url, params={"dry_run": "true"}, json=body))
    assert [(i["cluster"], i["status"]) for i in planned["installs"]] == [
        (PREP, "planned"),
        (PROD, "planned"),
    ]
    assert planned["installs"][0]["files"] == [
        {
            "action": "create",
            "path": f"{PREP_IN_CLUSTER}/cluster-roles/values.yaml",
        }
    ]
    assert ok(await jane.get("/api/day2/approvals")) == []
    opened = ok(await jane.post(url, json=body), 201)
    assert [i["status"] for i in opened["installs"]] == ["opened", "opened"]
    titles = sorted(i["merge_request"]["title"] for i in opened["installs"])
    assert titles == [
        "[Wingman/Day2] Install addon redbull/cluster-roles on ocp4-prep-mce-site1-a",
        "[Wingman/Day2] Install addon redbull/cluster-roles on ocp4-prod-mce-site1-a",
    ]
    again = ok(await jane.post(url, params={"dry_run": "true"}, json=body))
    assert {i["status"] for i in again["installs"]} == {"planned"}
    hosted = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
    bad = problem(await jane.post(url, json={"clusters": [hosted]}), 422, "VALIDATION_ERROR")
    assert bad["details"]["rule"] == "not-an-mce"


async def test_an_installed_mce_is_refused_on_its_own(jane: httpx.AsyncClient) -> None:
    body = {"clusters": [PROD]}
    result = ok(
        await jane.post(
            "/api/day2/addons/redbull/bmhgen/mce-installs", params={"dry_run": "true"}, json=body
        )
    )
    (install,) = result["installs"]
    assert (install["status"], install["rule"]) == ("refused", "installed")
    assert install["merge_request"] is None and install["detail"]


async def test_the_writes_are_admin_only_and_refused_for_a_read_only_team(
    jane: httpx.AsyncClient, vic: httpx.AsyncClient
) -> None:
    problem(
        await vic.put(f"{EXAMPLE}/destinations/{PROD}/values", json={"values": {"a": 1}}),
        403,
        "FORBIDDEN",
    )
    problem(
        await vic.post(
            "/api/day2/addons/redbull/cluster-roles/mce-installs", json={"clusters": [PROD]}
        ),
        403,
        "FORBIDDEN",
    )
    problem(
        await jane.post("/api/day2/addons/orca/metrics/mce-installs", json={"clusters": [PROD]}),
        403,
        "TEAM_READ_ONLY",
    )


async def test_the_addons_paths_and_the_3_12_operators_aliases_answer_the_same(
    vic: httpx.AsyncClient,
) -> None:
    listed = ok(await vic.get("/api/day2/teams/redbull/addons"))
    assert listed == ok(await vic.get("/api/day2/teams/redbull/operators"))
    detail = ok(await vic.get("/api/day2/teams/redbull/addons/dhcp-api-token"))
    assert detail == ok(await vic.get("/api/day2/teams/redbull/operators/dhcp-api-token"))
    assert detail["name"] == "dhcp-api-token"
    problem(await vic.get("/api/day2/teams/redbull/addons/ghost"), 404, "NOT_FOUND")
