"""A cluster's NodePools scaled through the update-nodepool workflow, over HTTP (ADR-0062).

On by default wherever the orchestrator is (3.53.0); without one, or with
``DAY1_SCALE_NODEPOOLS=false``, every route answers 501. On,
anyone signed in reads what can be scaled and the run (a viewer's names no
server); admins start one for one NodePool of the cluster file; day1 fills the MCE and the cluster,
refuses a NodePool it cannot map to one entry of the file (and the retired
InfraEnv kind) before anything is sent; a NodePool whose replicas a flavor
locks moves only back to its locked value; everything else is the
workflow's to judge, in its words.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import AmbiguousStartError
from wingman_day1.domain.scale import ScaleRequest
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_scale import FakePool, FakeScaleWorkflow
from wingman_day1.infrastructure.scale_workflow import HttpScaleWorkflow

Auth = Callable[[User], dict[str, str]]

LARK = "ocp4-prod-lark-site1"
BASE = f"/api/day1/clusters/{LARK}"
MCE = "ocp4-prod-mce-site1-a"
HOSTED = f"sites/site1/mces/{MCE}/hostedClusters"
SMALL = "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"
STORAGE = "prod-lark-site1-dell-r760-site1-64c-512gb-20tb"
WEBHOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"}
SIZED = """\
apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-sized
  description: "Lark's sizes: the first nodepool's replicas are locked"
  version: "1.0.0"
spec:
  day1:
    locked_paths:
      - nodepools[0].replicas
    values:
      nodepools:
        - replicas: 3
        - replicas: 2
"""


async def pools(_cluster: str) -> Sequence[FakePool]:
    return (
        FakePool(SMALL, "dell-r660-site1-128c-1024gb-5tb", 3),
        FakePool(STORAGE, "dell-r760-site1-64c-512gb-20tb", 2, "fewest-pods"),
    )


class ManualClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def run_clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def scale(run_clock: ManualClock) -> FakeScaleWorkflow:
    return FakeScaleWorkflow(clock=run_clock, pools=pools)


@pytest.fixture
async def on(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    scale: FakeScaleWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        scale=scale,
        workflows_api_url="http://workflows-orchestrator-api.test:8080",
        server_scan_url="http://server-scan.test:8000",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


async def follow(client: httpx.AsyncClient, support: Any, gitlab: InMemoryGitLab) -> None:
    """Lark follows agent-sized, which locks its first NodePool's replicas at 3."""
    specs = await support.project_id(gitlab, support.SPECS)
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-sized.yaml", content=SIZED
    )
    day1 = await support.project_id(gitlab, support.DAY1)
    path = f"{HOSTED}/{LARK}.yaml"
    current = await gitlab.read_file(day1, RepoPath(path), "main")
    header = '# specName: "agent-sized"\n# specVersion: "1.0.0"\n'
    await support.push(
        gitlab, support.DAY1, branch="main", file=path, content=header + current.content
    )
    for pid in (specs, day1):
        await client.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)


async def assert_off(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    for response in (
        await client.get(f"{BASE}/scale", headers=alice),
        await client.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=alice),
        await client.get(f"{BASE}/scale-run", headers=alice),
    ):
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        assert "DAY1_SCALE_NODEPOOLS" in response.json()["detail"]


