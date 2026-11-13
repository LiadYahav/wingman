"""The clusters list's upgrades (ADR-0055's amendments): its runs and its hints.

``GET /api/day1/upgrades`` is behind ``DAY1_UPGRADES`` like the rest of the
upgrade routes; anyone signed in reads it. One cached read of the
orchestrator's run list, one row per cluster (open first), the first rows
read by id for their phase and ``waiting_for``; a start or a decision drops
the cache. ``GET /api/day1/clusters`` carries each cluster's
``upgrade_available`` while upgrades are on: the newest release its MCE
offers above its mastertag, from the day1 repo only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.upgrades import UpgradeDecision, UpgradeRequest
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.fake_upgrade import FakeUpgradeWorkflow
from wingman_day1.infrastructure.fake_upgrade_script import (
    default_upgrade_file,
    load_upgrade_script,
)

Auth = Callable[[User], dict[str, str]]

FLEET = "/api/day1/upgrades"
CLUSTERS = "/api/day1/clusters"
LARK = "ocp4-prod-lark-site1"
HERZI = "ocp4-prod-herzi-site1"


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


def lark(by: str = "alice") -> UpgradeRequest:
    return UpgradeRequest(cluster=LARK, requested_by=by, target_version="4.18.56")


async def test_off_it_is_501_like_every_upgrade_route(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(FLEET, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert "DAY1_UPGRADES" in response.json()["detail"]


async def test_no_runs_is_an_empty_list_and_it_needs_a_session(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await on.get(FLEET, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()) == (200, {"runs": []})
    assert (await on.get(FLEET)).status_code == 401


async def test_each_clusters_run_with_its_phase_and_where_day1_has_it(
    on: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    upgrade: FakeUpgradeWorkflow,
    run_clock: ManualClock,
) -> None:
    await upgrade.start(UpgradeRequest(cluster=HERZI, requested_by="b", target_minor="4.17"))
    await upgrade.decide(
        f"upgrade-cluster-{HERZI}", UpgradeDecision.ABORT, by="b", reason="not today"
    )
    run_clock.advance(60)
    await upgrade.start(lark())
    run_clock.advance(10)  # past planning and the pre-flight
    response = await on.get(FLEET, headers=auth(support.VIEWER))
    assert response.status_code == 200
    first, second = response.json()["runs"]
    assert first == {
        "workflow_id": f"upgrade-cluster-{LARK}",
        "cluster": LARK,
        "site": "site1",
        "mce": "ocp4-prod-mce-site1-a",
        "status": "running",
        "started_at": "2026-11-13T09:01:00+00:00",
        "closed_at": None,
        "phase": "awaiting-approval",
        "waiting_for": first["waiting_for"],
        "paused": False,
        "outcome": None,
    }
    assert first["waiting_for"].startswith("approve: 4.18.22 → 4.18.56")
    assert (second["cluster"], second["status"], second["outcome"]) == (
        HERZI,
        "completed",
        "cancelled",
    )
    assert (second["phase"], second["waiting_for"]) == (None, None)


async def test_a_cluster_day1_does_not_have_is_listed_without_a_place(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    await upgrade.start(
        UpgradeRequest(cluster="ocp4-prod-gone-site1", requested_by="a", target_version="4.18.56")
    )
    [gone] = (await on.get(FLEET, headers=auth(support.ALICE))).json()["runs"]
    assert (gone["cluster"], gone["site"], gone["mce"]) == ("ocp4-prod-gone-site1", None, None)


async def test_the_list_is_cached_and_a_start_or_a_decision_drops_it(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    alice = auth(support.ALICE)
    assert (await on.get(FLEET, headers=alice)).json() == {"runs": []}
    await upgrade.start(lark("outside"))  # not through day1: the cached list does not see it
    assert (await on.get(FLEET, headers=alice)).json() == {"runs": []}
    started = await on.post(
        f"/api/day1/clusters/{HERZI}/upgrade", json={"target_minor": "4.17"}, headers=alice
    )
    assert started.status_code == 202, started.text
    assert {r["cluster"] for r in (await on.get(FLEET, headers=alice)).json()["runs"]} == {
        LARK,
        HERZI,
    }
    aborted = await on.post(
        f"/api/day1/clusters/{HERZI}/upgrade-run/abort", json={"reason": "no"}, headers=alice
    )
    assert aborted.status_code == 200, aborted.text
    runs = {r["cluster"]: r for r in (await on.get(FLEET, headers=alice)).json()["runs"]}
    assert runs[HERZI]["outcome"] == "cancelled"


async def test_an_unreachable_orchestrator_is_502(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    upgrade.unavailable = True
    response = await on.get(FLEET, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")


# ── The clusters list's "Upgrade available" ─────────────────────────────────


async def hints(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, str | None]:
    response = await client.get(CLUSTERS, headers=headers)
    assert response.status_code == 200, response.text
    return {c["name"]: c["upgrade_available"] for c in response.json()}


async def test_off_no_cluster_carries_a_hint(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    listed = await hints(client, auth(support.ALICE))
    assert listed[LARK] is None
    assert set(listed.values()) == {None}


async def test_on_each_cluster_gets_the_newest_release_its_mce_offers_above_its_mastertag(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    listed = await hints(on, auth(support.VIEWER))
    # ocp4-prod-mce-site1-a hosts 4.16 to 4.18: from 4.18.22 and from 4.16.27 alike
    assert (listed[LARK], listed[HERZI]) == ("4.18.56", "4.18.56")
    assert listed["ocp4-prep-eyal-site1"] == "4.21.40"  # 4.20.9; its MCE hosts up to 4.21
    assert listed["ocp4-prep-wren-site2"] is None  # 4.19.10, newer than its MCE's 4.18
    assert listed["ocp4-upgrade-demo"] is None  # at the ladder's newest rung


async def test_the_hints_need_no_orchestrator(
    on: httpx.AsyncClient, auth: Auth, support: Any, upgrade: FakeUpgradeWorkflow
) -> None:
    upgrade.unavailable = True
    assert (await hints(on, auth(support.ALICE)))[LARK] == "4.18.56"


async def test_an_mce_without_its_upgrade_file_suggests_nothing(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    path = RepoPath("upgrade/mces/ocp4-prod-mce-site1-a.yaml")
    pid = await support.project_id(gitlab, support.DAY1)
    current = await gitlab.read_file(pid, path, "main")
    await gitlab.commit(
        pid,
        branch="main",
        message="remove the MCE's rules",
        changes=[FileChange.delete(path, last_commit_id=current.last_commit_id)],
    )
    listed = await hints(on, auth(support.ALICE))
    assert (listed[LARK], listed["ocp4-prep-eyal-site1"]) == (None, "4.21.40")
