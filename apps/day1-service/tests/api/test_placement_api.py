"""MCE placement over HTTP (ADR-0050): the read, and create checking the chosen MCE.

site1 has three prod MCEs: ``-a`` (the fixtures' six cluster files, one of
them owner 7's), ``-b`` (empty, roomy) and ``-c`` (empty, 40 free pods,
hosting only 4.16 and 4.17). The create body's nodepools need two servers of
each of two node types: ``-a`` and ``-b`` have them free and healthy (one of
``-a``'s Dell servers is in maintenance, one Dell Agent is in no server-scan
row); ``-c`` has none.
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
from wingman_day1.api.v1.placement import parse_needs
from wingman_day1.application.placement import added_text, file_needs, mador_of, preset_needs
from wingman_day1.domain.errors import HubDeniedError
from wingman_day1.domain.machines import BMH_LABEL, INFRA_ENV_LABEL, AgentObservation
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_hub import FREE_AGENT, FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

Auth = Callable[[User], dict[str, str]]

A, B, C = (f"ocp4-prod-mce-site1-{x}" for x in "abc")
PLACEMENT = "/api/day1/placement"
VERSION = "4.18.56"
MASTER = NodeObservation("master-0", True, False, True, 250)
DELL, HP = "dell-r660-site1-128c-1024gb-5tb", "hp-gen11-site1-64c"
AGENTS = {
    A: [("s1", DELL), ("s2", DELL), ("s5", DELL), ("ghost", DELL), ("s6", HP), ("s7", HP)],
    B: [("s3", DELL), ("s4", DELL), ("s8", HP), ("s9", HP)],
}
"""Each MCE's free Agents: the server they are, and their InfraEnv."""


def workers(*names: str, pods: int = 250) -> tuple[NodeObservation, ...]:
    return (MASTER, *(NodeObservation(n, True, False, False, pods) for n in names))


def spare(name: str, mce: str, **changes: Any) -> ServerRow:
    row = ServerRow(
        id=f"srv_{name}",
        name=name,
        state="INSTALLED_TO_INVENTORY",
        health="HEALTHY",
        site="site1",
        mce=mce,
    )
    return replace(row, **changes)


def free_agent(server: str, infra_env: str) -> AgentObservation:
    return AgentObservation(
        name=f"agent-{server}",
        labels={INFRA_ENV_LABEL: infra_env, BMH_LABEL: server},
        approved=True,
        conditions=FREE_AGENT,
    )


def placement_hub(**more: Any) -> FakeHubApi:
    return FakeHubApi(
        nodes={A: workers("a-0", "a-1"), B: workers("b-0", "b-1"), C: workers("c-0")},
        pods={
            A: {"master-0": 200, "a-0": 180, "a-1": 170},
            B: {"b-0": 20, "b-1": 30},
            C: {"c-0": 210},
        },
        infra_envs={A: {"inventory": [DELL]}},
        agents={
            (mce, "inventory"): [free_agent(server, infra_env) for server, infra_env in agents]
            for mce, agents in AGENTS.items()
        },
        **more,
    )


