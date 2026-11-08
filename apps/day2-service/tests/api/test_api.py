"""The HTTP API end to end, through ASGI, against the in-memory GitLab seeded from the fixtures."""

from __future__ import annotations

from typing import Any

import httpx

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
PROD_MCE = "mce:site1:prod:ocp4-prod-mce-site1-a"
HERZI_DIR = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1"
BMHGEN_VALUES = f"{HERZI_DIR}/bmhgen/values.yaml"
PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id", "details"}


def problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) == PROBLEM_KEYS
    assert (body["status"], body["code"]) == (status, code)
    assert body["request_id"] and body["instance"] == response.request.url.path
    return body


def ok(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def install(
    client: httpx.AsyncClient,
    team: str,
    chart: str,
    body: dict[str, Any] | None = None,
    cluster: str = "ocp4-prod-herzi-site1",
) -> httpx.Response:
    return await client.post(f"/api/day2/clusters/{cluster}/addons/{team}/{chart}", json=body or {})


async def installed(client: httpx.AsyncClient, cluster: str) -> dict[str, dict[str, Any]]:
    body = ok(await client.get(f"/api/day2/clusters/{cluster}/addons"))
    return {f"{item['team']}/{item['name']}": item for item in body["installed"]}


async def approve(client: httpx.AsyncClient, team: str, iid: int, sha: str) -> httpx.Response:
    return await client.post(f"/api/day2/approvals/{team}/{iid}/approve", json={"sha": sha})


async def project_id(gitlab: InMemoryGitLab, path: str) -> int:
    return (await gitlab.get_project(path)).id


# ── auth and errors ─────────────────────────────────────────────────────────


async def test_a_request_without_a_token_is_401_problem(anonymous: httpx.AsyncClient) -> None:
    problem(await anonymous.get("/api/day2/clusters"), 401, "UNAUTHORIZED")


async def test_a_viewer_reads_but_cannot_write(vic: httpx.AsyncClient) -> None:
    ok(await vic.get("/api/day2/clusters"))
    base = "/api/day2/clusters/ocp4-prod-herzi-site1/addons/redbull/cluster-roles"
    problem(await vic.post(base, json={}), 403, "FORBIDDEN")
    problem(await vic.put(base, json={}), 403, "FORBIDDEN")
    problem(await vic.delete(base), 403, "FORBIDDEN")
    problem(
        await vic.post("/api/day2/approvals/redbull/1/approve", json={"sha": "a" * 40}),
        403,
        "FORBIDDEN",
    )


async def test_errors_are_rfc9457_problems(jane: httpx.AsyncClient) -> None:
    problem(await jane.get("/api/day2/clusters/no-such-cluster"), 404, "NOT_FOUND")
    problem(await jane.get("/api/day2/clusters/hosted:x"), 422, "VALIDATION_ERROR")
    problem(await jane.get("/api/day2/addons?team=nope"), 404, "NOT_FOUND")
    body = problem(
        await install(jane, "redbull", "bmhgen", {"override_values": {}, "bogus": 1}),
        422,
        "VALIDATION_ERROR",
    )
    assert any("bogus" in e["loc"] for e in body["details"]["errors"])
    problem(await install(jane, "nope", "bmhgen"), 404, "NOT_FOUND")


async def test_a_bare_name_resolves_when_unique_and_mce_narrows_it(
    jane: httpx.AsyncClient,
) -> None:
    body = ok(await jane.get("/api/day2/clusters/ocp4-prod-herzi-site1?mce=ocp4-prod-mce-site1-a"))
    assert body["id"] == HERZI
    problem(await jane.get("/api/day2/clusters/ocp4-prod-herzi-site1?mce=other"), 404, "NOT_FOUND")


async def test_an_ambiguous_bare_name_lists_the_candidate_ids(
    jane: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    # In redbull, which also places herzi as a hosted cluster: name reuse is checked per repo.
    await gitlab.commit(
        await project_id(gitlab, "sigs/redbull"),
        branch="main",
        message="a UPI folder reusing a hosted-cluster name",
        changes=[
            FileChange.create(
                RepoPath("sites/site1/prod/upi/ocp4-prod-herzi-site1/cluster-roles/values.yaml"),
                "{}\n",
            )
        ],
    )
    body = problem(
        await jane.get("/api/day2/clusters/ocp4-prod-herzi-site1"), 422, "VALIDATION_ERROR"
    )
    assert body["details"]["candidates"] == [HERZI, "upi:site1:prod:ocp4-prod-herzi-site1"]
    ok(await jane.get(f"/api/day2/clusters/{HERZI}"))
    upi = ok(await jane.get("/api/day2/clusters/upi:site1:prod:ocp4-prod-herzi-site1"))
    assert "upi-name-reused" in {w["rule"] for w in upi["warnings"]}


# ── the whole flow on one hosted cluster ────────────────────────────────────


async def test_install_approve_update_and_remove_on_a_hosted_cluster(
    jane: httpx.AsyncClient, bob: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    change = ok(await install(jane, "redbull", "bmhgen", {"override_values": {"replicas": 2}}), 201)
    assert change["title"] == "[Wingman/Day2] Install addon redbull/bmhgen on ocp4-prod-herzi-site1"
    assert set(change["labels"]) == {"wingman", "day2", "install"}
    assert change["files"] == [{"action": "create", "path": BMHGEN_VALUES}]
    assert change["cluster"] == HERZI and change["team"] == "redbull"
    assert change["app_names"] == ["redbull-ocp4-prod-herzi-site1-bmhgen-deploy"]
    assert any("manual-sync" in note for note in change["notes"])
    assert change["author"]["username"] == "jane"

    pending = ok(await jane.get("/api/day2/approvals"))
    assert [(p["team"], p["iid"], p["author"]["username"]) for p in pending] == [
        ("redbull", change["iid"], "jane")
    ]
    problem(await approve(jane, "redbull", change["iid"], change["sha"]), 403, "SELF_APPROVAL")
    merged = ok(await approve(bob, "redbull", change["iid"], change["sha"]))
    assert merged["state"] == "merged"
    # The requester, not the service account that opened the MR or bob who merged it.
    assert (merged["author"]["username"], merged["gitlab_author"]) == ("jane", "wingman-bot")
    assert ok(await jane.get("/api/day2/approvals")) == []

    charts = await installed(jane, HERZI)
    assert charts["redbull/bmhgen"]["source"] == "cluster"
    assert charts["redbull/bmhgen"]["override_values"] == {"replicas": 2}
    assert (await installed(jane, "ocp4-prod-herzi-site1")).keys() == charts.keys()

    preview = ok(await jane.get(f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen"))
    assert preview["merged"]["replicas"] == 2
    assert preview["provenance"]["replicas"] == "cluster"
    assert preview["cluster_values"] == {"replicas": 2} and preview["installed"] is True

    read_at = charts["redbull/bmhgen"]["last_commit_id"]
    updated = ok(
        await jane.put(
            f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen",
            json={"override_values": {"replicas": 3}, "last_commit_id": read_at},
        )
    )
    assert updated["title"].startswith("[Wingman/Day2] Update addon redbull/bmhgen")
    assert updated["files"] == [{"action": "update", "path": BMHGEN_VALUES}]

    redbull = await project_id(gitlab, "sigs/redbull")
    await gitlab.commit(
        redbull,
        branch="main",
        message="someone else",
        changes=[FileChange.update(RepoPath(BMHGEN_VALUES), "replicas: 9\n", last_commit_id=None)],
    )
    problem(
        await jane.put(
            f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen",
            json={"override_values": {"replicas": 4}, "last_commit_id": read_at},
        ),
        409,
        "REVISION_CONFLICT",
    )

    removal = ok(await jane.delete(f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen"))
    assert (
        removal["title"] == "[Wingman/Day2] Remove addon redbull/bmhgen from ocp4-prod-herzi-site1"
    )
    assert removal["files"] == [{"action": "delete", "path": BMHGEN_VALUES}]
    assert any("keeps running" in note for note in removal["notes"])
    assert ok(await approve(bob, "redbull", removal["iid"], removal["sha"]))["state"] == "merged"
    assert "redbull/bmhgen" not in await installed(jane, HERZI)
    assert "redbull/cluster-roles" in await installed(jane, HERZI)


# ── refusals ────────────────────────────────────────────────────────────────


async def test_installing_a_fleet_default_into_a_cluster_folder_is_refused(
    jane: httpx.AsyncClient,
) -> None:
    body = problem(
        await install(jane, "falcon", "mce-agent", cluster=PROD_MCE), 409, "ALREADY_EXISTS"
    )
    assert body["details"]["rule"] == "xor"
    assert body["details"]["fleet_default"] == "defaults/mces/mce-agent"
    assert ok(await jane.get("/api/day2/approvals")) == []


async def test_a_miscased_repourl_is_flagged_and_an_install_without_one_refused(
    jane: httpx.AsyncClient,
) -> None:
    body = problem(await install(jane, "redbull", "kyverno"), 422, "VALIDATION_ERROR")
    assert body["details"]["rule"] == "repourl-missing"
    kyverno = (await installed(jane, PROD_MCE))["redbull/kyverno"]
    assert kyverno["deploy"]["repo_url"] == ""
    assert {"repourl-miscased", "repourl-missing"} <= {w["rule"] for w in kyverno["warnings"]}
    fixed = ok(
        await install(
            jane, "redbull", "kyverno", {"repourl": "http://gitlab.fake/helm-charts/kyverno.git"}
        ),
        201,
    )
    assert {f["path"].rsplit("/", 1)[-1] for f in fixed["files"]} == {"kyverno.yaml", "values.yaml"}


async def test_a_per_cluster_version_needs_an_explicit_emergency_pin(
    jane: httpx.AsyncClient,
) -> None:
    body = problem(
        await install(jane, "redbull", "bmhgen", {"version": "1.0.0"}), 422, "VALIDATION_ERROR"
    )
    assert body["details"] | {"inherited": "HEAD", "requested": "1.0.0"} == body["details"]
    assert body["details"]["rule"] == "emergency-pin-required"
    same = ok(await install(jane, "redbull", "bmhgen", {"version": "HEAD"}), 201)
    assert [f["path"] for f in same["files"]] == [BMHGEN_VALUES]


async def test_an_emergency_pin_writes_the_deploy_config_and_warns(
    jane: httpx.AsyncClient,
) -> None:
    change = ok(
        await install(jane, "redbull", "bmhgen", {"version": "1.0.0", "emergency_pin": True}),
        201,
    )
    assert f"{HERZI_DIR}/bmhgen/bmhgen.yaml" in [f["path"] for f in change["files"]]
    assert "emergency-pin" in {w["rule"] for w in change["warnings"]}


async def test_bulk_install_opens_one_mr_per_team(jane: httpx.AsyncClient) -> None:
    body = ok(
        await jane.post(
            f"/api/day2/clusters/{HERZI}/addons/bulk",
            json={
                "addons": [
                    {"team": "redbull", "addon": "bmhgen", "override_values": {"a": 1}},
                    {"team": "orca", "addon": "metrics"},
                ],
                "custom_message": "rollout",
            },
        ),
        201,
    )
    assert sorted(mr["team"] for mr in body["merge_requests"]) == ["orca", "redbull"]
    assert body["failed"] == []
    assert all("rollout" in mr["description"] for mr in body["merge_requests"])
    assert len(ok(await jane.get("/api/day2/approvals"))) == 2


async def test_a_bulk_install_with_one_bad_item_opens_nothing(jane: httpx.AsyncClient) -> None:
    body = problem(
        await jane.post(
            f"/api/day2/clusters/{HERZI}/addons/bulk",
            json={
                "addons": [
                    {"team": "redbull", "addon": "bmhgen"},
                    {"team": "redbull", "addon": "kyverno"},
                ]
            },
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert body["details"]["rule"] == "bulk"
    assert [p["chart"] for p in body["details"]["problems"]] == ["kyverno"]
    assert ok(await jane.get("/api/day2/approvals")) == []


# ── approvals by (team, iid) ────────────────────────────────────────────────


async def test_two_teams_own_mr_1_and_approving_one_leaves_the_other(
    jane: httpx.AsyncClient, bob: httpx.AsyncClient
) -> None:
    redbull = ok(await install(jane, "redbull", "bmhgen"), 201)
    orca = ok(await install(jane, "orca", "metrics"), 201)
    assert redbull["iid"] == orca["iid"] == 1
    assert redbull["project_id"] != orca["project_id"]
    assert ok(await approve(bob, "orca", 1, orca["sha"]))["state"] == "merged"
    assert ok(await jane.get("/api/day2/approvals/redbull/1"))["mr"]["state"] == "opened"
    assert [p["team"] for p in ok(await jane.get("/api/day2/approvals"))] == ["redbull"]


async def test_an_approval_of_a_moved_branch_is_a_conflict(
    jane: httpx.AsyncClient, bob: httpx.AsyncClient
) -> None:
    change = ok(await install(jane, "redbull", "bmhgen"), 201)
    problem(await approve(bob, "redbull", change["iid"], "f" * 40), 409, "REVISION_CONFLICT")


async def test_an_edit_of_a_branch_that_moved_since_review_writes_nothing(
    jane: httpx.AsyncClient, bob: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    # ADR-0006: the editor reviewed one head; a commit pushed after it (by a
    # person, CI or a workflow) must not be overwritten unseen.
    change = ok(await install(jane, "redbull", "bmhgen", {"override_values": {"a": 1}}), 201)
    reviewed = ok(await bob.get(f"/api/day2/approvals/redbull/{change['iid']}"))["mr"]["sha"]
    team = await gitlab.get_project("sigs/redbull")
    await gitlab.commit(
        team.id,
        branch=change["source_branch"],
        message="a bot pushes after the review",
        changes=[FileChange.create(RepoPath("bot.yaml"), "x: 1\n")],
    )
    edit = {"files": [{"path": BMHGEN_VALUES, "content": "a: 2\n"}], "sha": reviewed}
    url = f"/api/day2/approvals/redbull/{change['iid']}"
    problem(await bob.put(url, json=edit), 409, "REVISION_CONFLICT")
    now = ok(await bob.get(url))
    assert "+a: 1" in next(d for d in now["diffs"] if d["new_path"] == BMHGEN_VALUES)["diff"]
    edited = ok(await bob.put(url, json={**edit, "sha": now["mr"]["sha"]}))
    assert "+a: 2" in next(d for d in edited["diffs"] if d["new_path"] == BMHGEN_VALUES)["diff"]


async def test_mr_detail_edit_and_reject(jane: httpx.AsyncClient, bob: httpx.AsyncClient) -> None:
    change = ok(await install(jane, "redbull", "bmhgen", {"override_values": {"a": 1}}), 201)
    detail = ok(await jane.get(f"/api/day2/approvals/redbull/{change['iid']}"))
    assert detail["mr"]["team"] == "redbull"
    assert [d["new_path"] for d in detail["diffs"]] == [BMHGEN_VALUES]
    assert detail["diffs"][0]["new_file"] is True

    edited = ok(
        await bob.put(
            f"/api/day2/approvals/redbull/{change['iid']}",
            json={"files": [{"path": BMHGEN_VALUES, "content": "a: 2\n"}], "message": "tweak"},
        )
    )
    assert "+a: 2" in edited["diffs"][0]["diff"]
    body = problem(
        await bob.put(
            f"/api/day2/approvals/redbull/{change['iid']}",
            json={"files": [{"path": "README.md", "content": "x"}]},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert body["details"]["rule"] == "path-not-in-mr"
    problem(
        await bob.put(
            f"/api/day2/approvals/redbull/{change['iid']}",
            json={"files": [{"path": "../x", "content": "x"}]},
        ),
        422,
        "VALIDATION_ERROR",
    )
    closed = ok(await bob.post(f"/api/day2/approvals/redbull/{change['iid']}/reject"))
    assert closed["state"] == "closed"
    assert closed["author"]["username"] == change["author"]["username"]
    body = problem(
        await bob.put(
            f"/api/day2/approvals/redbull/{change['iid']}",
            json={"files": [{"path": BMHGEN_VALUES, "content": "a: 3\n"}]},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert body["details"]["rule"] == "mr-not-open"
    problem(await jane.get("/api/day2/approvals/redbull/99"), 404, "NOT_FOUND")


# ── reads and legacy shapes ─────────────────────────────────────────────────


async def test_gitlab_info_and_teams(jane: httpx.AsyncClient) -> None:
    assert ok(await jane.get("/api/day2/gitlab-info")) == {
        "gitlab_url": "http://gitlab.fake",
        "sigs_group_path": "sigs",
        "sigs_group_url": "http://gitlab.fake/groups/sigs",
    }
    teams = ok(await jane.get("/api/day2/teams"))
    assert [t["name"] for t in teams] == ["falcon", "lynx", "orca", "redbull"]
    assert teams[3]["path_with_namespace"] == "sigs/redbull"


async def test_the_catalog_keeps_the_legacy_shape(jane: httpx.AsyncClient) -> None:
    entries = {f"{e['team']}/{e['name']}": e for e in ok(await jane.get("/api/day2/addons"))}
    roles = entries["redbull/cluster-roles"]
    legacy = {
        "team",
        "name",
        "available_versions",
        "current_version",
        "default_values",
        "argocd_metadata",
        "dependencies",
    }
    assert legacy <= set(roles)
    assert roles["dependencies"] == [] and roles["current_version"] == "main"
    assert roles["available_versions"][0] == "main"
    assert {"projectNamespace", "repourl", "targetRevision", "syncPolicy"} <= set(
        roles["argocd_metadata"]
    )
    assert entries["redbull/bmhgen"]["current_version"] == "HEAD"
    assert "repourl-miscased" in {w["rule"] for w in entries["redbull/kyverno"]["warnings"]}
    only = ok(await jane.get("/api/day2/addons?team=lynx"))
    assert {e["team"] for e in only} == {"lynx"}
    one = ok(await jane.get("/api/day2/addons/redbull/cluster-roles"))
    assert one["name"] == "cluster-roles" and one["chart_project"] == "helm-charts/cluster-roles"
    problem(await jane.get("/api/day2/addons/redbull/nope"), 404, "NOT_FOUND")


async def test_versions_are_chart_repo_branches_default_first(jane: httpx.AsyncClient) -> None:
    versions = ok(await jane.get("/api/day2/addons/redbull/cluster-roles/versions"))
    assert versions[0] == "main"
    assert set(versions) == {"main", "2.0.0", "2.1.5-hotfix"}
    values = ok(await jane.get("/api/day2/addons/redbull/cluster-roles/values?version=2.0.0"))
    assert "aggregateToView" in values
    assert ok(await jane.get("/api/day2/addons/redbull/cluster-roles/values?version=nope")) == {}


async def test_clusters_by_kind_and_one_by_id(jane: httpx.AsyncClient) -> None:
    upis = ok(await jane.get("/api/day2/clusters?kind=upi"))
    assert {c["id"] for c in upis} == {
        "upi:site1:prod:ocp4-dok-site1",
        "upi:site2:prep:ocp4-rom-site2",
    }
    prep = ok(await jane.get("/api/day2/clusters?site=site2&env=prep"))
    assert prep and all((c["site"], c["env"]) == ("site2", "prep") for c in prep)
    herzi = ok(await jane.get(f"/api/day2/clusters/{HERZI}"))
    assert (herzi["kind"], herzi["ocp_version"], herzi["argo"], herzi["teams"]) == (
        "hosted",
        "4.16.27",
        "ocp4-prod-mce-site1-a",
        ["redbull"],
    )
    hub = ok(await jane.get("/api/day2/clusters/hub"))
    assert hub["name"] == "prod-hub" and hub["kind"] == "hub"


async def test_cluster_history_lists_commits_of_its_folder(jane: httpx.AsyncClient) -> None:
    history = ok(await jane.get(f"/api/day2/clusters/{HERZI}/history"))
    assert history and {h["team"] for h in history} == {"redbull"}
    assert {"sha", "short_sha", "message", "author", "date", "web_url"} <= set(history[0])
    unknown_env = "hosted:site1::ocp4-mce-workflow-test:ocp4-upgrade-demo"
    assert ok(await jane.get(f"/api/day2/clusters/{unknown_env}/history")) == []


async def test_upgrade_check_names_pinned_charts_missing_the_new_version(
    jane: httpx.AsyncClient, gitlab: InMemoryGitLab
) -> None:
    await gitlab.commit(
        await project_id(gitlab, "sigs/redbull"),
        branch="main",
        message="pin cluster-roles for 4.16.27",
        changes=[
            FileChange.create(
                RepoPath("operators/cluster-roles/ocp-versions/4.16.27/cluster-roles.yaml"),
                "targetRevision: 2.0.0\n",
            )
        ],
    )
    body = ok(await jane.get(f"/api/day2/clusters/{HERZI}/upgrade-check?to=4.17.1-x86_64"))
    assert (body["from_version"], body["to_version"]) == ("4.16.27", "4.17.1")
    assert [w["chart"] for w in body["warnings"]] == ["cluster-roles"]
    assert body["warnings"][0]["rule"] == "ocp-version-pin-missing"
    same = ok(await jane.get(f"/api/day2/clusters/{HERZI}/upgrade-check?to=4.16.27"))
    assert same["warnings"] == []
    problem(
        await jane.get(f"/api/day2/clusters/{HERZI}/upgrade-check?to=latest"),
        422,
        "VALIDATION_ERROR",
    )


async def test_lints_report_every_team_or_one(jane: httpx.AsyncClient) -> None:
    every = ok(await jane.get("/api/day2/lints"))
    assert any(f["rule"] == "repourl-miscased" and f["chart"] == "kyverno" for f in every)
    redbull = ok(await jane.get("/api/day2/lints?team=redbull"))
    assert redbull and all(f["team"] == "redbull" for f in redbull)
    assert {"rule", "severity", "message", "team", "path", "cluster", "chart"} == set(redbull[0])


async def test_merge_preview_shows_edited_cluster_values(jane: httpx.AsyncClient) -> None:
    body = ok(
        await jane.post(
            "/api/day2/merge-preview",
            json={
                "team": "redbull",
                "addon": "cluster-roles",
                "cluster": "ocp4-prod-herzi-site1",
                "mce": "ocp4-prod-mce-site1-a",
                "override_values": {"aggregateToView": False},
            },
        )
    )
    assert body["merged"]["aggregateToView"] is False
    assert body["provenance"]["aggregateToView"] == "cluster"
    assert body["chart"]["project"] == "helm-charts/cluster-roles"
    assert [layer["role"] for layer in body["layers"]][-1] == "cluster"
    assert body["deploy"]["provenance"]["repourl"] == "operators/cluster-roles/cluster-roles.yaml"
    problem(
        await jane.post(
            "/api/day2/merge-preview",
            json={"team": "redbull", "addon": "nope", "cluster": HERZI},
        ),
        404,
        "NOT_FOUND",
    )


async def test_preview_of_a_chart_not_installed_and_at_another_version(
    jane: httpx.AsyncClient,
) -> None:
    body = ok(await jane.get(f"/api/day2/clusters/{HERZI}/addons/redbull/bmhgen?version=1.0.0"))
    assert body["installed"] is False and body["version"] == "1.0.0"
    assert body["source"] == "cluster" and body["ocp_version"] == "4.16.27"


async def test_audit_lists_commits_and_merge_requests_and_diffs(
    jane: httpx.AsyncClient,
) -> None:
    change = ok(await install(jane, "redbull", "bmhgen"), 201)
    commits = ok(await jane.get("/api/day2/audit/commits?per_page=5"))
    assert 0 < len(commits) <= 5 and all(c["repo"] == "day2" and c["team"] for c in commits)
    diff = ok(await jane.get(f"/api/day2/audit/commits/{commits[0]['id']}/diff"))
    assert isinstance(diff, list)
    scoped = ok(
        await jane.get(f"/api/day2/audit/commits/{commits[0]['id']}/diff?team={commits[0]['team']}")
    )
    assert scoped == diff
    problem(await jane.get(f"/api/day2/audit/commits/{'0' * 40}/diff"), 404, "NOT_FOUND")
    mrs = ok(await jane.get("/api/day2/audit/merge-requests"))
    assert [(m["team"], m["iid"]) for m in mrs] == [("redbull", change["iid"])]
    assert ok(await jane.get("/api/day2/audit/merge-requests?page=2")) == []


async def test_history_names_the_requester_not_the_service_account(
    jane: httpx.AsyncClient, bob: httpx.AsyncClient
) -> None:
    # As day1's: the MR's author is the footer's requester, and its commit is
    # authored by them (GitLab keeps the service account as the committer).
    change = ok(await install(jane, "redbull", "bmhgen"), 201)
    ok(await approve(bob, "redbull", change["iid"], change["sha"]))
    [mr] = ok(await jane.get("/api/day2/audit/merge-requests"))
    assert (mr["author"]["username"], mr["gitlab_author"]) == ("jane", "wingman-bot")
    commits = ok(await jane.get("/api/day2/audit/commits?per_page=10"))
    [installed] = [c for c in commits if c["title"].startswith("Install bmhgen")]
    assert (installed["author_name"], installed["author_email"]) == ("jane", "jane@openshift.local")


# ── operations endpoints ────────────────────────────────────────────────────


async def test_health_and_metrics(anonymous: httpx.AsyncClient, jane: httpx.AsyncClient) -> None:
    assert ok(await anonymous.get("/healthz")) == {"status": "ok"}
    ready = ok(await anonymous.get("/health/ready"))
    assert ready == {"status": "ready", "checks": {"gitlab": "ok"}}
    ok(await jane.get("/api/day2/teams"))
    metrics = await anonymous.get("/metrics")
    assert metrics.status_code == 200
    assert 'wingman_build_info{commit="unknown",component="day2"' in metrics.text
    assert 'operation="list_group_projects",outcome="ok"' in metrics.text