async def test_without_the_orchestrator_every_scale_route_is_501(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await assert_off(client, auth(support.ALICE))


async def test_turned_off_beside_the_orchestrator_every_scale_route_is_501(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
    scale: FakeScaleWorkflow,
    auth: Auth,
) -> None:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        scale=scale,
        day1_scale_nodepools=False,
        workflows_api_url="http://workflows-orchestrator-api.test:8080",
        server_scan_url="http://server-scan.test:8000",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        await assert_off(client, auth(support.ALICE))
    assert scale.started == []


async def test_the_options_are_the_files_nodepools(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await on.get(f"{BASE}/scale", headers=auth(support.ALICE))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["cluster"], body["mce"], body["flavor"]) == (LARK, MCE, None)
    assert body["nodepools"] == [
        {
            "index": 0,
            "name": SMALL,
            "infra_env": "dell-r660-site1-128c-1024gb-5tb",
            "replicas": 3,
            "locked_by": None,
            "locked_replicas": None,
            "unnamed": None,
            "scale_down_policy": None,
        },
        {
            "index": 1,
            "name": STORAGE,
            "infra_env": "dell-r760-site1-64c-512gb-20tb",
            "replicas": 2,
            "locked_by": None,
            "locked_replicas": None,
            "unnamed": None,
            "scale_down_policy": None,
        },
    ]
    assert "kinds" not in body


async def test_each_nodepools_scale_down_policy_is_read_from_its_annotations(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    day1 = await support.project_id(gitlab, support.DAY1)
    path = f"{HOSTED}/{LARK}.yaml"
    current = (await gitlab.read_file(day1, RepoPath(path), "main")).content
    small, storage = "  replicas: 3\n", "  replicas: 2\n"
    assert current.count(small) == 1 and current.count(storage) == 1
    annotated = current.replace(
        small, small + "  annotations:\n    redbull.io/scale-down-policy: newest-first\n"
    ).replace(storage, storage + "  annotations:\n    redbull.io/scale-down-policy: fewest-pods\n")
    await support.push(gitlab, support.DAY1, branch="main", file=path, content=annotated)
    await on.post("/api/webhooks/gitlab", json={"project": {"id": day1}}, headers=WEBHOOK)
    body = (await on.get(f"{BASE}/scale", headers=auth(support.VIEWER))).json()
    # As written, a value the workflow does not know too: it refuses that one itself
    assert [(p["name"], p["scale_down_policy"]) for p in body["nodepools"]] == [
        (SMALL, "newest-first"),
        (STORAGE, "fewest-pods"),
    ]


async def test_an_admin_starts_one_nodepool_and_day1_names_the_mce_and_cluster(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    run_clock: ManualClock,
) -> None:
    alice = auth(support.ALICE)
    started = await on.post(
        f"{BASE}/scale", json={"replicas": 4, "nodepool": STORAGE}, headers=alice
    )
    assert started.status_code == 202, started.text
    assert {k: started.json()[k] for k in ("workflow_id", "status")} == {
        "workflow_id": f"update-nodepool-{LARK}",
        "status": "running",
    }
    assert scale.started == [ScaleRequest(MCE, LARK, 4, nodepool=STORAGE)]
    busy = await on.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=alice)
    assert (busy.status_code, busy.json()["code"]) == (409, "SCALE_ALREADY_RUNNING")
    assert (
        busy.json()["detail"] == f"An update-nodepool run is already in flight for cluster {LARK}"
    )
    run_clock.advance(seconds=120)
    run = (await on.get(f"{BASE}/scale-run", headers=auth(support.VIEWER))).json()
    assert (run["status"], run["direction"], run["error"]) == ("completed", "up", None)
    result = run["result"]
    assert (result["nodepool"], result["infra_env_kind"], result["ignored"]) == (STORAGE, None, [])
    assert result["nodepools"] == [
        {
            "name": STORAGE,
            "infra_env": "dell-r760-site1-64c-512gb-20tb",
            "before": 2,
            "after": 4,
            "scale_down_policy": "fewest-pods",
        }
    ]
    by_name = await on.post(f"{BASE}/scale", json={"replicas": 2, "nodepool": SMALL}, headers=alice)
    assert by_name.status_code == 202, by_name.text
    assert scale.started[-1] == ScaleRequest(MCE, LARK, 2, nodepool=SMALL)


async def test_a_running_scale_down_shows_its_childs_phase(
    on: httpx.AsyncClient, auth: Auth, support: Any, run_clock: ManualClock
) -> None:
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": STORAGE}, headers=alice)
    run_clock.advance(seconds=4 * 5)
    run = (await on.get(f"{BASE}/scale-run", headers=alice)).json()
    assert (run["status"], run["phase"], run["direction"]) == ("running", "scaling-down", "down")
    assert run["child"]["workflow_id"] == f"scale-down-nodepool-{LARK}"
    assert run["child"]["phase"] == "marking-machines"
    assert run["result"] is None


async def test_a_failed_run_is_shown_in_the_workflows_words(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    run_clock: ManualClock,
) -> None:
    async def mce_lacks_storage(_cluster: str) -> Sequence[FakePool]:
        return [p for p in await pools(_cluster) if p.name != STORAGE]

    scale.read_pools_with(mce_lacks_storage)
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": STORAGE}, headers=alice)
    run_clock.advance(seconds=60)
    run = (await on.get(f"{BASE}/scale-run", headers=alice)).json()
    assert (run["status"], run["phase"], run["error_type"]) == ("failed", "reading-nodepools", None)
    assert f"no NodePool {STORAGE}" in run["error"]


async def test_viewers_read_but_only_admins_start(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer = auth(support.VIEWER)
    assert (await on.get(f"{BASE}/scale-run", headers=viewer)).status_code == 404
    refused = await on.post(
        f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=viewer
    )
    assert refused.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"replicas": 1},
        {"replicas": 1, "nodepool": SMALL, "infra_env_kind": "dell"},
        {"replicas": -1, "nodepool": SMALL},
        {"replicas": "2", "nodepool": SMALL},
        {"replicas": 1, "nodepool": "Not A Name"},
        {"replicas": 1, "nodepool": SMALL, "mce_cluster": "elsewhere"},
        {"replicas": 2, "nodepool": SMALL, "server_names": []},
        {"replicas": 2, "nodepool": SMALL, "server_names": "ocp-a"},
        {"replicas": 2, "nodepool": SMALL, "server_names": ["ocp-a b"]},
        {"replicas": 1, "nodepool": SMALL, "server_names": ["ocp-A", "ocp-a"]},
        {"replicas": 0, "nodepool": SMALL, "server_names": [f"ocp-{n}" for n in range(21)]},
    ],
)
async def test_a_body_the_workflow_would_refuse_is_a_422_before_anything_is_sent(
    on: httpx.AsyncClient, auth: Auth, support: Any, scale: FakeScaleWorkflow, body: Any
) -> None:
    response = await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert scale.started == []


