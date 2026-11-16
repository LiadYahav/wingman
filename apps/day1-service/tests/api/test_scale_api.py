"""A cluster's NodePools scaled through the update-nodepool workflow, over HTTP (ADR-0062).

Off by default: every route answers 501. With ``DAY1_SCALE_NODEPOOLS`` on,
anyone signed in reads what can be scaled and the run; admins start one, by
kind or by NodePool; day1 fills the MCE and the cluster; a NodePool whose
replicas a flavor locks moves only back to its locked value; everything
else is the workflow's to judge, in its words.
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
        day1_scale_nodepools=True,
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


async def test_off_every_scale_route_is_501(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    for response in (
        await client.get(f"{BASE}/scale", headers=alice),
        await client.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=alice),
        await client.get(f"{BASE}/scale-run", headers=alice),
    ):
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        assert "DAY1_SCALE_NODEPOOLS" in response.json()["detail"]


async def test_the_options_are_the_files_nodepools_and_their_kinds(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await on.get(f"{BASE}/scale", headers=auth(support.VIEWER))
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
    assert body["kinds"] == [
        {"kind": "dell-r660-site1-128c-1024gb-5tb", "nodepools": [SMALL], "total": 3, "locked": []},
        {
            "kind": "dell-r760-site1-64c-512gb-20tb",
            "nodepools": [STORAGE],
            "total": 2,
            "locked": [],
        },
    ]


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


async def test_an_admin_starts_by_kind_or_by_nodepool_and_day1_names_the_mce_and_cluster(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    scale: FakeScaleWorkflow,
    run_clock: ManualClock,
) -> None:
    alice = auth(support.ALICE)
    kind = "dell-r760-site1-64c-512gb-20tb"
    started = await on.post(
        f"{BASE}/scale", json={"replicas": 4, "infra_env_kind": kind}, headers=alice
    )
    assert started.status_code == 202, started.text
    assert {k: started.json()[k] for k in ("workflow_id", "status")} == {
        "workflow_id": f"update-nodepool-{LARK}",
        "status": "running",
    }
    assert scale.started == [ScaleRequest(MCE, LARK, 4, infra_env_kind=kind)]
    busy = await on.post(f"{BASE}/scale", json={"replicas": 1, "nodepool": SMALL}, headers=alice)
    assert (busy.status_code, busy.json()["code"]) == (409, "SCALE_ALREADY_RUNNING")
    assert (
        busy.json()["detail"] == f"An update-nodepool run is already in flight for cluster {LARK}"
    )
    run_clock.advance(seconds=120)
    run = (await on.get(f"{BASE}/scale-run", headers=auth(support.VIEWER))).json()
    assert (run["status"], run["direction"], run["error"]) == ("completed", "up", None)
    assert run["result"]["nodepools"] == [
        {
            "name": STORAGE,
            "infra_env": kind,
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
    on: httpx.AsyncClient, auth: Auth, support: Any, run_clock: ManualClock
) -> None:
    alice = auth(support.ALICE)
    await on.post(f"{BASE}/scale", json={"replicas": 1, "infra_env_kind": "hp"}, headers=alice)
    run_clock.advance(seconds=60)
    run = (await on.get(f"{BASE}/scale-run", headers=alice)).json()
    assert (run["status"], run["phase"], run["error_type"]) == ("failed", "reading-nodepools", None)
    assert "InfraEnv hp or hp-*" in run["error"]


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
    ],
)
async def test_a_body_the_workflow_would_refuse_is_a_422_before_anything_is_sent(
    on: httpx.AsyncClient, auth: Auth, support: Any, scale: FakeScaleWorkflow, body: Any
) -> None:
    response = await on.post(f"{BASE}/scale", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
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
    assert [k["locked"] for k in options["kinds"]] == [[SMALL], []]
    moved = await on.post(f"{BASE}/scale", json={"replicas": 4, "nodepool": SMALL}, headers=alice)
    assert (moved.status_code, moved.json()["code"]) == (422, "VALIDATION_ERROR")
    assert moved.json()["details"]["problems"] == [
        f"{SMALL}: its replicas are locked by flavor agent-sized at 3; change the flavor, or "
        "restore it to 3"
    ]
    by_kind = await on.post(
        f"{BASE}/scale",
        json={"replicas": 4, "infra_env_kind": "dell-r660-site1-128c-1024gb-5tb"},
        headers=alice,
    )
    assert by_kind.status_code == 422
    assert (
        "kind dell-r660-site1-128c-1024gb-5tb selects it"
        in by_kind.json()["details"]["problems"][0]
    )
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
