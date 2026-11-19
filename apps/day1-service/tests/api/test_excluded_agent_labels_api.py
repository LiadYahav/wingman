"""Agent labels every NodePool excludes, over HTTP (ADR-0065).

With ``DAY1_EXCLUDED_AGENT_LABELS`` set, a create writes the keys on every
agent nodepool (``excludeAgentLabels``), the form schema never offers the
input, and a request or a flavor that sets it is refused; a template that does
not render it refuses the create. An existing cluster takes the keys through
its own merge request, ``POST .../excluded-agent-labels``, which leaves a
Replace NodePool out; an edit may not change an existing Replace NodePool's
list. Empty (the default), both routes answer 501 and nothing changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.excluded_agent_labels import GUIDE
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider

Auth = Callable[[User], dict[str, str]]
USED = "redbull.io/used"
LARK = "ocp4-prod-lark-site1"
BASE = f"/api/day1/clusters/{LARK}"
LARK_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{LARK}.yaml"
DELL, HP = "dell-r660-site1-128c-1024gb-5tb", "hp-gen11-site1-64c"
WEBHOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"}
TEMPLATE = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
_START = TEMPLATE.index("{% if excluded_agent_labels")
OLD_TEMPLATE = TEMPLATE[:_START] + TEMPLATE[TEMPLATE.index("{% endif %}", _START) + 12 :]
LINE = f'  excludeAgentLabels: ["{USED}"]\n'


@pytest.fixture
async def on(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        day1_excluded_agent_labels=USED,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


async def push(
    client: httpx.AsyncClient,
    support: Any,
    gitlab: InMemoryGitLab,
    project: str,
    file: str,
    text: str,
) -> None:
    """Commit outside Wingman, then tell it, as GitLab's push webhook does."""
    await support.push(gitlab, project, branch="main", file=file, content=text)
    pid = await support.project_id(gitlab, project)
    await client.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)


def create(support: Any, **variables: Any) -> dict[str, Any]:
    body = support.create_body()
    body["variables"]["nodepools"] = support.nodepools(DELL, HP)
    body["variables"].update(variables)
    return body


def problems(response: httpx.Response) -> list[str]:
    assert response.status_code == 422, response.text
    return response.json()["details"]["problems"]


# ── A create ─────────────────────────────────────────────────────────────────


async def test_a_create_writes_the_keys_on_every_nodepool_and_the_form_never_offers_them(
    on: httpx.AsyncClient, client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    viewer, alice = auth(support.VIEWER), auth(support.ALICE)
    schema = (await on.get("/api/day1/specs/template/schema", headers=viewer)).json()
    assert "excluded_agent_labels" not in [f["name"] for f in schema]
    preview = await on.post("/api/day1/clusters/preview", json=create(support), headers=alice)
    assert preview.status_code == 200, preview.text
    pools = yaml.safe_load(preview.json()["yaml"])["nodepool"]
    assert [p["excludeAgentLabels"] for p in pools] == [[USED], [USED]]
    assert f'    excludeAgentLabels: ["{USED}"]\n' in preview.json()["yaml"]
    plain = await client.post("/api/day1/clusters/preview", json=create(support), headers=alice)
    assert "excludeAgentLabels" not in plain.json()["yaml"], "empty: every file as before"


async def test_a_request_that_sets_the_input_is_refused(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = create(support, excluded_agent_labels=["other"])
    response = await on.post("/api/day1/clusters/preview", json=body, headers=auth(support.ALICE))
    (problem,) = problems(response)
    assert problem.startswith("excluded_agent_labels: set by this deployment")


async def test_a_template_that_does_not_render_the_input_refuses_every_create(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await push(on, support, gitlab, support.SPECS, "cluster-template.j2", OLD_TEMPLATE)
    response = await on.post(
        "/api/day1/clusters/preview", json=create(support), headers=auth(support.ALICE)
    )
    found = problems(response)
    assert [p.split(":")[0] for p in found] == [
        "nodepool[0].excludeAgentLabels",
        "nodepool[1].excludeAgentLabels",
    ]
    assert GUIDE in found[0]


async def test_a_flavor_never_gives_the_input(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    flavor = {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": "agent-used", "version": "1.0.0"},
        "spec": {
            "day1": {
                "values": {"excluded_agent_labels": [USED], "nodepools": [{"infra_env": DELL}]}
            },
            "day2": {"addons": []},
        },
    }
    (problem,) = problems(
        await on.post("/api/day1/specs", json=flavor, headers=auth(support.ALICE))
    )
    assert problem.startswith("excluded_agent_labels: set by this deployment")


# ── An existing cluster ──────────────────────────────────────────────────────


async def test_off_the_plan_and_the_merge_request_answer_501(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    for method in ("GET", "POST"):
        response = await client.request(
            method, f"{BASE}/excluded-agent-labels", json={}, headers=auth(support.ALICE)
        )
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")


async def test_one_merge_request_writes_the_keys_on_the_clusters_nodepools_every_other_line_kept(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    viewer, alice = auth(support.VIEWER), auth(support.ALICE)
    plan = (await on.get(f"{BASE}/excluded-agent-labels", headers=viewer)).json()
    assert plan["labels"] == [USED]
    assert [(p["name"], p["excludes"], p["change"]) for p in plan["nodepools"]] == [
        (DELL, [], True),
        ("dell-r760-site1-64c-512gb-20tb", [], True),
    ]
    forbidden = await on.post(f"{BASE}/excluded-agent-labels", json={}, headers=viewer)
    assert forbidden.status_code == 403
    opened = await on.post(
        f"{BASE}/excluded-agent-labels",
        json={"last_commit_id": plan["last_commit_id"]},
        headers=alice,
    )
    assert opened.status_code == 201, opened.text
    pid = await support.project_id(gitlab, support.DAY1)
    edited = gitlab.snapshot(pid, opened.json()["source_branch"])[LARK_PATH]
    main = (await gitlab.read_file(pid, RepoPath(LARK_PATH), "main")).content
    assert edited.count(LINE) == 2
    assert edited.replace(LINE, "") == main
    assert "ADR-0065" in opened.json()["description"]


async def test_a_replace_nodepool_is_left_out_and_an_edit_may_not_change_its_list(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    pid = await support.project_id(gitlab, support.DAY1)
    main = (await gitlab.read_file(pid, RepoPath(LARK_PATH), "main")).content
    replace = main.replace(
        f"- infraEnvName: {DELL}\n", f"- infraEnvName: {DELL}\n  upgradeType: Replace\n", 1
    )
    await push(on, support, gitlab, support.DAY1, LARK_PATH, replace)
    plan = (await on.get(f"{BASE}/excluded-agent-labels", headers=alice)).json()
    assert [p["change"] for p in plan["nodepools"]] == [False, True]
    assert plan["nodepools"][0]["reason"].startswith("upgradeType Replace")

    cluster = (await on.get(BASE, headers=alice)).json()
    edit = cluster["yaml"].replace("  upgradeType: Replace\n", f"  upgradeType: Replace\n{LINE}", 1)
    refused = await on.patch(
        BASE,
        json={"updated_yaml": edit, "last_commit_id": cluster["last_commit_id"]},
        headers=alice,
    )
    (problem,) = problems(refused)
    assert problem.startswith(
        f"nodepool[0].excludeAgentLabels: NodePool {DELL} is upgradeType Replace"
    )