async def test_a_scale_down_may_name_exactly_the_servers_that_leave(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    run_clock: ManualClock,
) -> None:
    alice = auth(support.ALICE)
    named = [
        "ocp-dell-r660-site1-128c-1024gb-5tb-DL0001",
        "ocp-dell-r660-site1-128c-1024gb-5tb-DL0002",
    ]
    started = await on.post(
        f"{BASE}/scale",
        json={"replicas": 1, "nodepool": SMALL, "server_names": named},
        headers=alice,
    )
    assert started.status_code == 202, started.text
    assert scale.started == [ScaleRequest(MCE, LARK, 1, nodepool=SMALL, server_names=tuple(named))]
    run_clock.advance(seconds=120)
    run = (await on.get(f"{BASE}/scale-run", headers=alice)).json()
    assert [(c["server"], c["policy"]) for c in run["result"]["chosen"]] == [
        (named[0].lower(), "named"),
        (named[1].lower(), "named"),
    ]


async def test_a_viewer_reads_the_same_run_without_its_servers(
    on: httpx.AsyncClient, auth: Auth, support: Any, run_clock: ManualClock
) -> None:
    """ADR-0038's 2026-11-23 amendment: the counts stay; no server, Machine or node is named."""
    named = ["ocp-dell-r660-site1-128c-1024gb-5tb-DL0001"]
    body = {"replicas": 2, "nodepool": SMALL, "server_names": named}
    assert (await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))).is_success
    run_clock.advance(seconds=120)
    admin = (await on.get(f"{BASE}/scale-run", headers=auth(support.ALICE))).json()
    seen = await on.get(f"{BASE}/scale-run", headers=auth(support.VIEWER))
    viewer = seen.json()
    assert seen.status_code == 200
    assert admin["result"]["chosen"] and admin["result"]["deleting"]
    assert (viewer["result"]["chosen"], viewer["result"]["deleting"]) == ([], [])
    kept = {k: v for k, v in admin["result"].items() if k not in {"chosen", "deleting"}}
    assert {k: v for k, v in viewer["result"].items() if k in kept} == kept
    assert {k: v for k, v in viewer.items() if k != "result"} == {
        k: v for k, v in admin.items() if k != "result"
    }
    assert (viewer["result"]["total_before"], viewer["result"]["total_after"]) == (3, 2)
    for name in (named[0].lower(), *admin["result"]["deleting"]):
        assert name not in seen.text


