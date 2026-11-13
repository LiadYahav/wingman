"""A cluster's upgrade through the upgrade-cluster workflow, over HTTP (ADR-0055).

Off by default: every route answers 501 and versions are edited as before.
With ``DAY1_UPGRADES`` on, admins read the targets, start a run and decide;
anyone signed in reads the run; who asked is always the signed-in user; and
a modify or a review edit may not change the versions the workflow owns.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import AmbiguousDecisionError, AmbiguousStartError
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_upgrade import FakeUpgradeWorkflow
from wingman_day1.infrastructure.fake_upgrade_script import (
    default_upgrade_file,
    load_upgrade_script,
)

Auth = Callable[[User], dict[str, str]]

LARK = "ocp4-prod-lark-site1"
BASE = f"/api/day1/clusters/{LARK}"
WHERE = {"site": "site1", "mce": "ocp4-prod-mce-site1-a"}


class ManualClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def run_clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def upgrade(run_clock: ManualClock) -> FakeUpgradeWorkflow:
    return FakeUpgradeWorkflow(load_upgrade_script(default_upgrade_file()), clock=run_clock)


@pytest.fixture
async def on(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    upgrade: FakeUpgradeWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        upgrade=upgrade,
        day1_upgrades=True,
        workflows_api_url="http://workflows-orchestrator-api.test:8080",
        server_scan_url="http://server-scan.test:8000",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


async def reach(
    client: httpx.AsyncClient, run_clock: ManualClock, headers: dict[str, str], phase: str
) -> dict[str, Any]:
    for _ in range(60):
        run = (await client.get(f"{BASE}/upgrade-run", headers=headers)).json()
        if run["phase"] == phase:
            return run
        run_clock.advance(1)
    raise AssertionError(f"never reached {phase}")


# ── Off (the default) ────────────────────────────────────────────────────────


async def test_off_every_route_is_501_and_versions_are_a_normal_edit(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    for response in (
        await client.get(f"{BASE}/upgrade-targets", headers=alice),
        await client.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice),
        await client.get(f"{BASE}/upgrade-run", headers=alice),
        await client.post(f"{BASE}/upgrade-run/approve", json={}, headers=alice),
        await client.post(f"{BASE}/upgrade-run/actions/a1/approve", headers=alice),
    ):
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    cluster = (await client.get(BASE, headers=alice)).json()
    edited = await client.patch(
        BASE,
        json={
            "updated_yaml": cluster["yaml"].replace("4.18.22", "4.18.56"),
            "last_commit_id": cluster["last_commit_id"],
        },
        headers=alice,
    )
    assert edited.status_code == 200, edited.text


# ── On ───────────────────────────────────────────────────────────────────────


async def test_admins_read_the_targets_and_viewers_may_not(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = await on.get(f"{BASE}/upgrade-targets", headers=auth(support.VIEWER))
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    found = await on.get(f"{BASE}/upgrade-targets", params=WHERE, headers=auth(support.ALICE))
    assert found.status_code == 200, found.text
    body = found.json()
    assert (body["cluster"], body["mce"], body["control_plane_version"]) == (
        LARK,
        "ocp4-prod-mce-site1-a",
        "4.18.22",
    )
    assert body["targets"][0] == {
        "version": "4.18.56",
        "minor": "4.18",
        "steps": 2,
        "control_plane_steps": 1,
        "newest_in_minor": True,
        "must": True,
    }
    assert len(body["nodepools"]) == len(body["nodepool_order"]) == 2
    owl = await on.get(
        "/api/day1/clusters/ocp4-prod-owl-site1/upgrade-targets", headers=auth(support.ALICE)
    )
    assert owl.json()["targets"] == [], "an empty list is an answer"


async def test_a_cluster_day1_does_not_have_is_404_everywhere(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    ghost = "/api/day1/clusters/ocp4-prod-ghost-site1"
    alice = auth(support.ALICE)
    for response in (
        await on.get(f"{ghost}/upgrade-targets", headers=alice),
        await on.post(f"{ghost}/upgrade", json={"target_version": "4.18.56"}, headers=alice),
        await on.get(f"{ghost}/upgrade-run", headers=alice),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_a_start_takes_who_asked_from_the_session_and_walks_through_decisions(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    upgrade: FakeUpgradeWorkflow,
    run_clock: ManualClock,
) -> None:
    alice, viewer = auth(support.ALICE), auth(support.VIEWER)
    none_yet = await on.get(f"{BASE}/upgrade-run", headers=viewer)
    assert (none_yet.status_code, none_yet.json()["code"]) == (404, "NOT_FOUND")
    started = await on.post(
        f"{BASE}/upgrade", params=WHERE, json={"target_version": "4.18.56"}, headers=alice
    )
    assert started.status_code == 202, started.text
    assert (started.json()["workflow_id"], started.json()["status"]) == (
        f"upgrade-cluster-{LARK}",
        "running",
    )
    [request] = upgrade.starts
    assert (request.cluster, request.requested_by, request.target_version) == (
        LARK,
        "alice",
        "4.18.56",
    )
    again = await on.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice)
    assert (again.status_code, again.json()["code"]) == (409, "UPGRADE_ALREADY_RUNNING")

    waiting = await reach(on, run_clock, viewer, "awaiting-approval")
    assert waiting["waiting_for"].startswith("approve: 4.18.22 → 4.18.56")
    denied = await on.post(f"{BASE}/upgrade-run/approve", json={}, headers=viewer)
    assert (denied.status_code, denied.json()["code"]) == (403, "FORBIDDEN")

    refused = await on.post(f"{BASE}/upgrade-run/confirm-day2", json={}, headers=alice)
    assert (refused.status_code, refused.json()["code"]) == (409, "UPGRADE_DECISION_REFUSED")
    assert "awaiting-approval, waiting for approve:" in refused.json()["detail"]

    approved = await on.post(
        f"{BASE}/upgrade-run/approve", json={"reason": "reviewed"}, headers=auth(support.BOB)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["decision"] == "approve"
    assert approved.json()["run"]["phase"] == "waiting-for-slot"
    assert upgrade.decisions[-1] == (f"upgrade-cluster-{LARK}", "approve", "bob", "reviewed")


async def test_decisions_are_checked_for_what_the_workflow_requires(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice)
    cases: list[tuple[str, dict[str, str], str]] = [
        ("abort", {}, "abort needs a reason"),
        ("approve-admin-ack", {"reason": "  "}, "approve-admin-ack needs a reason"),
        ("continue", {"reason": "go"}, "continue takes no reason"),
        ("approve", {"nodepool": "a"}, "only continue names a NodePool"),
    ]
    for decision, body, problem in cases:
        response = await on.post(f"{BASE}/upgrade-run/{decision}", json=body, headers=alice)
        assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
        assert problem in response.json()["details"]["problems"]
    unknown = await on.post(f"{BASE}/upgrade-run/rollback", json={}, headers=alice)
    assert unknown.status_code == 422
    extra = await on.post(f"{BASE}/upgrade-run/pause", json={"by": "mallory"}, headers=alice)
    assert extra.status_code == 422, "who decides is never taken from the body"
    no_target = await on.post(f"{BASE}/upgrade", json={}, headers=alice)
    assert no_target.status_code == 422
    assert upgrade.decisions == []

    aborted = await on.post(
        f"{BASE}/upgrade-run/abort", json={"reason": "wrong target"}, headers=alice
    )
    assert aborted.status_code == 200, aborted.text
    assert aborted.json()["run"]["outcome"] == "cancelled"
    gone = await on.post(f"{BASE}/upgrade-run/abort", json={"reason": "x"}, headers=alice)
    assert (gone.status_code, gone.json()["code"]) == (404, "NOT_FOUND")


async def test_an_unanswered_start_or_decision_is_ambiguous_and_never_retried(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    alice = auth(support.ALICE)

    async def lost_start(_request: object) -> None:
        raise AmbiguousStartError("the upgrade was sent but no answer came back")

    upgrade.start = lost_start  # type: ignore
    started = await on.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice)
    assert (started.status_code, started.json()["code"]) == (504, "AMBIGUOUS_WRITE")

    async def lost_decision(*_args: object, **_kwargs: object) -> None:
        raise AmbiguousDecisionError("approve was sent but no answer came back")

    upgrade.decide = lost_decision  # type: ignore
    decided = await on.post(f"{BASE}/upgrade-run/approve", json={}, headers=alice)
    assert (decided.status_code, decided.json()["code"]) == (504, "AMBIGUOUS_WRITE")


async def test_an_unreachable_orchestrator_is_502_and_a_proposal_refusal_409(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice)
    proposal = await on.post(f"{BASE}/upgrade-run/actions/act-1/approve", headers=alice)
    assert (proposal.status_code, proposal.json()["code"]) == (409, "UPGRADE_DECISION_REFUSED")
    bad = await on.post(f"{BASE}/upgrade-run/actions/act-1/maybe", headers=alice)
    assert bad.status_code == 422
    upgrade.unavailable = True
    for response in (
        await on.get(f"{BASE}/upgrade-run", headers=alice),
        await on.get(f"{BASE}/upgrade-targets", headers=alice),
    ):
        assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")


# ── Versions belong to the workflow while it is on ───────────────────────────


async def test_a_modify_may_not_change_versions_but_may_clear_paused_until(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    cluster = (await on.get(BASE, headers=alice)).json()
    moved = await on.patch(
        BASE,
        json={
            "updated_yaml": cluster["yaml"].replace("4.18.22", "4.18.56"),
            "last_commit_id": cluster["last_commit_id"],
        },
        headers=alice,
    )
    assert (moved.status_code, moved.json()["code"]) == (422, "VALIDATION_ERROR")
    assert moved.json()["details"]["problems"] == [
        "mastertag: Versions change through Upgrade on the cluster page"
    ]
    path = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{LARK}.yaml"
    aborted = cluster["yaml"] + 'pausedUntil: "true"\n'
    await support.push(gitlab, support.DAY1, branch="main", file=path, content=aborted)
    hook = await on.post(
        "/api/webhooks/gitlab",
        json={
            "object_kind": "push",
            "project": {"id": await support.project_id(gitlab, support.DAY1)},
            "ref": "refs/heads/main",
        },
        headers={"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"},
    )
    assert hook.json() == {"status": "ok"}
    paused = (await on.get(BASE, headers=alice)).json()
    assert "pausedUntil" in paused["yaml"]
    cleared = await on.patch(
        BASE,
        json={
            "updated_yaml": paused["yaml"].replace('pausedUntil: "true"\n', ""),
            "last_commit_id": paused["last_commit_id"],
        },
        headers=alice,
    )
    assert cleared.status_code == 200, cleared.text


async def test_a_review_edit_may_not_change_an_existing_clusters_versions(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice, bob = auth(support.ALICE), auth(support.BOB)
    cluster = (await on.get(BASE, headers=alice)).json()
    opened = await on.patch(
        BASE,
        json={
            "updated_yaml": cluster["yaml"].replace("replicas: 3", "replicas: 4", 1),
            "last_commit_id": cluster["last_commit_id"],
        },
        headers=alice,
    )
    assert opened.status_code == 200, opened.text
    mr = opened.json()
    pid = await support.project_id(gitlab, support.DAY1)
    path = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{LARK}.yaml"
    content = gitlab.snapshot(pid, mr["source_branch"])[path]
    edit = await on.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={"files": [{"path": path, "content": content.replace("4.18.22", "4.18.56")}]},
        headers=bob,
    )
    assert (edit.status_code, edit.json()["code"]) == (422, "VALIDATION_ERROR")
    assert any("Versions change through Upgrade" in p for p in edit.json()["details"]["problems"])


async def test_a_create_still_writes_and_its_review_may_change_the_starting_version(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    created = await on.post(
        "/api/day1/clusters", json=support.create_body(), headers=auth(support.ALICE)
    )
    assert created.status_code == 201, created.text
    mr = created.json()
    pid = await support.project_id(gitlab, support.DAY1)
    path = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-falcon-site1.yaml"
    content = gitlab.snapshot(pid, mr["source_branch"])[path]
    tag = next(line for line in content.splitlines() if line.startswith("mastertag:"))
    edit = await on.put(
        f"/api/day1/approvals/{mr['iid']}",
        json={"files": [{"path": path, "content": content.replace(tag, "mastertag: 4.17.58")}]},
        headers=auth(support.BOB),
    )
    assert edit.status_code == 200, edit.text


async def test_a_decision_taken_whose_run_cannot_be_read_again_answers_without_it(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/upgrade", json={"target_version": "4.18.56"}, headers=alice)
    decide = upgrade.decide

    async def then_down(*args: Any, **kwargs: Any) -> None:
        await decide(*args, **kwargs)
        upgrade.unavailable = True

    upgrade.decide = then_down  # type: ignore
    aborted = await on.post(f"{BASE}/upgrade-run/abort", json={"reason": "r"}, headers=alice)
    assert aborted.status_code == 200, aborted.text
    assert aborted.json() == {
        "workflow_id": f"upgrade-cluster-{LARK}",
        "decision": "abort",
        "run": None,
    }