def fleet() -> list[ServerRow]:
    """server-scan's rows for the free Agents (but ``ghost``): spare servers of their MCE."""
    return [
        spare(server, mce, maintenance=server == "s2")
        for mce, agents in AGENTS.items()
        for server, _ in agents
        if server != "ghost"
    ]


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
    inventory = FakeServerInventory(fleet())
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
    client: httpx.AsyncClient, headers: dict[str, str], **query: str | list[str]
) -> dict[str, Any]:
    response = await client.get(
        PLACEMENT, params={"site": "site1", "env": "prod", **query}, headers=headers
    )
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
        placed,
        auth(support.VIEWER),
        version=f"{VERSION}-x86_64",
        owner="7",
        flavor="agent-standard",
    )
    assert (body["version"], body["owner"], body["flavor"]) == (VERSION, "7", "agent-standard")
    assert body["needs"] == [], "the flavor names no InfraEnv, and the form sent no need"
    assert body["pick"] == B
    assert body["why"] == f"{B} has the fewest clusters of owner 7: 0, against 1 on {A}."
    assert [(c["mce"], c["rank"]) for c in body["candidates"]] == [(B, 1), (A, 2), (C, None)]
    found = by_mce(body)
    assert found[A]["clusters"] == 6
    assert (found[A]["owner_clusters"], found[B]["owner_clusters"]) == (1, 0)
    assert found[A]["behind_on"] == "owner_clusters"
    assert found[A]["spare"] == {"total": 5, "usable": 4}
    assert found[B]["spare"] == {"total": 4, "usable": 4}
    assert found[C]["spare"] is None
    assert found[C]["spare_detail"] == (
        f"server-scan names no server for {C}, so its spare servers are unknown."
    )
    assert found[B]["pods"] == {
        "free": 450,
        "allocatable": 500,
        "used": 50,
        "nodes_counted": 2,
        "nodes_excluded": {
            "control_plane": 1,
            "infra": 0,
            "not_ready": 0,
            "unschedulable": 0,
            "tainted": 0,
        },
    }
    assert found[C]["eligible"] is False
    assert [(c["check"], c["status"]) for c in found[C]["checks"]] == [
        ("version", "fail"),
        ("free_pods", "fail"),
        ("servers", "pass"),
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
    app = support.build_app(
        gitlab=gitlab,
        hub=placement_hub(),
        identity=identity,
        day2=day2,
        clock=clock,
        placement_min_free_pods=30,
    )
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
        response = await off.get(
            PLACEMENT, params={"site": "site1", "env": "prod"}, headers=auth(support.VIEWER)
        )
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        created = await off.post(
            "/api/day1/clusters", json=support.create_body(), headers=auth(support.ALICE)
        )
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
    assert found[B]["checks"][3]["status"] == "fail"
    assert "may not list nodes and pods" in found[B]["checks"][3]["detail"]
    assert "unreachable" in found[C]["checks"][3]["detail"]


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
    body = support.create_body(
        mce=B, name="ocp4-prod-falcon-site1", placement={"pick": B, "reason": None}
    )
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
    servers = f"{DELL} 2/2, {HP} 2/2"
    assert f"| `{B}` (pick, chosen) | 0 | 0 | 4 (4) | 450 | {servers} | pass |" in text
    assert f"| `{C}` | 0 | 0 | unknown | 40 | {DELL} 0/2, {HP} 0/2 | not offered:" in text
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
        "free_pods: 40 free pods; a new cluster needs 70.",
        f"servers: {DELL}: 0 healthy free of 2 needed; {HP}: 0 healthy free of 2 needed.",
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
    app = support.build_app(
        gitlab=gitlab,
        hub=placement_hub(),
        identity=identity,
        day2=day2,
        clock=clock,
        provision=provision,
    )
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


# ── Servers of each node type ────────────────────────────────────────────────


def servers_check(candidate: dict[str, Any]) -> tuple[str, str]:
    check = next(c for c in candidate["checks"] if c["check"] == "servers")
    return check["status"], check["detail"]


async def test_the_needs_the_form_sends_are_checked_per_type(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await get_placement(
        placed,
        auth(support.VIEWER),
        version=VERSION,
        need=[f"{DELL}:1", f"{DELL}:1", f"{HP}:2"],
    )
    assert body["needs"] == [
        {"infra_env": DELL, "replicas": 2},
        {"infra_env": HP, "replicas": 2},
    ]
    found = by_mce(body)
    assert found[A]["node_types"][0] == {
        "infra_env": DELL,
        "needed": 2,
        "free_agents": 4,
        "healthy": 2,
        "not_in_server_scan": 1,
        "health_checked": True,
        "status": "pass",
        "detail": f"{DELL}: 2 healthy free of 2 needed (1 more free, not in server-scan)",
    }
    assert servers_check(found[B])[0] == "pass"
    assert servers_check(found[C]) == (
        "fail",
        f"{DELL}: 0 healthy free of 2 needed; {HP}: 0 healthy free of 2 needed.",
    )


async def test_a_type_short_on_one_mce_and_unknown_on_another_leaves_no_pick(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    """A: 2 healthy Dell, one free Agent not in server-scan; B: 2 Dell in all."""
    body = await get_placement(placed, auth(support.VIEWER), version=VERSION, need=f"{DELL}:3")
    found = by_mce(body)
    assert servers_check(found[A]) == (
        "unknown",
        f"{DELL}: 2 healthy free of 3 needed (1 more free, not in server-scan).",
    )
    assert servers_check(found[B]) == ("fail", f"{DELL}: 2 healthy free of 3 needed.")
    assert body["pick"] is None
    assert body["problems"] == ["No prod MCE at site1 passes every check."]


async def test_a_type_short_on_the_pick_takes_it_out(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    """Without needs B is the pick (owner 7 has none there); B has no third HP server."""
    plain = await get_placement(placed, auth(support.VIEWER), version=VERSION, owner="7")
    assert plain["pick"] == B
    short = await get_placement(
        placed, auth(support.VIEWER), version=VERSION, owner="7", need=f"{HP}:3"
    )
    assert servers_check(by_mce(short)[B]) == ("fail", f"{HP}: 2 healthy free of 3 needed.")
    assert servers_check(by_mce(short)[A])[0] == "fail"


async def test_create_checks_the_servers_its_own_nodepools_need(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    variables = {**support.create_body()["variables"]}
    variables["nodepools"] = support.nodepools(DELL, HP, replicas=3)
    body = support.create_body(mce=B, variables=variables, placement={"pick": B})
    refused = await placed.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
    assert refused.json()["detail"] == "No prod MCE at site1 can take this cluster"
    assert (
        f"{B}: servers: {DELL}: 2 healthy free of 3 needed; {HP}: 2 healthy free of 3 needed."
        in (refused.json()["details"]["problems"])
    )


@pytest.mark.parametrize(
    "need",
    [f"{DELL}", f"{DELL}:x", f"{DELL}:0", f"{DELL}:1001", "Not_A_Label:2", ":2"],
)
async def test_a_need_that_is_not_a_type_and_replicas_is_a_problem(
    placed: httpx.AsyncClient, auth: Auth, support: Any, need: str
) -> None:
    response = await placed.get(
        PLACEMENT,
        params={"site": "site1", "env": "prod", "need": need},
        headers=auth(support.VIEWER),
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


async def test_an_unknown_flavor_is_not_found(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await placed.get(
        PLACEMENT,
        params={"site": "site1", "env": "prod", "flavor": "rcs"},
        headers=auth(support.VIEWER),
    )
    assert response.status_code == 404


async def test_agents_the_token_may_not_list_make_the_servers_unknown(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
) -> None:
    class NoAgents(FakeHubApi):
        async def infra_env_agents(self, mce: str, **_: Any) -> list[AgentObservation]:
            raise HubDeniedError(f"MCE {mce!r} hub API denied Wingman's token (403) on GET agents")

    hub = NoAgents(nodes={A: workers("a-0"), B: workers("b-0")})
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        inventory=FakeServerInventory(fleet()),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        body = await get_placement(client, auth(support.VIEWER), version=VERSION, need=f"{DELL}:1")
    status, detail = servers_check(by_mce(body)[A])
    assert status == "unknown"
    assert "Its token may not list Agents" in detail
    assert body["pick"] is None


async def test_without_server_scan_free_agents_count_as_they_are(
    support: Any,
    gitlab: InMemoryGitLab,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    auth: Auth,
) -> None:
    app = support.build_app(
        gitlab=gitlab, hub=placement_hub(), identity=identity, day2=day2, clock=clock
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        body = await get_placement(client, auth(support.VIEWER), version=VERSION, need=f"{DELL}:4")
    found = by_mce(body)
    assert found[A]["node_types"][0]["health_checked"] is False
    assert servers_check(found[A]) == (
        "pass",
        f"{DELL}: 4 free of 4 needed, their health not checked (server-scan is not configured).",
    )
    assert body["pick"] == A


async def test_an_empty_need_says_no_needs_and_skips_the_flavor(
    placed: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = await get_placement(placed, auth(support.VIEWER), version=VERSION, need="")
    assert body["needs"] == []
    assert {servers_check(c)[1] for c in body["candidates"]} == {
        "No nodepool names a node type yet."
    }


def test_needs_from_the_query_the_flavor_and_the_file() -> None:
    assert parse_needs(["", f"{DELL}:2", f"{HP}:1"]) == [(DELL, 2), (HP, 1)]
    assert parse_needs([""]) == []
    presets = [
        {"infra_env": DELL, "replicas": 3},
        {"infra_env": HP},
        {"replicas": 2},
        {"infra_env": " ", "replicas": 1},
        "not a nodepool",
    ]
    assert preset_needs(presets, ratio=()) == [(DELL, 3), (HP, 2)], "2: the template's default"
    assert preset_needs(presets, ratio=(1, 4)) == [(DELL, 3), (HP, 4)], "the ratio's part"
    assert preset_needs(None, ratio=()) == []
    content = (
        f"nodepool:\n  - infraEnvName: {DELL}\n    replicas: 3\n"
        f"  - infraEnvName: {HP}\n    replicas: 2\n  - infraEnvName: {HP}\n"
    )
    assert file_needs(content) == [(DELL, 3), (HP, 2)]
    assert file_needs("nodepool: [\n") == []