@pytest.mark.parametrize(
    ("replicas", "names", "problem"),
    [
        (
            4,
            ["ocp-a"],
            f"server_names: servers are named only on a scale-down; {SMALL} goes from 3 to 4",
        ),
        (
            3,
            ["ocp-a"],
            f"server_names: servers are named only on a scale-down; {SMALL} goes from 3 to 3",
        ),
        (
            1,
            ["ocp-a"],
            f"server_names: {SMALL} goes from 3 to 1, so 2 server(s) leave and 1 are named; "
            "name exactly the servers that leave, or none to let its policy pick",
        ),
    ],
)
async def test_servers_are_named_only_on_a_scale_down_and_as_many_as_leave(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    replicas: int,
    names: list[str],
    problem: str,
) -> None:
    body = {"replicas": replicas, "nodepool": SMALL, "server_names": names}
    response = await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [problem]
    assert scale.started == []


async def test_a_total_over_an_infraenv_kind_is_refused_in_words_and_never_sent(
    on: httpx.AsyncClient, auth: Auth, support: Any, scale: FakeScaleWorkflow
) -> None:
    response = await on.post(
        f"{BASE}/scale",
        json={"replicas": 4, "infra_env_kind": "dell-r660-site1-128c-1024gb-5tb"},
        headers=auth(support.ALICE),
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    (error,) = response.json()["details"]["errors"]
    assert "infra_env_kind is no longer taken: send the NodePool's name as nodepool" in error["msg"]
    assert scale.started == []


async def test_a_nodepool_the_day1_file_does_not_name_is_refused_before_anything_is_sent(
    on: httpx.AsyncClient, auth: Auth, support: Any, scale: FakeScaleWorkflow
) -> None:
    response = await on.post(
        f"{BASE}/scale",
        json={"replicas": 2, "nodepool": "prod-lark-site1-hp-gen11"},
        headers=auth(support.ALICE),
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [
        "nodepool: no entry of the day1 file on main renders NodePool prod-lark-site1-hp-gen11; "
        f"its NodePools are {SMALL}, {STORAGE}"
    ]
    assert scale.started == []


async def test_a_name_two_entries_render_is_refused_before_anything_is_sent(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    scale: FakeScaleWorkflow,
) -> None:
    day1 = await support.project_id(gitlab, support.DAY1)
    path = f"{HOSTED}/{LARK}.yaml"
    current = (await gitlab.read_file(day1, RepoPath(path), "main")).content
    storage = "- infraEnvName: dell-r760-site1-64c-512gb-20tb\n"
    twice = current.replace(
        storage, f"- name: {SMALL}\n  infraEnvName: dell-r760-site1-64c-512gb-20tb\n"
    )
    await support.push(gitlab, support.DAY1, branch="main", file=path, content=twice)
    await on.post("/api/webhooks/gitlab", json={"project": {"id": day1}}, headers=WEBHOOK)
    response = await on.post(
        f"{BASE}/scale", json={"replicas": 2, "nodepool": SMALL}, headers=auth(support.ALICE)
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [
        f"nodepool[0] and nodepool[1] both render NodePool {SMALL}: give each its own name in "
        "the day1 file"
    ]
    assert scale.started == []


async def test_a_locked_nodepool_moves_only_to_its_locked_value(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    scale: FakeScaleWorkflow,
) -> None:
    await follow(on, support, gitlab)
    alice = auth(support.ALICE)
    options = (await on.get(f"{BASE}/scale", headers=alice)).json()
    assert options["flavor"] == "agent-sized"
    assert [(p["locked_by"], p["locked_replicas"]) for p in options["nodepools"]] == [
        ("agent-sized", 3),
        (None, None),
    ]
    moved = await on.post(f"{BASE}/scale", json={"replicas": 4, "nodepool": SMALL}, headers=alice)
    assert (moved.status_code, moved.json()["code"]) == (422, "VALIDATION_ERROR")
    assert moved.json()["details"]["problems"] == [
        f"{SMALL}: its replicas are locked by flavor agent-sized at 3; change the flavor, or "
        "restore it to 3"
    ]
    assert scale.started == []
    restore = await on.post(f"{BASE}/scale", json={"replicas": 3, "nodepool": SMALL}, headers=alice)
    assert restore.status_code == 202, restore.text


async def test_a_lost_answer_is_an_ambiguous_write_and_is_logged(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lost(_request: ScaleRequest) -> Any:
        raise AmbiguousStartError("sent, no answer: it may have started")

    monkeypatch.setattr(scale, "start", lost)
    response = await on.post(
        f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=auth(support.ALICE)
    )
    assert (response.status_code, response.json()["code"]) == (504, "AMBIGUOUS_WRITE")
    assert any("scale start unconfirmed" in r.getMessage() for r in caplog.records)


async def test_an_orchestrator_without_update_nodepool_leaves_scale_readable_and_says_so(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turned on before the workflow is deployed: the tab loads, a start says why nothing ran."""

    def before_update_nodepool(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/workflows/runs/"):
            return httpx.Response(404, json={"detail": "Workflow not found"})
        return httpx.Response(404, json={"detail": "Not Found"})  # FastAPI: no such route

    orchestrator = HttpScaleWorkflow(
        base_url="http://workflows-orchestrator-api.test:8080",
        transport=httpx.MockTransport(before_update_nodepool),
    )
    monkeypatch.setattr(scale, "start", orchestrator.start)
    monkeypatch.setattr(scale, "run", orchestrator.run)
    alice = auth(support.ALICE)
    assert (await on.get(f"{BASE}/scale", headers=alice)).status_code == 200
    run = await on.get(f"{BASE}/scale-run", headers=alice)
    assert (run.status_code, run.json()["code"]) == (404, "NOT_FOUND")
    started = await on.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=alice)
    assert (started.status_code, started.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert started.json()["detail"] == (
        "update-nodepool is not deployed on this orchestrator yet (it has no POST "
        f"/workflows/server-lifecycle/update-nodepool): nothing was started for {LARK}. "
        "Scaling works as soon as the workflow is deployed there, with no change to Wingman."
    )
    await orchestrator.aclose()


async def test_a_scale_down_may_choose_its_own_policy_for_the_run(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    run_clock: ManualClock,
) -> None:
    alice = auth(support.ALICE)
    started = await on.post(
        f"{BASE}/scale",
        json={"replicas": 1, "nodepool": STORAGE, "scale_down_policy": "least-requested"},
        headers=alice,
    )
    assert started.status_code == 202, started.text
    assert scale.started == [
        ScaleRequest(MCE, LARK, 1, nodepool=STORAGE, scale_down_policy="least-requested")
    ]
    run_clock.advance(seconds=120)
    result = (await on.get(f"{BASE}/scale-run", headers=alice)).json()["result"]
    assert [p["scale_down_policy"] for p in result["nodepools"]] == ["least-requested"]
    assert {c["policy"] for c in result["chosen"]} == {"least-requested"}


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (
            {"replicas": 1, "nodepool": SMALL, "scale_down_policy": "random"},
            "'fewest-pods', 'least-requested' or 'least-utilized'",
        ),
        (
            {
                "replicas": 2,
                "nodepool": SMALL,
                "scale_down_policy": "fewest-pods",
                "server_names": ["ocp-a"],
            },
            "send scale_down_policy or server_names, not both",
        ),
    ],
)
async def test_an_unknown_policy_or_one_beside_named_servers_is_refused_before_anything_is_sent(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    body: dict[str, Any],
    said: str,
) -> None:
    response = await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    (error,) = response.json()["details"]["errors"]
    assert said in error["msg"]
    assert scale.started == []


@pytest.mark.parametrize(("replicas", "move"), [(4, "3 to 4"), (3, "3 to 3")])
async def test_a_policy_is_chosen_only_for_a_scale_down(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    replicas: int,
    move: str,
) -> None:
    body = {"replicas": replicas, "nodepool": SMALL, "scale_down_policy": "fewest-pods"}
    response = await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [
        f"scale_down_policy: a policy is chosen only for a scale-down; {SMALL} goes from {move}"
    ]
    assert scale.started == []
