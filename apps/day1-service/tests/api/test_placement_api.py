"""MCE placement over HTTP (ADR-0050): the read, and create checking the chosen MCE.

site1 gets two more prod MCEs for these tests: ``-b`` (empty, roomy) and
``-c`` (empty, 40 free pods, hosting only 4.16 and 4.17). ``-a`` is the
fixtures' own, with six cluster files, one of them owner 7's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.git import FileDiff, RepoPath
from wingman_core.domain.merge_request import MRState, NewMergeRequest
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.application.placement import added_text, mador_of
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

Auth = Callable[[User], dict[str, str]]

A, B, C = (f"ocp4-prod-mce-site1-{x}" for x in "abc")
PLACEMENT = "/api/day1/placement"
VERSION = "4.18.56"
MASTER = NodeObservation("master-0", True, False, True, 250)


def workers(*names: str, pods: int = 250) -> tuple[NodeObservation, ...]:
    return (MASTER, *(NodeObservation(n, True, False, False, pods) for n in names))


def spare(name: str, mce: str, **changes: Any) -> ServerRow:
    row = ServerRow(id=f"srv_{name}", name=name, state="INSTALLED_TO_INVENTORY",
                    health="HEALTHY", site="site1", mce=mce)  # fmt: skip
    return replace(row, **changes)


def placement_hub() -> FakeHubApi:
    return FakeHubApi(
        nodes={A: workers("a-0", "a-1"), B: workers("b-0", "b-1"), C: workers("c-0")},
        pods={
            A: {"master-0": 200, "a-0": 180, "a-1": 170},
            B: {"b-0": 20, "b-1": 30},
            C: {"c-0": 210},
        },
        infra_envs={A: {"inventory": ["dell-r660-site1-128c-1024gb-5tb"]}},
    )


async def add_mces(support: Any, gitlab: InMemoryGitLab) -> None:
    for mce, minors in ((B, '["4.18", "4.17", "4.16"]'), (C, '["4.17", "4.16"]')):
        for file, content in (
            (f"sites/site1/mces/{mce}/values.yaml", "mastertag: 4.16.27-x86_64\n"),
            (f"sites/site1/mces/{mce}/version.yaml", "mastertag: 4.16.27-x86_64\n"),
            (f"upgrade/mces/{mce}.yaml", f"mce:\n  supportedHostedVersions: {minors}\n"),
        ):
            await support.push(gitlab, support.DAY1, branch="main", file=file, content=content)


@pytest.fixture
async def placed_app(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> FastAPI:
    await add_mces(support, gitlab)
    inventory = FakeServerInventory(
        [spare("s1", A), spare("s2", A, maintenance=True), spare("s3", B), spare("s4", B)]
    )
    return support.build_app(
        gitlab=gitlab,
        hub=placement_hub(),
        identity=identity,
        day2=day2,
        clock=clock,
        inventory=inventory,
    )


@pytest.fixture
async def placed(placed_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=placed_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


async def get_placement(
    client: httpx.AsyncClient, headers: dict[str, str], **query: str
) -> dict[str, Any]:
    response = await client.get(PLACEMENT, params={"site": "site1", "env": "prod", **query},
                                headers=headers)  # fmt: skip
    assert response.status_code == 200, response.text
    return response.json()


def by_mce(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["mce"]: c for c in body["candidates"]}


# ── The read ─────────────────────────────────────────────────────────────────


async def test_without_a_version_it_lists_what_the_candidates_host_and_picks_nothing(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await get_placement(placed, auth(support.VIEWER))
    assert [c["mce"] for c in body["candidates"]] == [A, B, C]
    assert (body["pick"], body["why"]) == (None, None)
    assert body["problems"] == ["Choose an OpenShift version."]
    assert body["versions"][:3] == ["4.18.56", "4.17.58", "4.16.55"]
    assert body["min_free_pods"] == 70
    assert {c["checks"][0]["status"] for c in body["candidates"]} == {"unknown"}


async def test_the_pick_its_numbers_and_why(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await get_placement(
        placed, auth(support.VIEWER), version=f"{VERSION}-x86_64", owner="7", flavor="rcs"
    )
    assert (body["version"], body["owner"], body["flavor"]) == (VERSION, "7", "rcs")
    assert body["pick"] == B
    assert body["why"] == f"{B} has the fewest clusters of owner 7: 0, against 1 on {A}."
    assert [(c["mce"], c["rank"]) for c in body["candidates"]] == [(B, 1), (A, 2), (C, None)]
    found = by_mce(body)
    assert found[A]["clusters"] == 6
    assert (found[A]["owner_clusters"], found[B]["owner_clusters"]) == (1, 0)
    assert found[A]["behind_on"] == "owner_clusters"
    assert found[A]["spare"] == {"total": 2, "usable": 1}
    assert found[B]["spare"] == {"total": 2, "usable": 2}
    assert found[C]["spare"] is None
    assert found[C]["spare_detail"] == (
        f"server-scan names no server for {C}, so its spare servers are unknown."
    )
    assert found[B]["pods"] == {
        "free": 450,
        "allocatable": 500,
        "used": 50,
        "nodes_counted": 2,
        "nodes_excluded": {"control_plane": 1, "not_ready": 0, "unschedulable": 0},
    }
    assert found[C]["eligible"] is False
    assert [(c["check"], c["status"]) for c in found[C]["checks"]] == [
        ("version", "fail"),
        ("free_pods", "fail"),
        ("readable", "pass"),
    ]
    assert found[C]["checks"][1]["detail"] == "40 free pods; a new cluster needs 70."
    assert body["server_scan_error"] is None


async def test_the_min_free_pods_is_a_setting(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
) -> None:
    await add_mces(support, gitlab)
    app = support.build_app(gitlab=gitlab, hub=placement_hub(), identity=identity, day2=day2,
                            clock=clock, placement_min_free_pods=30)  # fmt: skip
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        body = await get_placement(client, auth(support.VIEWER), version="4.17.58")
    assert by_mce(body)[C]["eligible"] is True
    assert body["server_scan_error"] == (
        "server-scan is not configured (SERVER_SCAN_URL), so spare servers are unknown."
    )


@pytest.mark.parametrize(
    ("query", "status"),
    [
        ({"site": "site9", "env": "prod"}, 404),
        ({"site": "site1", "env": "staging"}, 422),
        ({"site": "site1", "env": "prod", "owner": "seven"}, 422),
        ({"site": "site1", "env": "prod", "version": "4.18"}, 422),
        ({"env": "prod"}, 422),
    ],
)
async def test_bad_inputs_are_problems(
    placed: httpx.AsyncClient, auth: Auth, support: Any, query: dict[str, str], status: int
) -> None:
    response = await placed.get(PLACEMENT, params=query, headers=auth(support.VIEWER))
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_without_the_mce_hubs_placement_is_not_available(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> None:
    app = support.build_app(gitlab=gitlab, hub=None, identity=identity, day2=day2, clock=clock)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as off:
        response = await off.get(PLACEMENT, params={"site": "site1", "env": "prod"},
                                 headers=auth(support.VIEWER))  # fmt: skip
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        created = await off.post("/api/day1/clusters", json=support.create_body(),
                                 headers=auth(support.ALICE))  # fmt: skip
        assert created.status_code == 201, "with placement off, create checks nothing new"


async def test_an_mce_whose_token_may_not_list_pods_is_unreadable_and_never_picked(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
) -> None:
    await add_mces(support, gitlab)
    hub = FakeHubApi(nodes={A: workers("a-0")}, denied=[B], unavailable=[C])
    app = support.build_app(gitlab=gitlab, hub=hub, identity=identity, day2=day2, clock=clock)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        body = await get_placement(client, auth(support.VIEWER), version=VERSION)
    found = by_mce(body)
    assert body["pick"] == A
    assert found[B]["pods"] is None
    assert found[B]["checks"][2]["status"] == "fail"
    assert "may not list nodes and pods" in found[B]["checks"][2]["detail"]
    assert "unreachable" in found[C]["checks"][2]["detail"]


# ── Create ───────────────────────────────────────────────────────────────────


def sample(app: FastAPI, decision: str) -> float:
    value = app.state.metrics.registry.get_sample_value(
        "wingman_placement_decisions_total", {"decision": decision}
    )
    return value or 0.0


async def descriptions(gitlab: InMemoryGitLab, support: Any) -> list[str]:
    pid = await support.project_id(gitlab, support.DAY1)
    return [mr.description for mr in await gitlab.list_merge_requests(pid, state=MRState.OPENED)]


async def test_creating_on_the_pick_records_it_in_the_merge_request(
    placed: httpx.AsyncClient, placed_app: FastAPI, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    body = support.create_body(mce=B, name="ocp4-prod-falcon-site1",
                               placement={"pick": B, "reason": None})  # fmt: skip
    preview = await placed.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert preview.status_code == 200, preview.text
    assert sample(placed_app, "picked") == 0, "a preview is not a decision"
    created = await placed.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert created.status_code == 201, created.text
    (text,) = await descriptions(gitlab, support)
    assert "### MCE placement" in text
    assert f"Wingman picked `{B}`: {B} has the fewest clusters of owner 7" in text
    assert f"| `{B}` (pick, chosen) | 0 | 0 | 2 (2) | 450 | pass |" in text
    assert f"| `{C}` | 0 | 0 | unknown | 40 | not offered:" in text
    assert text.index("### MCE placement") < text.index("\n---\n"), "above the footer"
    assert sample(placed_app, "picked") == 1


async def test_another_mce_needs_a_reason_and_the_reason_is_recorded(
    placed: httpx.AsyncClient, placed_app: FastAPI, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    body = support.create_body(placement={"pick": B})
    refused = await placed.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
    assert refused.json()["detail"] == f"Choosing {A} over Wingman's pick {B} needs a reason"
    assert sample(placed_app, "refused") == 1
    body["placement"] = {"pick": B, "reason": "Next to the owner's\nstorage"}
    created = await placed.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert created.status_code == 201, created.text
    (text,) = await descriptions(gitlab, support)
    assert (
        f"An admin chose `{A}` over Wingman's pick `{B}`. Reason: `Next to the owner's storage`"
    ) in text
    assert sample(placed_app, "override") == 1


async def test_an_mce_that_fails_a_check_is_refused_with_its_reasons(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body(
        mce=C,
        variables={**support.create_body()["variables"], "openshift_release_version": "4.17.58"},
        placement={"pick": B, "reason": "it is quieter"},
    )
    refused = await placed.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
    assert refused.json()["detail"] == f"MCE {C} cannot take this cluster"
    assert refused.json()["details"]["problems"] == [
        "free_pods: 40 free pods; a new cluster needs 70."
    ]


async def test_a_pick_that_moved_since_the_form_is_a_conflict_naming_the_new_pick(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body(placement={"pick": A})
    stale = await placed.post("/api/day1/clusters/preview", json=body, headers=auth(support.ALICE))
    assert (stale.status_code, stale.json()["code"]) == (409, "REVISION_CONFLICT")
    assert stale.json()["details"] == {"pick": B}
    assert stale.json()["detail"].startswith(f"Wingman's pick changed from {A} to {B}")


async def test_an_open_create_counts_on_its_mce_and_for_its_owner(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    first = support.create_body(mce=B, name="ocp4-prod-falcon-site1", placement={"pick": B})
    assert (
        await placed.post("/api/day1/clusters", json=first, headers=auth(support.ALICE))
    ).status_code == 201
    body = await get_placement(placed, auth(support.VIEWER), version=VERSION, owner="7")
    found = by_mce(body)
    assert (found[B]["clusters"], found[B]["open_creates"], found[B]["owner_clusters"]) == (1, 1, 1)
    assert body["pick"] == B, "owner 7 has one on each now; B has fewer clusters"
    assert found[A]["behind_on"] == "clusters"


async def test_the_chosen_mce_goes_to_the_provision_workflow(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await add_mces(support, gitlab)
    provision = FakeProvisionWorkflow(clock=clock)
    app = support.build_app(gitlab=gitlab, hub=placement_hub(), identity=identity, day2=day2,
                            clock=clock, provision=provision)  # fmt: skip
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    body = support.create_body(placement={"pick": B, "reason": "owner asked"})
    with caplog.at_level("INFO"):
        async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
            started = await client.post(
                "/api/day1/clusters", json=body, headers=auth(support.ALICE)
            )
    assert started.status_code == 202, started.text
    assert [start["mce"] for start in provision.starts] == [A]
    (event,) = [r for r in caplog.records if getattr(r, "event", None) == "mce_placement_chosen"]
    assert (event.mce, event.pick, event.override, event.reason) == (A, B, True, "owner asked")  # ty: ignore[unresolved-attribute]


# ── Sources that cannot answer ───────────────────────────────────────────────


async def test_an_open_create_whose_diff_is_not_ready_is_named_and_not_counted(
    placed: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    await gitlab.create_branch(pid, "platform/olga/create-cluster-x", "main")
    await gitlab.create_merge_request(
        pid,
        NewMergeRequest(
            source_branch="platform/olga/create-cluster-x",
            target_branch="main",
            title="[Wingman/Day1] Create cluster ocp4-prod-x-site1 from spec rcs v1.0.0",
            labels=("wingman",),
        ),
    )
    body = await get_placement(placed, auth(support.VIEWER), version=VERSION)
    assert by_mce(body)[A]["open_creates"] == 0
    (problem,) = body["problems"]
    assert "adds no cluster file yet" in problem


async def test_server_scan_down_makes_every_spare_count_unknown(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
) -> None:
    await add_mces(support, gitlab)
    app = support.build_app(
        gitlab=gitlab,
        hub=placement_hub(),
        identity=identity,
        day2=day2,
        clock=clock,
        inventory=FakeServerInventory(unavailable=True),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        body = await get_placement(client, auth(support.VIEWER), version=VERSION, owner="7")
    assert body["server_scan_error"].startswith("server-scan could not be read")
    assert {c["mce"]: c["spare"] for c in body["candidates"]} == {A: None, B: None, C: None}
    assert body["pick"] == B, "unknown spare everywhere still ranks on the rest"


def test_a_new_files_text_comes_from_its_added_lines() -> None:
    diff = FileDiff(
        old_path=RepoPath("x.yaml"),
        new_path=RepoPath("x.yaml"),
        new_file=True,
        deleted_file=False,
        renamed_file=False,
        diff=(
            '@@ -0,0 +1,3 @@\n+owner:\n+  mador: "0042"\n+mastertag: 4.18.56\n'
            "\\ No newline at end of file\n"
        ),
    )
    assert added_text(diff) == 'owner:\n  mador: "0042"\nmastertag: 4.18.56\n'
    assert mador_of(added_text(diff)) == "0042"


@pytest.mark.parametrize(
    ("content", "mador"),
    [
        ('owner:\n  mador: "7"\n', "7"),
        ("owner:\n  mador: 7\n", "7"),
        ("owner:\n  merkaz: '1'\n", None),
        ("mastertag: 4.18.56\n", None),
        ("owner: [\n", None),
    ],
)
def test_a_files_mador(content: str, mador: str | None) -> None:
    assert mador_of(content) == mador
