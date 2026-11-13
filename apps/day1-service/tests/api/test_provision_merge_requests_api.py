"""The provision-cluster workflow's merge request, seen by Wingman (ADR-0042's amendment).

The workflow opens its day1 MR itself, with no label and its own title, on
``provision-cluster/<file stem>``. Wingman counts it as an open create (the
name suggestion, the "already being created" check) and lists it on the
approvals page, marked as the workflow's; it is reviewed and merged in
GitLab, never through Wingman. An unlabelled MR on any other branch is not
Wingman's business.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.merge_request import MRState
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]
NEW = "ocp4-prod-falcon-site1"
SUGGEST = "/api/day1/clusters/name-suggestion"
HOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Merge Request Hook"}


async def test_the_workflows_mr_is_listed_and_marked_as_the_workflows(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    created = await client.post(
        "/api/day1/clusters",
        json=support.create_body("ocp4-prod-lynx-site1"),
        headers=auth(support.ALICE),
    )
    assert created.status_code == 201, created.text
    workflow = await support.open_provision_mr(gitlab, NEW)
    await support.open_provision_mr(gitlab, "ocp4-prod-orca-site1", branch="someone/orca")
    await support.open_provision_mr(
        gitlab, "ocp4-prod-puma-site1", branch="provision-cluster-ocp4-prod-puma-site1"
    )

    listed = (await client.get("/api/day1/approvals", headers=auth(support.VIEWER))).json()
    assert {m["source_branch"]: m["opened_by_workflow"] for m in listed} == {
        created.json()["source_branch"]: None,
        f"provision-cluster/{NEW}": "provision-cluster",
    }, "an unlabelled MR on any other branch is not listed"
    [mine] = [m for m in listed if m["opened_by_workflow"]]
    assert (mine["iid"], mine["repo"], mine["labels"]) == (workflow.ref.iid, "day1", [])
    assert mine["title"] == f"Provision hosted cluster {NEW} on {support.PROD_MCE}"
    assert mine["web_url"] == workflow.web_url
    assert mine["author"]["username"] == "wingman-bot", "the account that opened it: no footer"


async def test_its_name_is_taken_and_a_second_create_is_refused_with_its_url(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    # The flavor's first free name, before any MR (ADR-0040's suggestion)
    await support.open_provision_mr(gitlab, "ocp4-prod-agent-standar-site1-a")
    workflow = await support.open_provision_mr(gitlab, NEW)
    params = {"site": support.PROD_SITE, "mce": support.PROD_MCE, "flavor": "agent-standard"}
    suggested = await client.get(SUGGEST, params=params, headers=auth(support.VIEWER))
    assert suggested.json()["name"] == "ocp4-prod-agent-standar-site1-b"

    again = await client.post(
        "/api/day1/clusters", json=support.create_body(NEW), headers=auth(support.ALICE)
    )
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_EXISTS")
    assert again.json()["detail"] == (
        f"an open merge request already creates cluster {NEW!r}: {workflow.web_url}"
    )


async def test_an_unlabelled_mr_on_another_branch_does_not_hold_a_name(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.open_provision_mr(gitlab, NEW, branch=f"someone/{NEW}")
    created = await client.post(
        "/api/day1/clusters", json=support.create_body(NEW), headers=auth(support.ALICE)
    )
    assert created.status_code == 201, created.text


async def test_it_is_reviewed_in_gitlab_never_through_wingman(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    workflow = await support.open_provision_mr(gitlab, NEW)
    iid, admin = workflow.ref.iid, auth(support.BOB)
    detail = await client.get(f"/api/day1/approvals/{iid}", headers=admin)
    approve = await client.post(
        f"/api/day1/approvals/{iid}/approve", json={"sha": workflow.sha}, headers=admin
    )
    reject = await client.post(f"/api/day1/approvals/{iid}/reject", headers=admin)
    file = f"sites/{support.PROD_SITE}/mces/{support.PROD_MCE}/hostedClusters/{NEW}.yaml"
    edit = await client.put(
        f"/api/day1/approvals/{iid}",
        json={"files": [{"path": file, "content": "x: 1\n"}], "sha": workflow.sha},
        headers=admin,
    )
    for response in (detail, approve, reject, edit):
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    after = await gitlab.get_merge_request(workflow.ref)
    assert (after.state, after.sha) == (MRState.OPENED, workflow.sha)


async def test_one_mr_that_is_both_wingmans_and_on_the_workflows_branch_is_listed_once(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.open_provision_mr(
        gitlab,
        NEW,
        title=f"[Wingman/Day1] Create cluster {NEW} from spec agent-standard v1.0.0",
        labels=("wingman",),
    )
    listed = (await client.get("/api/day1/approvals", headers=auth(support.VIEWER))).json()
    assert [m["opened_by_workflow"] for m in listed] == ["provision-cluster"]


async def test_a_merge_request_event_shows_a_new_one_at_once(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    viewer = auth(support.VIEWER)
    assert (await client.get("/api/day1/approvals", headers=viewer)).json() == []
    workflow = await support.open_provision_mr(gitlab, NEW)
    assert (await client.get("/api/day1/approvals", headers=viewer)).json() == []  # cached
    hook = await client.post(
        "/api/webhooks/gitlab", json={"project": {"id": workflow.ref.project_id}}, headers=HOOK
    )
    assert hook.json() == {"status": "ok"}
    listed = (await client.get("/api/day1/approvals", headers=viewer)).json()
    assert [m["iid"] for m in listed] == [workflow.ref.iid]
